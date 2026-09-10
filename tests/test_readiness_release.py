"""Release contracts. No credentials or external service calls are used here."""
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from factory.api import create_router
from factory.config import Settings
from factory.providers.export_config import export_config
from factory.providers.registry import ProviderService
from factory.schemas import ProviderInput, ProviderCredentials
from factory.toolchain import validate_structurizr


def test_structurizr_receives_file_not_wrapper_default_directory(tmp_path, monkeypatch):
    analysis = tmp_path / 'analysis'
    (analysis / 'architecture').mkdir(parents=True)
    (analysis / 'architecture/workspace.dsl').write_text('workspace {}')
    calls = []
    def execute(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout='validated', stderr='')
    monkeypatch.setattr('factory.toolchain.subprocess.run', execute)
    result = validate_structurizr(analysis, str(uuid4()), Settings(_env_file=None, docker_host_data_dir='/srv/rnd/data'))
    command = calls[0]
    assert command[-5:] == ['-jar', '/usr/local/structurizr.war', 'validate', '-w', '/usr/local/structurizr/workspace.dsl']
    assert command[command.index('--entrypoint')+1] == 'java'
    assert command[command.index('--user')+1] == '10001:10001'
    assert '--network' in command and 'none' in command
    assert calls[-1][:3] == ['docker', 'rm', '-f']
    assert result['validated'] is True


def test_no_store_and_legacy_demo_fail_closed(db, tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, credential_encryption_key='unit-only-' * 6)
    app = FastAPI()
    app.include_router(create_router(db, settings, lambda: 'owner', admin_dependency=lambda: True))
    with TestClient(app) as client:
        for path in ['/factory/projects', '/factory-api/projects']:
            response = client.post(path, json={'title': 'Register', 'requirement': 'Create a register'})
            assert response.status_code == 201
            assert response.headers['cache-control'] == 'no-store'
        project = response.json()
        result = client.post(f'/factory-api/projects/{project["id"]}/runs', json={'idempotency_key': str(uuid4())})
        assert result.status_code == 422
        reset = client.delete('/factory/toolchain/coder/config?revision=0')
        assert reset.status_code == 200 and reset.json()['data']['revision'] == 1
        assert client.delete('/factory/toolchain/coder/config?revision=0').status_code == 409


def test_subscription_profiles_are_not_exported_to_shared_proxy():
    profiles = [{'id': 'test-account', 'provider': 'chatgpt', 'enabled': True}]
    value = export_config(profiles)
    assert value['skipped'] == [{'id': 'test-account', 'reason': 'owner_scoped_subscription_not_shareable'}]
    assert value['environment_variables'] == ['LITELLM_MASTER_KEY']
    assert 'chatgpt/' not in value['yaml']


def test_supplier_credentials_cannot_be_mixed(db):
    service = ProviderService(db, Settings(_env_file=None, credential_encryption_key='unit-only-' * 6))
    with pytest.raises(HTTPException) as exc:
        service.create('owner', ProviderInput(name='bad', provider='openai', model='test',
            credentials=ProviderCredentials(aws_access_key_id='not-a-real-key')))
    assert exc.value.status_code == 422


@pytest.mark.parametrize('value', [
    '{"type":"external_account","credential_source":{"file":"/etc/passwd"}}',
    '{"type":"service_account","token_uri":"https://unapproved.example/token"}',
    '/tmp/credentials.json',
])
def test_vertex_untrusted_credentials_are_rejected(value):
    with pytest.raises(ValueError):
        ProviderCredentials(vertex_credentials=value)


def test_c4_metadata_is_data_and_duplicate_labels_are_disambiguated():
    from factory.artifacts import c4_dsl, dsl_quote
    from factory.schemas import demo_spec
    spec = demo_spec()
    spec.title = '中文 \"name\" ${SECRET}\n!include /etc/passwd\ufeff'
    for entity in spec.entities:
        entity.label = "Authentication adapter"
    text = c4_dsl(spec)
    assert text.startswith('workspace {\n  name "')
    assert '${SECRET}' not in text and '\ufeff' not in text
    assert '\n!include' not in text
    assert '"Authentication adapter (device)"' in text
    assert '"Authentication adapter (maintenance)"' in text
    assert dsl_quote('a\u2028b') == '"a b"'


def test_cube_image_uses_locked_dependencies_and_portable_python_without_tls_bypass():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "integrations/cube/Dockerfile.fullstack").read_text()
    assert "DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt-get install" in dockerfile
    assert "UV_PYTHON_DOWNLOADS=never" in dockerfile
    assert "UV_PYTHON_INSTALL_DIR=/opt/rnd-python" in dockerfile
    assert "UV_NATIVE_TLS=true" in dockerfile
    assert "SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt" in dockerfile
    assert "--python 3.12 --no-python-downloads" in dockerfile
    assert "--frozen --no-dev" in dockerfile
    assert "/app/runtime/combined/uv.lock" in dockerfile
    assert "uv python install 3.12" in dockerfile
    assert "python3.12-venv" not in dockerfile
    assert "COPY --from=cache /usr/local/bin/python" not in dockerfile
    assert "allow-insecure-host" not in dockerfile
    assert not any(line.startswith(("CMD ", "ENTRYPOINT ")) for line in dockerfile.splitlines())
    workflow = (root / ".github/workflows/tests.yml").read_text()
    assert "bash scripts/verify_cube_image.sh" in workflow
