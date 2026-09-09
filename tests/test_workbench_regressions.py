"""Deterministic regression tests. External-provider HTTP replies are mocks, not live receipts."""
import asyncio
import hashlib
import json
import stat
import time
from dataclasses import replace
from uuid import uuid4
from zipfile import ZipFile, ZipInfo

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Header
from fastapi.testclient import TestClient

from factory.api import create_router
from factory.clarifier import _conversation
from factory.config import Settings
from factory.database import Run
from factory.handoff import issue_source_ticket, verify_source_ticket
from factory.providers.coder import CoderClient
from factory.providers.endpoint_policy import validate_model_origin
from factory.providers.llm import litellm_model
from factory.providers.registry import ProviderRuntime, ProviderService
from factory.repository import Repository
from factory.schemas import ClarificationResult, ProjectInput, ProviderInput, ProviderUpdate, RunInput, demo_spec
from integrations.coder.import_source import extract_verified


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, credential_encryption_key="test-only-" * 6, data_dir=tmp_path,
                    model_allowed_origins=["http://gateway:4000"])


def profile():
    return ProviderRuntime(id="p", name="p", provider="openrouter", base_url="", model="anthropic/example",
                           api_key="test-key-not-a-real-secret", temperature=0.1, max_tokens=1000)


def create_project(db):
    return Repository(db).create_project("a", ProjectInput(title="Test", requirement="Create a register"))


def create_run(db):
    p = create_project(db)
    return Repository(db).create_run("a", p["id"], RunInput(idempotency_key=str(uuid4())))


def test_native_envelope_status_and_root_path_legacy(db, settings):
    app = FastAPI(root_path="/api/v1")
    def actor(x_actor: str = Header("a")):
        return x_actor
    app.include_router(create_router(db, settings, actor))
    with TestClient(app) as client:
        response = client.post("/api/v1/factory/projects", json={"title": "t", "requirement": "new requirement"})
        assert response.status_code == 201
        body = response.json()
        assert body["code"] == 0 and isinstance(body["data"]["created_at"], str)
        raw = client.get("/api/v1/factory-api/projects")
        assert isinstance(raw.json(), list)
        assert client.get("/api/v1/factory/projects").json()["data"][0]["id"] == body["data"]["id"]


def test_explicit_provider_never_falls_back_or_crosses_owner(db, settings):
    settings.model_api_key = "configured-system-key"
    service = ProviderService(db, settings)
    row = service.create("a", ProviderInput(name="test", provider="openai", model="example", api_key="private"))
    for owner, id in [("b", row["id"]), ("a", "missing")]:
        with pytest.raises(HTTPException) as exc:
            service.runtime(owner, id)
        assert exc.value.status_code == 404
    service.update("a", row["id"], ProviderUpdate(enabled=False))
    with pytest.raises(HTTPException):
        service.runtime("a", row["id"])
    assert "test-key-not-a-real-secret" not in repr(profile())


@pytest.mark.parametrize("provider,model,expected", [
    ("openrouter", "anthropic/example", "openrouter/anthropic/example"),
    ("custom_openai", "team/model", "openai/team/model"),
    ("anthropic", "anthropic/example", "anthropic/example"),
    ("azure_openai", "deployment", "azure/deployment"),
])
def test_vendor_selection_is_not_changed_by_model_prefix(provider, model, expected):
    assert litellm_model(replace(profile(), provider=provider, model=model)) == expected


def test_custom_endpoint_is_administrator_approved(settings):
    validate_model_origin("custom_openai", "http://gateway:4000/v1", settings)
    for value in ["http://169.254.169.254/latest", "http://gateway:4001/v1", "https://unapproved.example/v1"]:
        with pytest.raises(HTTPException):
            validate_model_origin("custom_openai", value, settings)


def test_stale_ai_analysis_does_not_approve_new_requirements(db):
    repo = Repository(db)
    p = create_project(db)
    repo.add_message("a", p["id"], "Add a critical approval workflow")
    result = ClarificationResult(ready=True, understanding="A register", acceptance_criteria=["Users can list own records"])
    with pytest.raises(HTTPException) as exc:
        repo.save_clarification("a", p["id"], result, "p", expected_revision=p["revision"])
    assert exc.value.status_code == 409
    current = repo.get_project("a", p["id"])
    assert current["clarification_status"] == "NEEDS_CLARIFICATION"
    assert current["messages"][-1]["content"] == "Add a critical approval workflow"


def test_ai_receives_its_prior_questions():
    text = _conversation([{"role": "assistant", "content": "Need details", "questions": ["Private or shared data?"]},
                          {"role": "user", "content": "Private"}])
    assert "Private or shared data?" in text and "Private" in text


