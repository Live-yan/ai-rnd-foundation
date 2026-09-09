from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import init_env


def _use_root(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(init_env, "ROOT", root)


def test_existing_env_still_creates_missing_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_root(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text("FACTORY_CREDENTIAL_ENCRYPTION_KEY=existing\n", encoding="utf-8")

    init_env.main([])

    assert (tmp_path / "data").is_dir()
    assert "FACTORY_CREDENTIAL_ENCRYPTION_KEY=existing" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_directory_created_after_missing_probe_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_root(monkeypatch, tmp_path)
    data = tmp_path / "data"
    real_mkdir = Path.mkdir

    def racing_mkdir(
        path: Path, mode: int = 0o777, parents: bool = False, exist_ok: bool = False
    ) -> None:
        if path == data and not data.exists():
            real_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)
            raise FileExistsError(17, "File exists", str(path))
        real_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", racing_mkdir)
    init_env.main([])

    assert data.is_dir()
    assert (tmp_path / ".env").is_file()


def test_data_file_conflict_fails_before_creating_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_root(monkeypatch, tmp_path)
    (tmp_path / "data").write_text("preserve me", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        init_env.main([])

    message = str(exc.value)
    assert "path type is file" in message
    assert "--repair-data" in message
    assert not (tmp_path / ".env").exists()
    assert (tmp_path / "data").read_text(encoding="utf-8") == "preserve me"


def test_repair_moves_conflicting_file_without_deleting_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_root(monkeypatch, tmp_path)
    (tmp_path / "data").write_text("old payload", encoding="utf-8")

    init_env.main(["--repair-data"])

    assert (tmp_path / "data").is_dir()
    backups = list(tmp_path.glob("data.conflict-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "old payload"
    assert (tmp_path / ".env").is_file()


def test_repair_current_failure_shape_preserves_existing_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_root(monkeypatch, tmp_path)
    env = tmp_path / ".env"
    env.write_text("POSTGRES_PASSWORD=keep-this\nFACTORY_CREDENTIAL_ENCRYPTION_KEY=existing\n", encoding="utf-8")
    (tmp_path / "data").write_text("stale bind-mount object", encoding="utf-8")

    init_env.main(["--repair-data"])

    assert (tmp_path / "data").is_dir()
    assert "POSTGRES_PASSWORD=keep-this" in env.read_text(encoding="utf-8")
    backups = list(tmp_path.glob("data.conflict-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "stale bind-mount object"


def test_repair_preserves_broken_symlink_as_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_root(monkeypatch, tmp_path)
    data = tmp_path / "data"
    data.symlink_to(tmp_path / "missing-target", target_is_directory=True)
    assert os.path.lexists(data)
    assert not data.exists()

    init_env.main(["--repair-data"])

    assert data.is_dir()
    backups = list(tmp_path.glob("data.conflict-*"))
    assert len(backups) == 1
    assert backups[0].is_symlink()
    assert os.path.lexists(backups[0])


def test_valid_data_directory_is_never_replaced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_root(monkeypatch, tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    marker = data / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    init_env.main(["--repair-data"])

    assert marker.read_text(encoding="utf-8") == "keep"
    assert not list(tmp_path.glob("data.conflict-*"))
