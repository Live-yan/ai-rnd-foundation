"""Account device authorization contracts: no real login or provider requests."""
import asyncio
import json

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
import httpx
import pytest

from factory.config import Settings
from factory.database import ProviderProfile
from factory.privacy import metadata_only_route
from factory.providers.oauth import OAuthService, VERIFICATION_URL
from factory.providers.registry import ProviderService
from factory.schemas import ProviderInput
from factory.tool_probe import probe
from factory.tool_settings import ToolSettingsService


@pytest.fixture
def account(db):
    settings = Settings(_env_file=None, credential_encryption_key='account-test-only-' * 5)
    profile = ProviderService(db, settings).create('owner', ProviderInput(
        name='Personal account', provider='chatgpt', model='gpt-5'))
    return OAuthService(db, settings), profile['id']


def test_device_begin_is_owner_scoped_encrypted_and_restart_replaces_pending(db, account, monkeypatch):
    service, profile = account
    calls = []
    def job(data):
        calls.append(data['operation'])
        return {'pending': {'verification_url': VERIFICATION_URL, 'user_code': 'fixture-code-' + str(len(calls)),
                            'device_auth_id': 'private-device-id', 'interval': '5'}}
    monkeypatch.setattr('factory.providers.oauth.isolated_job', job)
    with pytest.raises(HTTPException) as exc:
        service.operation('other-owner', profile, 'begin')
    assert exc.value.status_code == 404 and not calls
    first = service.operation('owner', profile, 'begin')
    assert first['status'] == 'pending' and first['verification_url'] == VERIFICATION_URL
    assert 'private-device-id' not in json.dumps(first)
    assert service.operation('owner', profile, 'begin')['user_code'] == first['user_code']
    assert len(calls) == 1
    with db.session() as session:
        stored = json.dumps(session.get(ProviderProfile, profile).config)
        assert 'private-device-id' not in stored and first['user_code'] not in stored
    second = service.operation('owner', profile, 'restart')
    assert second['user_code'] != first['user_code'] and len(calls) == 2
    service.operation('owner', profile, 'disconnect')
    assert service.operation('owner', profile, 'poll')['status'] == 'not_connected'
    assert len(calls) == 2, 'Poll after disconnect must never initiate login'


def test_installed_sdk_device_contract_and_no_shared_auth_file(tmp_path, monkeypatch):
    from litellm.llms.chatgpt.authenticator import Authenticator
    from factory.providers.subscription_worker import execute
    monkeypatch.setenv('CHATGPT_TOKEN_DIR', str(tmp_path))
    monkeypatch.setenv('CHATGPT_AUTH_FILE', 'auth.json')
    monkeypatch.setattr(Authenticator, '_request_device_code', lambda self: {
        'device_auth_id': 'fixture-id', 'user_code': 'fixture-code', 'interval': '5'})
    result = execute({'operation': 'begin'})
    assert result['pending']['verification_url'] == VERIFICATION_URL
    assert result['pending']['user_code'] == 'fixture-code'
    assert not (tmp_path / 'auth.json').exists()
    assert callable(Authenticator._exchange_code_for_tokens)
    assert callable(Authenticator._build_auth_record)
    assert callable(Authenticator._login_device_code)


@pytest.mark.parametrize('status,header,expected', [(500, False, 401), (401, True, 401), (403, True, 403), (500, True, 500)])
def test_host_auth_errors_keep_status_without_exposing_credentials(status, header, expected):
    class HostAuthError(Exception):
        status_code = status
    records = []
    async def writer(record):
        records.append(record)
    route = metadata_only_route(APIRoute, writer, lambda request: '127.0.0.1', ['POST'], auth_exception=HostAuthError)
    router = APIRouter(route_class=route)
    @router.post('/auth')
    def auth():
        raise HostAuthError('private-token-must-not-appear')
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        result = client.post('/auth', headers={'Authorization': 'Bearer fixture'} if header else {})
    assert result.status_code == expected
    assert 'private-token-must-not-appear' not in result.text + json.dumps(records)


@pytest.mark.parametrize('tool,url,status,expected', [
    ('litellm', 'http://gateway:4000/health/liveliness', 200, 'reachable'),
    ('litellm', 'http://gateway:4000/health/liveliness', 503, 'failed'),
    ('structurizr', 'http://c4:8080/', 302, 'reachable'),
    ('structurizr', 'http://c4:8080/', 500, 'failed'),
])
def test_console_probe_checks_http_not_merely_installed_package(monkeypatch, tool, url, status, expected):
    async def get(self, actual):
        assert actual == url
        return httpx.Response(status)
    monkeypatch.setattr(httpx.AsyncClient, 'get', get)
    result = asyncio.run(probe(tool, Settings(_env_file=None, litellm_proxy_url='http://gateway:4000', structurizr_url='http://c4:8080')))
    assert result['status'] == expected


def test_tool_entrypoints_distinguish_consoles_embedded_and_external(db):
    service = ToolSettingsService(db, Settings(_env_file=None, coder_browser_url='https://ide.example.test'))
    for tool in ('langgraph', 'openspec', 'diagrams'):
        config = service.describe(tool, editable=True)
        assert config['access'] == 'embedded' and not config['web_url'] and not config['start_command']
    for tool in ('cube', 'serena', 'toolhive'):
        config = service.describe(tool, editable=True)
        assert config['access'] == 'external' and not config['web_url']
    for tool in ('litellm', 'coder', 'structurizr'):
        config = service.describe(tool, editable=True)
        assert config['access'] == 'console'
        assert '-f compose.tools.yaml' in config['start_command'] and config['start_command'].endswith('up -d ' + tool)
    assert service.describe('coder', editable=True)['web_url'] == 'https://ide.example.test'
