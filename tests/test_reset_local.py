from __future__ import annotations

from pathlib import Path

import pytest

from scripts import reset_local


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "init_env.py").write_text("# marker\n", encoding="utf-8")
    (tmp_path / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\nversion='0'\n", encoding="utf-8")
    return tmp_path


def test_fresh_reset_preserves_env_and_archives_active_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _repo(tmp_path)
    (root / ".env").write_text("POSTGRES_PASSWORD=keep-me\n", encoding="utf-8")
    data = root / "data"
    data.mkdir()
    (data / "artifact.txt").write_text("old-data", encoding="utf-8")
    calls: list[tuple[list[str], Path]] = []

    monkeypatch.setattr(reset_local, "_timestamp", lambda: "20260909T000000Z")
    monkeypatch.setattr(reset_local.subprocess, "run", lambda args, cwd, check: calls.append((args, cwd)))

    backup = reset_local.reset_local(root=root)

    assert calls == [(["docker", "compose", "down", "--volumes", "--remove-orphans"], root)]
    assert (root / ".env").read_text(encoding="utf-8") == "POSTGRES_PASSWORD=keep-me\n"
    assert (root / "data").is_dir()
    assert not any((root / "data").iterdir())
    assert backup == root / "runtime/reset-backups/20260909T000000Z"
    assert (backup / "data/artifact.txt").read_text(encoding="utf-8") == "old-data"


def test_fresh_new_env_archives_env_for_regeneration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _repo(tmp_path)
    (root / ".env").write_text("SECRET_KEY=old\n", encoding="utf-8")
    (root / "data").mkdir()
    monkeypatch.setattr(reset_local, "_timestamp", lambda: "20260909T010000Z")
    monkeypatch.setattr(reset_local.subprocess, "run", lambda *args, **kwargs: None)

    backup = reset_local.reset_local(root=root, new_env=True)

    assert not (root / ".env").exists()
    assert (backup / ".env").read_text(encoding="utf-8") == "SECRET_KEY=old\n"
    assert (root / "data").is_dir()


def test_dry_run_changes_nothing_and_does_not_call_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _repo(tmp_path)
    (root / ".env").write_text("A=B\n", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data/keep").write_text("yes", encoding="utf-8")

    def fail(*args, **kwargs):
        raise AssertionError("docker must not run during dry-run")

    monkeypatch.setattr(reset_local.subprocess, "run", fail)
    reset_local.reset_local(root=root, new_env=True, dry_run=True)

    assert (root / ".env").read_text(encoding="utf-8") == "A=B\n"
    assert (root / "data/keep").read_text(encoding="utf-8") == "yes"


def test_reset_refuses_unknown_directory(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        reset_local.reset_local(root=tmp_path, dry_run=True)
    assert "REFUSING_RESET" in str(exc.value)
