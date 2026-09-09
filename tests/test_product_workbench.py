from pathlib import Path

import pytest
from fastapi import HTTPException

from factory.config import Settings
from factory.database import Database, ProviderProfile
from factory.providers.registry import ProviderService
from factory.repository import Repository
from factory.schemas import ClarificationResult, ProjectInput, ProviderInput, RunInput
from scripts.bootstrap import install_factory_frontend


def test_fastapiadmin_workbench_installs_three_routes_and_typed_api(tmp_path: Path) -> None:
    target = tmp_path / "FastapiAdmin"
    menu = target / "frontend/web/src/router/MenuProcessor.ts"
    menu.parent.mkdir(parents=True)
    menu.write_text(
        'import type { AppRouteRecord } from "@/types/router";\n'
        'export const builtinFrontendRoutes: AppRouteRecord[] = [];\n',
        encoding="utf-8",
    )
    install_factory_frontend(target)
    text = menu.read_text(encoding="utf-8")
    assert text.count("AI-RND-FRONTEND-ROUTE:factory:v2") == 1
    for path in ["/factory", "/factory-providers", "/factory-toolchain"]:
        assert f'path: "{path}"' in text
    assert (target / "frontend/web/src/api/module_factory/index.ts").is_file()
    assert (target / "frontend/web/src/views/factory/FactoryConsole.vue").is_file()
    assert (target / "frontend/web/src/views/factory-providers/ProviderManager.vue").is_file()
    assert (target / "frontend/web/src/views/factory-toolchain/ToolchainCenter.vue").is_file()


def test_provider_secret_is_encrypted_and_never_returned() -> None:
    db = Database("sqlite:///:memory:", test_only=True)
    db.initialize_for_tests()
    settings = Settings(_env_file=None, credential_encryption_key="test-key-" * 6)
    service = ProviderService(db, settings)
    public = service.create("u1", ProviderInput(
        name="primary", provider="openai", model="test-model", api_key="top-secret", is_default=True,
    ))
    assert public["has_api_key"] is True
    assert "api_key" not in public
    runtime = service.runtime("u1", public["id"])
    assert runtime.api_key == "top-secret"
    with db.session() as session:
        row = session.get(ProviderProfile, public["id"])
        assert row.api_key_ciphertext and "top-secret" not in row.api_key_ciphertext
    db.engine.dispose()


def test_custom_provider_rejects_non_http_endpoint() -> None:
    db = Database("sqlite:///:memory:", test_only=True)
    db.initialize_for_tests()
    service = ProviderService(db, Settings(_env_file=None, credential_encryption_key="x" * 48))
    with pytest.raises(HTTPException) as exc:
        service.create("u1", ProviderInput(
            name="bad", provider="custom_openai", model="m", base_url="file:///etc/passwd",
        ))
    assert exc.value.status_code == 422
    db.engine.dispose()


def test_new_run_requires_clarification_but_legacy_demo_keeps_test_path() -> None:
    db = Database("sqlite:///:memory:", test_only=True)
    db.initialize_for_tests()
    repo = Repository(db)
    project = repo.create_project("u1", ProjectInput(title="t", requirement="build a device register"))
    legacy = repo.create_run("u1", project["id"], RunInput(idempotency_key="legacy-demo-001"))
    assert legacy["status"] == "QUEUED"

    project2 = repo.create_project("u1", ProjectInput(title="t2", requirement="build another register"))
    with pytest.raises(HTTPException) as exc:
        repo.create_run("u1", project2["id"], RunInput(
            provider="litellm", provider_id="provider-id", idempotency_key="strict-model-001",
        ))
    assert exc.value.status_code == 409
    db.engine.dispose()


def test_clarification_ready_requires_actionable_acceptance_criteria() -> None:
    with pytest.raises(ValueError):
        ClarificationResult(ready=True, understanding="clear", questions=[], acceptance_criteria=[])
    value = ClarificationResult(
        ready=False, understanding="still ambiguous", questions=["Who can approve records?"], acceptance_criteria=[]
    )
    assert value.ready is False
