"""Explicit, project-scoped reset for local development.

Default platform startup never calls this module. It is only used when the user
passes --fresh. Named Compose volumes are removed via `docker compose down
--volumes`, while host bind-mounted data is moved into an ignored backup folder
instead of being deleted. Optional --new-env also rotates the local .env.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _require_repo_root(root: Path) -> None:
    required = [root / "compose.yaml", root / "pyproject.toml", root / "scripts" / "init_env.py"]
    missing = [str(path.relative_to(root)) for path in required if not path.exists()]
    if missing:
        raise SystemExit("REFUSING_RESET: repository markers missing: " + ", ".join(missing))


def _move_if_present(source: Path, destination: Path) -> bool:
    if not _lexists(source):
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return True


def reset_local(*, root: Path = ROOT, new_env: bool = False, dry_run: bool = False) -> Path | None:
    """Reset only this Compose project's local state and return backup directory."""
    _require_repo_root(root)
    env_file = root / ".env"
    data_path = root / "data"
    backup_root = root / "runtime" / "reset-backups" / _timestamp()

    compose = ["docker", "compose", "down", "--volumes", "--remove-orphans"]
    print("Fresh reset requested explicitly.")
    print("Compose action:", " ".join(compose))
    print("Host data action: move active data/ into runtime/reset-backups before recreating it.")
    if new_env:
        print("Environment action: rotate .env and generate a new one after reset.")
    else:
        print("Environment action: preserve current .env and credentials.")

    if dry_run:
        return backup_root

    subprocess.run(compose, cwd=root, check=True)

    moved_any = False
    if _move_if_present(data_path, backup_root / "data"):
        moved_any = True
        print(f"Backed up host data to {backup_root / 'data'}")

    if new_env and _move_if_present(env_file, backup_root / ".env"):
        moved_any = True
        print(f"Backed up .env to {backup_root / '.env'}")

    data_path.mkdir(parents=True, exist_ok=False)
    print(f"Created fresh data directory: {data_path}")
    return backup_root if moved_any else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reset this repository's local Compose state explicitly.")
    parser.add_argument("--new-env", action="store_true", help="also rotate .env so init_env.py generates new credentials")
    parser.add_argument("--dry-run", action="store_true", help="show actions without changing Docker or files")
    args = parser.parse_args(argv)
    reset_local(new_env=args.new_env, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
