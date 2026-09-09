"""Run control-plane migrations with conservative recovery for legacy local volumes.

This wrapper addresses two common development upgrade states:
1. a previous release created the rnd_* tables but did not persist rnd_alembic_version;
2. an interrupted bootstrap left an empty version table next to a complete known schema.

It never drops tables and never guesses through a partial/unknown schema. Known complete
legacy schemas are stamped to the matching frozen revision and then upgraded normally.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from factory.config import get_settings
from factory.database import Database

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "alembic.ini"
VERSION_TABLE = "rnd_alembic_version"

V1_COLUMNS: dict[str, set[str]] = {
    "rnd_project": {"id", "owner_id", "title", "template_id", "messages", "created_at"},
    "rnd_run": {
        "id", "project_id", "owner_id", "idempotency_key", "request", "status", "spec",
        "spec_digest", "decision", "artifact", "artifact_sha256", "checks", "error",
        "created_at", "updated_at",
    },
    "rnd_event": {"id", "run_id", "level", "message", "created_at"},
    "rnd_outbox": {"id", "run_id", "kind", "sent", "attempts", "error"},
}

V2_COLUMNS: dict[str, set[str]] = {
    **V1_COLUMNS,
    "rnd_provider_profile": {
        "id", "owner_id", "name", "provider", "base_url", "model", "api_key_ciphertext",
        "enabled", "is_default", "config", "created_at", "updated_at",
    },
}
V2_COLUMNS["rnd_project"] = V1_COLUMNS["rnd_project"] | {
    "clarification_status", "clarification", "clarification_provider_id", "updated_at"
}
V2_COLUMNS["rnd_run"] = V1_COLUMNS["rnd_run"] | {"stage_details"}
V2_COLUMNS["rnd_event"] = V1_COLUMNS["rnd_event"] | {"stage", "tool", "payload"}

KNOWN_TABLES = set(V2_COLUMNS)
V2_MARKERS: dict[str, set[str]] = {
    "rnd_project": {"clarification_status", "clarification", "clarification_provider_id", "updated_at"},
    "rnd_run": {"stage_details"},
    "rnd_event": {"stage", "tool", "payload"},
    "rnd_provider_profile": set(V2_COLUMNS["rnd_provider_profile"]),
}


@dataclass(frozen=True)
class SchemaSnapshot:
    tables: Mapping[str, frozenset[str]]
    version_table_present: bool = False
    version: str | None = None


def _has_columns(snapshot: SchemaSnapshot, expected: Mapping[str, set[str]]) -> tuple[bool, list[str]]:
    problems: list[str] = []
    for table, required in expected.items():
        actual = set(snapshot.tables.get(table, frozenset()))
        if not actual:
            problems.append(f"missing table {table}")
            continue
        missing = sorted(required - actual)
        if missing:
            problems.append(f"{table} missing columns: {', '.join(missing)}")
    return not problems, problems


def classify_schema(snapshot: SchemaSnapshot) -> tuple[str, list[str]]:
    """Return managed/fresh/legacy:<revision>/incompatible plus diagnostics."""
    if snapshot.version_table_present and snapshot.version:
        return "managed", [f"current revision: {snapshot.version}"]

    app_tables = {name for name in snapshot.tables if name.startswith("rnd_") and name != VERSION_TABLE}
    if not app_tables:
        return "fresh", []

    unknown = sorted(app_tables - KNOWN_TABLES)
    if unknown:
        return "incompatible", [f"unknown rnd_* tables: {', '.join(unknown)}"]

    v2_ok, v2_problems = _has_columns(snapshot, V2_COLUMNS)
    if v2_ok:
        return "legacy:rnd_0002", []

    # If any v2-only marker exists, the schema is partially upgraded. Do not stamp over it.
    markers: list[str] = []
    for table, columns in V2_MARKERS.items():
        actual = set(snapshot.tables.get(table, frozenset()))
        if table == "rnd_provider_profile" and table in snapshot.tables:
            markers.append(table)
        elif columns & actual:
            markers.append(f"{table}({', '.join(sorted(columns & actual))})")
    if markers:
        return "incompatible", [
            "partial rnd_0002 markers detected: " + "; ".join(markers),
            *v2_problems,
        ]

    v1_ok, v1_problems = _has_columns(snapshot, V1_COLUMNS)
    if v1_ok:
        return "legacy:rnd_0001", []
    return "incompatible", v1_problems


def snapshot_database(db: Database) -> SchemaSnapshot:
    inspector = inspect(db.engine)
    names = set(inspector.get_table_names())
    tables: dict[str, frozenset[str]] = {}
    for name in names:
        if name.startswith("rnd_"):
            tables[name] = frozenset(column["name"] for column in inspector.get_columns(name))

    version: str | None = None
    present = VERSION_TABLE in names
    if present:
        with db.engine.connect() as connection:
            version = connection.execute(text(f"SELECT version_num FROM {VERSION_TABLE} LIMIT 1")).scalar_one_or_none()
    return SchemaSnapshot(tables=tables, version_table_present=present, version=version)


def _alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


def main() -> int:
    settings = get_settings()
    db = Database(settings.database_url)
    try:
        snapshot = snapshot_database(db)
    except OperationalError as exc:
        raise SystemExit(
            "DATABASE_PREFLIGHT_FAILED: cannot authenticate/connect using FACTORY_DATABASE_URL. "
            "For an existing Docker volume after .env regeneration, inspect `docker compose logs postgres-auth-sync migrate`."
        ) from exc

    state, diagnostics = classify_schema(snapshot)
    print(f"Control-plane migration preflight: {state}")
    for item in diagnostics:
        print(f"  - {item}")

    cfg = _alembic_config()
    if state.startswith("legacy:"):
        revision = state.split(":", 1)[1]
        print(f"Recognized complete legacy schema; stamping {revision} without changing application tables.")
        command.stamp(cfg, revision)
    elif state == "incompatible":
        raise SystemExit(
            "CONTROL_PLANE_SCHEMA_INCOMPATIBLE: existing rnd_* schema is partial or unknown; "
            "no tables were dropped and no revision was stamped. Inspect the diagnostics above and back up the database before repair."
        )

    command.upgrade(cfg, "head")
    print("Control-plane migrations are at head.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
