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


RUNTIME_CHECKS = ("full_stack", "frontend_build", "frontend_types", "postgres_integration", "upstream_auth",
                  "redis_sessions", "business_owner_isolation", "frontend_mount")
YUDAO_RUNTIME_CHECKS = tuple('mysql_integration' if key == 'postgres_integration' else key for key in RUNTIME_CHECKS) + ('backend_build',)


def require_runtime_quality(checks: dict, expected_source_digest: str | None = None) -> None:
    from .providers.sandbox import RuntimeVerificationError
    sandbox = checks.get("sandbox") or {}
    result = sandbox.get("result") or {}
    digest = checks.get("source_digest")
    archive_hash = sandbox.get("input_sha256")
    template_id = checks.get('template_id', 'fastapiadmin-pg-v1')
    required = YUDAO_RUNTIME_CHECKS if template_id == 'yudao-cloud-mini-antd-v1' else RUNTIME_CHECKS
    if (checks.get("validation_level") != "runtime"
            or checks.get("quality_level") != "generated_crud_stack_verified"
            or checks.get("production_ready") is not False
            or template_id not in ('fastapiadmin-pg-v1', 'yudao-cloud-mini-antd-v1')
            or (template_id == 'yudao-cloud-mini-antd-v1' and result.get('template_id') != template_id)
            or any(checks.get(key) != "passed" or result.get(key) != "passed" for key in required)
            or sandbox.get("provider") != "docker" or sandbox.get("scope") != "generated_crud_stack"
            or sandbox.get("executed") is not True or sandbox.get("exit_code") != 0
            or not sandbox.get("container_id") or not sandbox.get("image")
            or not isinstance(archive_hash, str) or len(archive_hash) != 64
            or any(c not in "0123456789abcdef" for c in archive_hash)
            or result.get("archive_sha256") != archive_hash
            or result.get("scope") != "generated_crud_stack" or result.get("production_ready") is not False
            or result.get("schema_version") != 1 or not isinstance(result.get("assertions"), int)
            or result.get("assertions", 0) < 5
            or not isinstance(digest, str) or len(digest) != 64
            or sandbox.get("source_digest") != digest
            or (expected_source_digest is not None and digest != expected_source_digest)):
        raise RuntimeVerificationError("运行验收证据不完整或与源码不一致，请重新运行 Docker 全栈验收。")
