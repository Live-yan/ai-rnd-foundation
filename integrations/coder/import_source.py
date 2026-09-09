"""Fixed Coder template importer. No model-generated command or platform credential.

The platform grants read access to one immutable ZIP for at most fifteen minutes.
Extraction is staged; existing developer work is never overwritten.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import urllib.request
from urllib.parse import urlsplit
from zipfile import ZipFile

MAX_ARCHIVE = 128 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024
MARKER = ".rnd-source-sha256"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Source download redirects are not allowed")


def extract_verified(archive: Path, target: Path, expected: str) -> None:
    """Verify first, stage safely, then publish atomically without overwriting work."""
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("Invalid expected SHA-256")
    if target.is_symlink():
        raise ValueError("Workspace target must not be a symlink")
    if target.exists():
        marker = target / MARKER
        if marker.is_file() and not marker.is_symlink() and marker.read_text().strip() == expected:
            return
        raise ValueError("Workspace contains different or unverified work; refusing to overwrite it")
    if archive.stat().st_size > MAX_ARCHIVE:
        raise ValueError("Source archive is too large")
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError("Source archive integrity check failed")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".rnd-import-", dir=target.parent))
    try:
        with ZipFile(archive) as zf:
            members = zf.infolist()
            if len(members) > 50000 or sum(m.file_size for m in members) > MAX_EXPANDED:
                raise ValueError("Source archive expansion limit exceeded")
            names: set[str] = set()
            for member in members:
                raw = member.filename
                path = PurePosixPath(raw)
                mode = member.external_attr >> 16
                if (not raw or "\\" in raw or "\x00" in raw or path.is_absolute()
                        or ".." in path.parts or ":" in raw or path.as_posix() == MARKER
                        or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR})):
                    raise ValueError("Unsafe archive entry")
                name = path.as_posix()
                if name in names:
                    raise ValueError("Duplicate archive entry")
                names.add(name)
                destination = staging / path
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as source, destination.open("xb") as output:
                        shutil.copyfileobj(source, output)
                    destination.chmod(0o755 if mode & stat.S_IXUSR else 0o644)
        receipt = staging / "delivery/approved-spec.json"
        if not receipt.is_file() or not isinstance(json.loads(receipt.read_text()), dict):
            raise ValueError("Expected generated product receipt is missing")
        (staging / MARKER).write_text(expected + "\n")
        # The agent runs one startup script. Recheck before rename to preserve prior work.
        if target.exists() or target.is_symlink():
            raise ValueError("Workspace changed during import; refusing to overwrite it")
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> None:
    target = Path.home() / "project"
    url = os.environ.get("RND_SOURCE_URL", "")
    token = os.environ.pop("RND_SOURCE_TOKEN", "")
    expected = os.environ.get("RND_SOURCE_SHA256", "")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Invalid source URL")
    # Persistent workspaces can restart after the capability has expired.
    marker = target / MARKER
    if not target.is_symlink() and marker.is_file() and not marker.is_symlink() and marker.read_text().strip() == expected:
        print("Verified product already present; preserving developer work")
        return
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with tempfile.TemporaryDirectory(prefix="rnd-download-") as temporary:
        archive = Path(temporary) / "product.zip"
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(request, timeout=45) as response, archive.open("xb") as output:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_ARCHIVE:
                    raise ValueError("Source download limit exceeded")
                output.write(chunk)
        extract_verified(archive, target, expected)
    print("Product source imported and SHA-256 verified")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Do not echo URLs, tokens, HTTP bodies or provider exception chains to agent logs.
        raise SystemExit("Source import failed. Check template configuration and the platform run; existing work was preserved.") from None
