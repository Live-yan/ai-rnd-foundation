from __future__ import annotations

from scripts.migrate_control_plane import (
    V1_COLUMNS,
    V2_COLUMNS,
    SchemaSnapshot,
    classify_schema,
)


def _snapshot(columns: dict[str, set[str]], *, version_table: bool = False, version: str | None = None) -> SchemaSnapshot:
    return SchemaSnapshot(
        tables={name: frozenset(values) for name, values in columns.items()},
        version_table_present=version_table,
        version=version,
    )


def test_fresh_database_is_not_stamped() -> None:
    state, problems = classify_schema(_snapshot({}))
    assert state == "fresh"
    assert problems == []


def test_existing_version_table_remains_alembic_managed() -> None:
    state, problems = classify_schema(_snapshot({}, version_table=True, version="rnd_0002"))
    assert state == "managed"
    assert problems == ["current revision: rnd_0002"]


def test_complete_v1_schema_without_version_is_safely_recognized() -> None:
    state, problems = classify_schema(_snapshot(V1_COLUMNS))
    assert state == "legacy:rnd_0001"
    assert problems == []


def test_complete_v2_schema_with_empty_version_table_is_safely_recognized() -> None:
    state, problems = classify_schema(_snapshot(V2_COLUMNS, version_table=True, version=None))
    assert state == "legacy:rnd_0002"
    assert problems == []


def test_partial_v2_schema_is_never_stamped() -> None:
    partial = {name: set(columns) for name, columns in V1_COLUMNS.items()}
    partial["rnd_run"].add("stage_details")
    state, problems = classify_schema(_snapshot(partial))
    assert state == "incompatible"
    assert any("partial rnd_0002 markers" in problem for problem in problems)


def test_unknown_rnd_table_is_never_stamped() -> None:
    unknown = {name: set(columns) for name, columns in V2_COLUMNS.items()}
    unknown["rnd_future_state"] = {"id"}
    state, problems = classify_schema(_snapshot(unknown))
    assert state == "incompatible"
    assert problems == ["unknown rnd_* tables: rnd_future_state"]


def test_missing_v1_column_is_never_stamped() -> None:
    partial = {name: set(columns) for name, columns in V1_COLUMNS.items()}
    partial["rnd_project"].remove("messages")
    state, problems = classify_schema(_snapshot(partial))
    assert state == "incompatible"
    assert any("rnd_project missing columns: messages" == problem for problem in problems)
