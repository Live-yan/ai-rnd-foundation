"""Read-only, stdlib prerequisite check; not an end-to-end health certificate."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]


def _path_kind(path: Path) -> str:
    if path.is_symlink():
        if not path.exists():
            return "broken_symlink"
        return "symlink_directory" if path.is_dir() else "symlink_file"
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    if os.path.lexists(path):
        return "other"
    return "missing"


result = {
    "python": sys.version.split()[0],
    "root": str(R),
    "env_exists": (R / ".env").is_file(),
    "data_path": {
        "path": str(R / "data"),
        "state": _path_kind(R / "data"),
    },
    "upstream_downloaded_on_host": (R / ".vendor/FastapiAdmin/LICENSE").is_file(),
    "checks": {},
    "notes": {
        "uv": "Host uv is optional for the Docker-first startup path; the application image contains pinned uv.",
        "data": "missing is normal before init_env.py; file/broken_symlink/symlink_file/other must be repaired before Docker startup.",
    },
}
for command in ("docker", "git", "uv"):
    path = shutil.which(command)
    result["checks"][command] = "found" if path else "missing"
if shutil.which("docker"):
    for key, args in [
        ("docker_daemon", ["docker", "info", "--format", "{{.ServerVersion}}"]),
        ("compose", ["docker", "compose", "version"]),
    ]:
        try:
            p = subprocess.run(args, capture_output=True, text=True, timeout=15)
            result["checks"][key] = p.stdout.strip()[:150] if p.returncode == 0 else "unavailable"
        except subprocess.TimeoutExpired:
            result["checks"][key] = "timeout"
print(json.dumps(result, ensure_ascii=False, indent=2))
