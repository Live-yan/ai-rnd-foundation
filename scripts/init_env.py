"""Generate local development secrets and prepare the persistent data directory safely."""
from __future__ import annotations

import argparse
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _new_values(password: str | None = None) -> dict[str, str]:
    password = password or secrets.token_hex(24)
    return {
        "COMPOSE_PROJECT_NAME": "ai-rnd",
        "POSTGRES_PASSWORD": password,
        "REDIS_PASSWORD": secrets.token_hex(24),
        "SECRET_KEY": secrets.token_hex(48),
        "FACTORY_TOKEN": secrets.token_hex(32),
        "FACTORY_CREDENTIAL_ENCRYPTION_KEY": secrets.token_hex(48),
        "FACTORY_DATABASE_URL": f"postgresql+psycopg://factory:{password}@postgres:5432/factory",
        "FACTORY_MODEL_API_KEY": "",
        "FACTORY_MODEL_NAME": "factory-planner",
        "FACTORY_MODEL_ALLOWED_ORIGINS": '["http://litellm:4000","http://host.docker.internal:11434"]',
        "FACTORY_CODER_AUTO_IMPORT": "False",
        "FACTORY_CODER_FACTORY_URL": "",
        "FACTORY_CODER_IMPORT_TIMEOUT": "240",
        "FACTORY_MODEL_BASE_URL": "http://litellm:4000/v1",
        "LITELLM_MASTER_KEY": "sk-" + secrets.token_hex(24),
        "OLLAMA_MODEL": "REPLACE_WITH_AN_INSTALLED_MODEL",
        "FACTORY_SERENA_URL": "",
        "FACTORY_SERENA_TOKEN": "",
        "FACTORY_CUBE_API_URL": "",
        "FACTORY_CUBE_API_KEY": "",
        "FACTORY_CUBE_TEMPLATE": "",
        "FACTORY_CODER_URL": "",
        "FACTORY_CODER_TOKEN": "",
        "FACTORY_CODER_TEMPLATE_ID": "",
        "FACTORY_CODER_OWNER_ID": "",
        "FACTORY_DOCKER_HOST_DATA_DIR": str(ROOT / "data"),
    }


def _path_kind(path: Path) -> str:
    """Describe a path without following a broken symlink away."""
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


def _backup_name(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = path.with_name(f"{path.name}.conflict-{stamp}")
    index = 1
    while os.path.lexists(candidate):
        candidate = path.with_name(f"{path.name}.conflict-{stamp}-{index}")
        index += 1
    return candidate


def ensure_data_dir(*, repair: bool = False) -> Path:
    """Ensure ROOT/data is usable without silently deleting an existing object.

    A valid directory (including a symlink to a directory) is preserved. A
    regular file, broken symlink, symlink to a file, or another filesystem
    object is treated as a conflict. With ``repair=True`` the conflicting
    object is moved aside to a timestamped backup before a fresh directory is
    created. Nothing is deleted.
    """
    data_dir = ROOT / "data"
    kind = _path_kind(data_dir)
    if kind in {"directory", "symlink_directory"}:
        return data_dir
    if kind == "missing":
        try:
            data_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            # Another initializer (or Docker) may create the bind-mount source
            # between the read-only probe above and mkdir. Re-check before
            # treating the harmless race as a path conflict.
            kind = _path_kind(data_dir)
            if kind in {"directory", "symlink_directory"}:
                return data_dir
            if kind == "missing":
                raise SystemExit(
                    f"Cannot initialize {data_dir}: the path changed during creation; retry the command."
                )
        else:
            return data_dir

    if not repair:
        raise SystemExit(
            f"Cannot initialize {data_dir}: path type is {kind}, not a directory.\n"
            "This commonly happens after overwriting an older checkout or after a stale/broken bind-mount link.\n"
            "Inspect it with: ls -ld data && file data\n"
            "To recover without deleting it, run: python3 scripts/init_env.py --repair-data"
        )

    backup = _backup_name(data_dir)
    data_dir.rename(backup)
    data_dir.mkdir(parents=True, exist_ok=False)
    print(f"Moved conflicting data path to {backup.name}; created a fresh data directory.")
    return data_dir


def _ensure_env_file() -> None:
    target = ROOT / ".env"
    if target.exists() and not target.is_file():
        raise SystemExit(f"Cannot initialize {target}: it exists but is not a regular file.")
    if target.is_symlink() and not target.exists():
        raise SystemExit(f"Cannot initialize {target}: it is a broken symlink.")

    if target.exists():
        text = target.read_text(encoding="utf-8")
        existing = {
            line.split("=", 1)[0]
            for line in text.splitlines()
            if "=" in line and not line.lstrip().startswith("#")
        }
        additions: dict[str, str] = {}
        if "FACTORY_CREDENTIAL_ENCRYPTION_KEY" not in existing:
            additions["FACTORY_CREDENTIAL_ENCRYPTION_KEY"] = secrets.token_hex(48)
        defaults = _new_values()
        for key in (
            "FACTORY_MODEL_ALLOWED_ORIGINS",
            "FACTORY_CODER_AUTO_IMPORT",
            "FACTORY_CODER_FACTORY_URL",
            "FACTORY_CODER_IMPORT_TIMEOUT",
        ):
            if key not in existing:
                additions[key] = defaults[key]
        if additions:
            with target.open("a", encoding="utf-8") as handle:
                handle.write("\n# Added by a newer AI R&D platform release; existing values were preserved.\n")
                for key, value in additions.items():
                    handle.write(f"{key}={value}\n")
            target.chmod(0o600)
            print(".env existing values preserved; appended missing workbench settings.")
        else:
            print(".env already exists; kept unchanged.")
        return

    values = _new_values()
    target.write_text(
        "# Local-only. Do not upload this file.\n" + "\n".join(f"{k}={v}" for k, v in values.items()) + "\n",
        encoding="utf-8",
    )
    target.chmod(0o600)
    print("Created .env with random secrets. Configure at least one real model provider in the FastapiAdmin UI.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repair-data",
        action="store_true",
        help="move a conflicting data path to a timestamped backup, then create data/; never deletes the old object",
    )
    args = parser.parse_args(argv)

    # Preflight the bind-mount source first. The old order wrote .env and then
    # failed on data/, leaving a partially initialized checkout whose next run
    # returned early because .env already existed.
    ensure_data_dir(repair=args.repair_data)
    _ensure_env_file()


if __name__ == "__main__":
    main()
