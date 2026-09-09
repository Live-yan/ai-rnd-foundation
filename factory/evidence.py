"""Fail-closed acceptance predicates shared by worker and regression tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .packaging import files_for_package
from .security import file_sha256


def source_digest(product: Path) -> str:
    excluded = {"delivery/quality.json", "delivery/files.sha256.json", ".rnd-source-sha256"}
    inventory = {p.relative_to(product).as_posix(): file_sha256(p) for p in files_for_package(product)
                 if p.relative_to(product).as_posix() not in excluded}
    return hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def require_full_quality(checks: dict) -> None:
    required = ["full_stack", "frontend_build", "frontend_types", "postgres_integration", "upstream_auth",
                "redis_sessions", "business_owner_isolation", "frontend_mount"]
    if any(checks.get(key) != "passed" for key in required):
        raise RuntimeError("Full mode requires real frontend, PostgreSQL, Redis and authenticated product acceptance")
    sandbox = checks.get("sandbox") or {}
    result = sandbox.get("result") or {}
    if (sandbox.get("provider") != "cube" or sandbox.get("scope") != "generated_crud_stack"
            or not sandbox.get("sandbox_id") or result.get("full_stack") != "passed"
            or result.get("archive_sha256") != sandbox.get("input_sha256")
            or not sandbox.get("input_sha256")):
        raise RuntimeError("Full mode requires a Cube execution receipt bound to the uploaded source archive")
    if not isinstance(checks.get("openspec"), dict) or checks["openspec"].get("exit_code") != 0:
        raise RuntimeError("Full mode requires a successful OpenSpec validation")
    architecture = checks.get("architecture") or {}
    if (architecture.get("c4_dsl") != "parser_validated"
            or (architecture.get("structurizr") or {}).get("validated") is not True
            or architecture.get("diagrams") != "rendered_portable_svg"):
        raise RuntimeError("Full mode requires parsed C4 and rendered diagrams, not just source files")
    if checks.get("source", {}).get("source_ast") != "passed" or checks.get("business_contract", {}).get("business_contract_sqlite") != "passed":
        raise RuntimeError("Source and business contract checks did not pass")


def require_full_delivery(checks: dict, stages: dict, artifact_sha256: str) -> None:
    require_full_quality(checks)
    context = stages.get("context") or {}
    if context.get("used") is not True or context.get("chars", 0) <= 0 or context.get("status") != "CONTEXT_READY":
        raise RuntimeError("Full mode requires completed ToolHive/Serena context retrieval")
    if not stages.get("openspec", {}).get("validated"):
        raise RuntimeError("Approval must follow successful OpenSpec analysis validation")
    coder = checks.get("coder") or {}
    if (coder.get("source_import") != "sha256_verified" or coder.get("source_sha256") != artifact_sha256
            or coder.get("readiness") != "running_source_imported" or not coder.get("workspace_id")):
        raise RuntimeError("Full mode requires a running Coder workspace with this exact ZIP import receipt")
