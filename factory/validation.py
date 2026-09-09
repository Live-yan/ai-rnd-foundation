from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from .config import Settings
from .providers.sandbox import cube_verify, docker_verify


def execute_json(args: list[str], cwd: Path, timeout: int = 90) -> dict:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout,
                            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"})
    if result.returncode:
        raise RuntimeError("Verification failed: " + result.stderr[-2000:] + result.stdout[-1000:])
    return json.loads(result.stdout)


def verify_product(product: Path, run_id: str, request: dict, settings: Settings) -> dict:
    from .evidence import source_digest, require_full_quality
    before = source_digest(product)
    full = request.get("pipeline_mode") == "full"
    report = {
        "quality_level": "scaffold_ready", "full_stack": "not_run", "production_ready": False,
        "frontend_build": "not_run", "postgres_integration": "not_run", "upstream_auth": "not_run",
        "provider_id": request.get("provider_id"), "requested_provider": request.get("provider") or "profile",
        "requested_sandbox": request.get("sandbox", "static"), "pipeline_mode": request.get("pipeline_mode", "core"),
    }
    report["source"] = execute_json([sys.executable, str(product / "scripts/verify_source.py")], product)
    report["business_contract"] = execute_json([sys.executable, str(product / "scripts/verify_business.py")], product)
    openspec = shutil.which("openspec")
    if not openspec:
        if settings.openspec_required:
            raise RuntimeError("OpenSpec CLI missing. Install @fission-ai/openspec@1.12.0")
        report["openspec"] = "not_run_cli_missing"
    else:
        result = subprocess.run(
            [openspec, "validate", "create-product", "--type", "change", "--strict", "--no-interactive"],
            cwd=product, text=True, capture_output=True, timeout=45,
            env={"PATH": os.environ.get("PATH", ""), "HOME": "/tmp", "LANG": "C.UTF-8", "OPENSPEC_TELEMETRY": "0", "CI": "1"},
        )
        report["openspec"] = {"exit_code": result.returncode, "output": (result.stdout + result.stderr)[-5000:]}
        if result.returncode:
            raise RuntimeError("OpenSpec validation did not pass: " + report["openspec"]["output"][-2000:])
    sandbox = request.get("sandbox", "static")
    if sandbox == "docker":
        report["sandbox"] = docker_verify(product, run_id, settings)
    elif sandbox == "cube":
        report["sandbox"] = cube_verify(product, settings, full_stack=full)
        if full:
            result = report["sandbox"]["result"]
            for key in ("full_stack", "frontend_build", "frontend_types", "postgres_integration", "upstream_auth",
                        "redis_sessions", "business_owner_isolation", "frontend_mount"):
                report[key] = result.get(key, "not_run")
            report["quality_level"] = "generated_crud_stack_verified"
            report["browser_interactions"] = result.get("browser_interactions", "not_run")
    else:
        report["sandbox"] = {"provider": "static", "scope": "trusted_source_and_business_contracts_only",
                             "untrusted_code_execution": "disabled"}
    report["architecture"] = json.loads((product / "delivery/receipt.json").read_text())["architecture"]
    if before != source_digest(product):
        raise RuntimeError("Product source changed during verification")
    report["source_digest"] = before
    if full:
        require_full_quality(report)
    return report
