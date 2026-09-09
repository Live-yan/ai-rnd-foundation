from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import Path, PurePosixPath
from uuid import UUID

EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "logs", ".env", ".idea"}


def run_path(root: Path, run_id: str) -> Path:
    # UUID-only, never user-provided filesystem paths.
    canonical = str(UUID(run_id))
    path = root.resolve() / "runs" / canonical
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if "\\" in value or path.is_absolute() or ".." in path.parts or ":" in value:
        raise ValueError("Unsafe relative path")
    if not path.parts or any(part in {"", "."} for part in path.parts):
        raise ValueError("Empty path")
    return path


def include_file(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if path.is_symlink() or any(p in EXCLUDED_DIRS for p in rel.parts):
        return False
    name = path.name
    if name.startswith(".env") and not (name.endswith(".example") or name == ".env.example"):
        return False
    if name.endswith((".pem", ".key", ".p12", ".pyc")) or name in {"credentials.json", ".DS_Store"}:
        return False
    return path.is_file()


def redact(message: str, secrets: list[str] = ()) -> str:
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[REDACTED]")
    message = re.sub(r"(Bearer\s+)[^\s\"']+", r"\1[REDACTED]", message, flags=re.I)
    message = re.sub(r"(postgresql(?:\+\w+)?://[^:]+:)[^@]+@", r"\1[REDACTED]@", message)
    return message[:2500]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def token_matches(actual: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(actual, expected)
