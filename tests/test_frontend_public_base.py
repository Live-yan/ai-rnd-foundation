from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_public_base_matches_fastapi_root_path() -> None:
    manifest = json.loads((ROOT / "templates/fastapiadmin/manifest.json").read_text(encoding="utf-8"))
    expected = f"{manifest['root_path'].rstrip('/')}/{manifest['frontend_mount'].strip('/')}/"
    assert manifest["frontend_public_base"] == expected == "/api/v1/web/"


def test_platform_and_delivery_builds_do_not_force_legacy_web_base() -> None:
    platform = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    delivery = (ROOT / "overlays/product/Dockerfile.delivery").read_text(encoding="utf-8")
    bootstrap = (ROOT / "scripts/bootstrap.py").read_text(encoding="utf-8")

    assert "--base=/web/" not in platform
    assert "--base=/web/" not in delivery
    assert "/api/v1/web/" in platform
    assert "VITE_BASE_URL=/api/v1/web/" in delivery
    assert "VITE_BASE_URL={frontend_public_base()}" in bootstrap


def _run_checker(tmp_path: Path, asset_base: str) -> subprocess.CompletedProcess[str]:
    dist = tmp_path / "dist"
    (dist / "js").mkdir(parents=True)
    (dist / "js/app.js").write_text("console.log('ok')", encoding="utf-8")
    (dist / "index.html").write_text(
        f'<html><body><script type="module" src="{asset_base}js/app.js"></script></body></html>',
        encoding="utf-8",
    )
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify_frontend_dist.py"), str(dist), "/api/v1/web/"],
        text=True,
        capture_output=True,
        check=False,
    )


def test_frontend_dist_checker_accepts_root_path_aware_assets(tmp_path: Path) -> None:
    result = _run_checker(tmp_path, "/api/v1/web/")
    assert result.returncode == 0, result.stderr


def test_frontend_dist_checker_rejects_legacy_assets_that_cause_white_screen(tmp_path: Path) -> None:
    result = _run_checker(tmp_path, "/web/")
    assert result.returncode == 1
    assert "asset escapes public base" in result.stderr
