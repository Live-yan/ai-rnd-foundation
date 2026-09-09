"""Regression contracts; mocked receipts are never reported as online acceptance."""
import asyncio
import io
import json
import logging
from uuid import uuid4

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.background import BackgroundTask
import pytest

from factory.api import create_router
from factory.config import Settings
from factory.database import Project, Run
from factory.evidence import require_full_delivery, source_digest
from factory.privacy import install_sdk_log_safety, metadata_only_route
from factory.repository import Repository
from factory.schemas import ClarificationResult, ProjectInput, RunInput


def ready_project(db):
    repo = Repository(db)
    project = repo.create_project("owner", ProjectInput(title="Register", requirement="Create a private register"))
    result = ClarificationResult(ready=True, understanding="Private register", acceptance_criteria=["Other users cannot read it"])
    return repo, repo.save_clarification("owner", project["id"], result, "provider", expected_revision=project["revision"])


def test_stale_browser_cannot_run_new_ready_analysis(db):
    repo, first = ready_project(db)
    changed = repo.add_message("owner", first["id"], "Add a new field")
    second = repo.save_clarification("owner", first["id"], ClarificationResult(
        ready=True, understanding="Register with new field", acceptance_criteria=["New field is persisted"]),
        "provider", expected_revision=changed["revision"])
    request = RunInput(provider="litellm", provider_id="provider", expected_revision=first["revision"], idempotency_key=str(uuid4()))
    with pytest.raises(HTTPException) as exc:
        repo.create_run("owner", first["id"], request)
    assert exc.value.status_code == 409
    run = repo.create_run("owner", first["id"], request.model_copy(update={"expected_revision": second["revision"]}))
    repo.add_message("owner", first["id"], "Another future requirement")
    with db.session() as session:
        stored = session.get(Run, run["id"])
        assert stored.request["clarification_revision"] == second["revision"]
        assert stored.request["clarification"]["understanding"] == "Register with new field"
        assert "Another future requirement" not in json.dumps(stored.request)


def test_legacy_ready_analysis_without_provenance_cannot_generate(db):
    repo, project = ready_project(db)
    with db.session() as session:
        row = session.get(Project, project["id"])
        value = dict(row.clarification)
        value.pop("conversation_revision")
        row.clarification = value
    with pytest.raises(HTTPException) as exc:
        repo.create_run("owner", project["id"], RunInput(provider="litellm", idempotency_key=str(uuid4())))
    assert exc.value.status_code == 409


def test_native_api_requires_reviewed_revision(db, tmp_path):
    app = FastAPI()
    app.include_router(create_router(db, Settings(_env_file=None, data_dir=tmp_path), lambda: "owner"))
    with TestClient(app) as client:
        response = client.post('/factory/projects/id/runs', json={"provider": "litellm", "idempotency_key": str(uuid4())})
        assert response.status_code == 428


def test_analysis_in_flight_cannot_overwrite_answer(db, tmp_path, monkeypatch):
    from factory.modules.workbench.service import WorkbenchService
    from factory.providers.registry import ProviderRuntime
    repo, project = ready_project(db)
    service = WorkbenchService(db, Settings(_env_file=None, data_dir=tmp_path))
    profile = ProviderRuntime(id="provider", name="p", provider="custom_openai", base_url="", model="fixture",
                              api_key="fixture", temperature=0.1, max_tokens=1000)
    monkeypatch.setattr(service.providers, "runtime", lambda *args: profile)
    async def fake_analysis(*args):
        repo.add_message("owner", project["id"], "New blocking requirement")
        return ClarificationResult(ready=True, understanding="Old result", acceptance_criteria=["Old acceptance"])
    monkeypatch.setattr("factory.modules.workbench.service.clarify", fake_analysis)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.clarify_project("owner", project["id"], "provider"))
    assert exc.value.status_code == 409
    current = repo.get_project("owner", project["id"])
    assert current["clarification_status"] == "NEEDS_CLARIFICATION"
    assert current["messages"][-1]["content"] == "New blocking requirement"


def test_audit_never_collects_success_invalid_json_or_schema_input(db, tmp_path):
    records = []
    async def writer(record):
        records.append(record)
    route = metadata_only_route(APIRoute, writer, lambda request: "127.0.0.1", ["POST", "PUT", "DELETE"])
    app = FastAPI()
    app.include_router(create_router(db, Settings(_env_file=None, data_dir=tmp_path,
        credential_encryption_key="test-only-" * 6), lambda: "owner", route_class=route))
    secret = "audit-sentinel-not-a-real-provider-key"
    with TestClient(app) as client:
        valid = {"name": "key-test", "provider": "openai", "model": "test", "api_key": secret}
        result = client.post("/factory/providers", json=valid)
        assert result.status_code == 201
        assert secret not in result.text
        invalid = client.post("/factory/providers", json=valid | {"unknown-secret-field": secret})
        assert invalid.status_code == 422 and secret not in invalid.text
        broken = client.post("/factory/providers", content='{"api_key": "' + secret,
                             headers={"Content-Type": "application/json"})
        assert broken.status_code == 422 and secret not in broken.text
    assert len(records) == 3
    assert secret not in json.dumps(records)
    assert [r["response_code"] for r in records] == [201, 422, 422]
    assert all(r["request_payload"] == '{"body":"[OMITTED_BY_CREDENTIAL_POLICY]"}' for r in records)


