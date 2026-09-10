"""Run the same storage contracts on SQLite and a disposable PostgreSQL schema.

Set FACTORY_TEST_POSTGRES_URL explicitly for PostgreSQL. No production tables are
created or dropped: each test owns a randomly named, isolated schema.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from threading import Barrier
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, text

from factory.api import create_router
from factory.config import Settings
from factory.database import Database, ToolSetting
from factory.providers.registry import decrypt_secret
from factory.tool_settings import ToolSettingsInput, ToolSettingsService


@pytest.fixture(params=['sqlite', 'postgres'])
def storage(request, tmp_path):
    if request.param == 'sqlite':
        db = Database('sqlite:///' + str(tmp_path / 'settings.db'), test_only=True)
        ToolSetting.__table__.create(db.engine)
        yield db
        db.engine.dispose()
        return
    url = os.environ.get('FACTORY_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('PostgreSQL test service not configured; CI must provide it')
    schema = 'rnd_test_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    db = Database(url)
    db.engine.update_execution_options(schema_translate_map={None: schema})
    try:
        ToolSetting.__table__.create(db.engine)
        yield db
    finally:
        db.engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


@pytest.fixture
def service(storage):
    return ToolSettingsService(storage, Settings(_env_file=None,
        credential_encryption_key='settings-test-only-' * 4, cube_api_key='environment-fixture-key'))


def save(service, revision, values=None):
    return service.save('cube', ToolSettingsInput(expected_revision=revision,
        values=values or {'cube_template': 'fixture-template'}))


def test_reset_removes_overrides_without_recycling_versions(storage, service):
    first = save(service, 0, {'cube_api_key': 'private-fixture-key', 'cube_template': 'fixture-template'})
    assert first['revision'] == 1 and service.effective().cube_api_key == 'private-fixture-key'
    reset = service.reset('cube', 1)
    assert reset['revision'] == 2
    assert service.effective().cube_api_key == 'environment-fixture-key'
    assert service.effective().cube_template == ''
    with storage.session() as session:
        row = session.get(ToolSetting, 'cube')
        assert row.revision == 2
        assert json.loads(decrypt_secret(row.ciphertext, service.defaults)) == {}
    for revision in (0, 1):
        with pytest.raises(HTTPException) as conflict:
            save(service, revision)
        assert conflict.value.status_code == 409
        with pytest.raises(HTTPException) as conflict:
            service.reset('cube', revision)
        assert conflict.value.status_code == 409
    assert save(service, 2)['revision'] == 3
    assert service.reset('cube', 3)['revision'] == 4


def test_reset_before_first_save_creates_tombstone(service):
    assert service.reset('cube', 0)['revision'] == 1
    with pytest.raises(HTTPException) as conflict:
        save(service, 0)
    assert conflict.value.status_code == 409


@pytest.mark.parametrize('initial', [False, True])
@pytest.mark.parametrize('actions', [('save', 'save'), ('save', 'reset'), ('reset', 'reset')])
def test_concurrent_writers_have_exactly_one_winner(service, initial, actions):
    revision = save(service, 0)['revision'] if initial else 0
    gate = Barrier(2)
    def writer(action):
        gate.wait(timeout=10)
        try:
            if action == 'save':
                save(service, revision)
            else:
                service.reset('cube', revision)
            return 200
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(writer, actions))
    assert sorted(statuses) == [200, 409]
    assert service.describe('cube', editable=True)['revision'] == revision + 1


def test_configuration_value_and_revision_are_read_together(storage, service):
    save(service, 0)
    statements = []
    def record(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)
    event.listen(storage.engine, 'before_cursor_execute', record)
    try:
        assert service.describe('cube', editable=True)['revision'] == 1
        assert len(statements) == 1
    finally:
        event.remove(storage.engine, 'before_cursor_execute', record)


def test_clear_browser_link_is_distinct_from_reset(service):
    result = service.save('coder', ToolSettingsInput(expected_revision=0, values={'web_url': ''}))
    assert result['web_url'] == ''
    assert service.reset('coder', result['revision'])['web_url'] == 'http://localhost:7080'


@pytest.mark.parametrize('url', ['/\\host', 'http://host/\npath', '//host/path', 'http://user:pass@host', 'http://[broken', 'http://host:99999'])
def test_unsafe_browser_url_is_rejected(service, url):
    with pytest.raises(HTTPException) as invalid:
        service.save('cube', ToolSettingsInput(expected_revision=0, values={'web_url': url}))
    assert invalid.value.status_code == 422


def test_unknown_tool_and_invalid_reset_revision(service):
    with pytest.raises(HTTPException) as missing:
        service.reset('no-such-tool', 0)
    assert missing.value.status_code == 404
    with pytest.raises(HTTPException) as invalid:
        service.reset('cube', -1)
    assert invalid.value.status_code == 422


def test_non_admin_cannot_reset_or_read_secret_fields(storage, service):
    save(service, 0, {'cube_api_key': 'private-fixture-key'})
    app = FastAPI()
    app.include_router(create_router(storage, service.defaults, lambda: 'reader', admin_dependency=lambda: False))
    with TestClient(app) as client:
        assert client.delete('/factory/toolchain/cube/config?revision=1').status_code == 403
        result = client.get('/factory/toolchain/cube/config').json()['data']
        assert result['editable'] is False
        assert all(field['value'] is None for field in result['fields'])
        assert 'private-fixture-key' not in json.dumps(result)