def test_artifact_preview_is_owner_scoped_and_whitelisted(db, settings):
    from factory.modules.workbench.service import WorkbenchService
    run = create_run(db)
    root = settings.data_dir / "runs" / run["id"] / "analysis"
    (root / "architecture").mkdir(parents=True)
    (root / "architecture/workspace.dsl").write_text("workspace {}")
    (root / "secret.env").write_text("do-not-expose")
    service = WorkbenchService(db, settings)
    assert service.analysis_files("a", run["id"]) == ["architecture/workspace.dsl"]
    assert service.analysis_file("a", run["id"], "architecture/workspace.dsl").read_text() == "workspace {}"
    for actor, path in [("b", "architecture/workspace.dsl"), ("a", "secret.env"), ("a", "../../secret.env")]:
        with pytest.raises(HTTPException):
            service.analysis_file(actor, run["id"], path)
    outside = settings.data_dir / "outside.txt"
    outside.write_text("outside")
    (root / "architecture/er.svg").symlink_to(outside)
    assert "architecture/er.svg" not in service.analysis_files("a", run["id"])


def test_capability_is_expiring_and_bound_to_one_archive(settings, monkeypatch):
    run_id = str(uuid4())
    now = int(time.time())
    monkeypatch.setattr("factory.handoff.time.time", lambda: now)
    token = issue_source_ticket(run_id, "a" * 64, settings)
    verify_source_ticket(token, run_id, "a" * 64, settings)
    for other_run, sha in [(str(uuid4()), "a" * 64), (run_id, "b" * 64)]:
        with pytest.raises(HTTPException):
            verify_source_ticket(token, other_run, sha, settings)
    with pytest.raises(HTTPException):
        verify_source_ticket(token + "x", run_id, "a" * 64, settings)
    monkeypatch.setattr("factory.handoff.time.time", lambda: now + 901)
    with pytest.raises(HTTPException):
        verify_source_ticket(token, run_id, "a" * 64, settings)


def test_source_capability_requires_approval_and_verifies_bytes(db, settings):
    run = create_run(db)
    artifact = settings.data_dir / "source.zip"
    artifact.write_bytes(b"immutable archive fixture")
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    with db.session() as session:
        row = session.get(Run, run["id"])
        row.artifact = "source.zip"; row.artifact_sha256 = sha; row.status = "PACKAGED"
    token = issue_source_ticket(run["id"], sha, settings)
    app = FastAPI()
    app.include_router(create_router(db, settings, lambda: "a"))
    with TestClient(app) as client:
        path = "/factory/transfer/" + run["id"]
        headers = {"Authorization": "Bearer " + token}
        assert client.get(path, headers=headers).status_code == 403
        with db.session() as session:
            session.get(Run, run["id"]).decision = {"approve": True}
        assert client.get(path).status_code == 403
        assert client.get(path, headers=headers).content == b"immutable archive fixture"
        artifact.write_bytes(b"changed")
        assert client.get(path, headers=headers).status_code == 409


def test_coder_reuses_workspace_but_requires_import_receipt(settings):
    settings.coder_url = "https://coder.example"
    settings.coder_token = "test-coder-key"
    settings.coder_template_id = "template"
    settings.coder_import_timeout = 0
    data = {"id": "ws", "owner_name": "owner", "template_id": "template", "latest_build": {"status": "running", "resources": []}}
    calls = []
    def reply(request):
        calls.append(request.method)
        return httpx.Response(200, json=data)
    client = CoderClient(settings, httpx.MockTransport(reply))
    source = {"url": "https://platform.example/factory/transfer/run", "token": "capability", "sha256": "a" * 64}
    with pytest.raises(RuntimeError, match="not confirmed"):
        asyncio.run(client.create_workspace(str(uuid4()), source=source))
    data["latest_build"]["resources"] = [{"agents": [{"status": "connected", "metadata": [
        {"description": {"key": "rnd_source_sha256"}, "result": {"value": "a" * 64 + "\n", "error": ""}}
    ]}]}]
    result = asyncio.run(client.create_workspace(str(uuid4()), source=source))
    assert result["source_import"] == "sha256_verified"
    assert "POST" not in calls
    assert "capability" not in json.dumps(result)


def zip_file(tmp_path, extra=None):
    path = tmp_path / "source.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("delivery/approved-spec.json", demo_spec().model_dump_json())
        archive.writestr("backend/app.py", "print('trusted source fixture')")
        if extra:
            archive.writestr(*extra)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_importer_verifies_and_preserves_developer_edits(tmp_path):
    archive, sha = zip_file(tmp_path)
    target = tmp_path / "project"
    extract_verified(archive, target, sha)
    (target / "backend/app.py").write_text("developer edit")
    extract_verified(archive, target, sha)
    assert (target / "backend/app.py").read_text() == "developer edit"
    with pytest.raises(ValueError):
        extract_verified(archive, target, "b" * 64)


@pytest.mark.parametrize("entry", ["../../escape", "/tmp/escape", "bad\\escape", ".rnd-source-sha256"])
def test_importer_rejects_unsafe_zip(tmp_path, entry):
    archive, sha = zip_file(tmp_path, (entry, "unsafe"))
    with pytest.raises(ValueError):
        extract_verified(archive, tmp_path / "project", sha)
    assert not (tmp_path / "project").exists()


def test_importer_rejects_symlinks_and_bad_hash(tmp_path):
    link = ZipInfo("link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    archive, sha = zip_file(tmp_path, (link, "/etc/passwd"))
    with pytest.raises(ValueError):
        extract_verified(archive, tmp_path / "project", sha)
    with pytest.raises(ValueError):
        extract_verified(archive, tmp_path / "project", "0" * 64)