def test_audit_retains_background_tasks_and_hides_exception_chains():
    completed = []
    async def writer(record):
        completed.append("audit")
    route = metadata_only_route(APIRoute, writer, lambda request: "127.0.0.1", ["POST"])
    router = APIRouter(route_class=route)
    @router.post("/ok")
    def ok():
        return JSONResponse({"ok": True}, background=BackgroundTask(completed.append, "original"))
    @router.post("/failure")
    def failed():
        raise RuntimeError("private-exception-sentinel")
    app = FastAPI(); app.include_router(router)
    with TestClient(app) as client:
        assert client.post("/ok").status_code == 200
        assert completed == ["original", "audit"]
        failed = client.post("/failure")
        assert failed.status_code == 500 and "private-exception-sentinel" not in failed.text
    assert completed == ["original", "audit", "audit"]


@pytest.mark.parametrize("name", ["LiteLLM", "LiteLLM.Router", "openai._base_client", "httpcore.connection", "e2b.api"])
def test_sdk_logs_created_after_bootstrap_cannot_expose_keys(name, monkeypatch):
    previous = logging.getLogRecordFactory()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger(name)
    old_handlers, old_level, old_propagate = logger.handlers, logger.level, logger.propagate
    try:
        install_sdk_log_safety()
        install_sdk_log_safety()  # idempotent, no nested growth
        logger.handlers = [handler]; logger.setLevel(logging.DEBUG); logger.propagate = False
        try:
            raise ValueError("exception-key-sentinel")
        except ValueError:
            logger.exception("api_key=%s", "argument-key-sentinel")
        output = stream.getvalue()
        assert "sentinel" not in output and "Traceback" not in output
        assert "omitted" in output
    finally:
        logger.handlers, logger.level, logger.propagate = old_handlers, old_level, old_propagate
        logging.setLogRecordFactory(previous)


def valid_full_evidence():
    archive_sha = "a" * 64
    input_sha = "b" * 64
    fields = ["full_stack", "frontend_build", "frontend_types", "postgres_integration", "upstream_auth",
              "redis_sessions", "business_owner_isolation", "frontend_mount"]
    checks = {key: "passed" for key in fields}
    checks.update({
        "source": {"source_ast": "passed"}, "business_contract": {"business_contract_sqlite": "passed"},
        "openspec": {"exit_code": 0},
        "architecture": {"c4_dsl": "parser_validated", "structurizr": {"validated": True}, "diagrams": "rendered_portable_svg"},
        "sandbox": {"provider": "cube", "scope": "generated_crud_stack", "sandbox_id": "fixture-not-live",
                    "input_sha256": input_sha, "result": {"archive_sha256": input_sha, "full_stack": "passed"}},
        "coder": {"source_import": "sha256_verified", "source_sha256": archive_sha,
                  "readiness": "running_source_imported", "workspace_id": "fixture-not-live"},
    })
    stages = {"context": {"used": True, "chars": 120, "status": "CONTEXT_READY"}, "openspec": {"validated": True}}
    return checks, stages, archive_sha


def test_full_delivery_accepts_complete_matching_receipts():
    require_full_delivery(*valid_full_evidence())


@pytest.mark.parametrize("field", ["full_stack", "frontend_build", "frontend_types", "postgres_integration",
                                   "upstream_auth", "redis_sessions", "business_owner_isolation", "frontend_mount"])
@pytest.mark.parametrize("bad", ["not_run", "skipped", "failed", True, None])
def test_unexecuted_or_failed_checks_never_complete_full_mode(field, bad):
    checks, stages, sha = valid_full_evidence()
    checks[field] = bad
    with pytest.raises(RuntimeError):
        require_full_delivery(checks, stages, sha)


@pytest.mark.parametrize("path,bad", [
    (("sandbox", "scope"), "source_only"), (("sandbox", "provider"), "static"),
    (("sandbox", "sandbox_id"), ""), (("sandbox", "result", "archive_sha256"), "c" * 64),
    (("coder", "source_import"), "manual_zip_upload"), (("coder", "source_sha256"), "c" * 64),
    (("coder", "readiness"), "created_not_build_verified"), (("coder", "workspace_id"), ""),
    (("openspec", "exit_code"), 1), (("architecture", "c4_dsl"), "source_only"),
    (("architecture", "structurizr", "validated"), False), (("architecture", "diagrams"), "not_run_dependency_missing"),
])
def test_partial_or_mismatched_tool_receipt_cannot_complete(path, bad):
    checks, stages, sha = valid_full_evidence()
    target = checks
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = bad
    with pytest.raises(RuntimeError):
        require_full_delivery(checks, stages, sha)


def test_source_digest_binds_code_but_allows_quality_metadata(tmp_path):
    (tmp_path / "code.py").write_text("print('original')")
    original = source_digest(tmp_path)
    (tmp_path / "delivery").mkdir()
    (tmp_path / "delivery/quality.json").write_text('{"full_stack":"passed"}')
    assert source_digest(tmp_path) == original
    (tmp_path / "code.py").write_text("print('changed')")
    assert source_digest(tmp_path) != original


def test_full_verifier_does_not_echo_failed_subprocess_output(tmp_path):
    import sys
    from scripts.full_stack import run_check
    with pytest.raises(RuntimeError) as exc:
        run_check([sys.executable, "-c", "print('private-child-secret');raise SystemExit(1)"],
                  cwd=tmp_path, env={}, phase="unit-check")
    assert "private-child-secret" not in str(exc.value)
    assert "unit-check" in str(exc.value)
