"""Generated business contract smoke test. SQLite is TEST ONLY, not the delivered DB.
This tests the trusted business runtime, not FastapiAdmin authentication or the Vue build.
"""
import json
import sys
from pathlib import Path
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool


def verify(root: Path) -> dict:
    sys.path.insert(0, str(root / 'backend'))
    from business_schema import ProjectSpec
    from business_runtime import build_metadata, create_business_router
    spec = ProjectSpec.model_validate_json((root / 'backend/business_spec.json').read_text())
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def foreign_keys(dbapi_connection, connection_record):
        dbapi_connection.execute('PRAGMA foreign_keys=ON')
    metadata = build_metadata(spec)
    metadata.create_all(engine)
    app = FastAPI()
    def actor(x_test_actor: str = Header('a')):
        return x_test_actor
    app.include_router(create_business_router(engine, spec, actor))
    ids = {}; payloads = {}; assertions = 0
    with TestClient(app) as client:
        for table in metadata.sorted_tables:
            name = table.name.removeprefix('biz_')
            entity = next(e for e in spec.entities if e.name == name)
            payload = {}
            for f in entity.fields:
                value = {'string':'example', 'text':'test content', 'integer':1, 'number':1.25,
                         'boolean':True,'date':'2026-09-08','datetime':'2026-09-08T12:00:00Z'}
                payload[f.name] = ids[f.references] if f.kind == 'reference' else value[f.kind]
            result = client.post('/business-api/' + name, json=payload)
            assert result.status_code == 201, result.text
            ids[name] = result.json()['id']; payloads[name] = payload; assertions += 1
            result = client.get('/business-api/' + name)
            assert result.status_code == 200 and result.json()['total'] == 1; assertions += 1
            other = client.get('/business-api/' + name, headers={'X-Test-Actor':'b'})
            assert other.json()['total'] == 0; assertions += 1
            assert client.patch(f'/business-api/{name}/{ids[name]}', json={}, headers={'X-Test-Actor':'b'}).status_code == 404; assertions += 1
            assert client.delete(f'/business-api/{name}/{ids[name]}', headers={'X-Test-Actor':'b'}).status_code == 404; assertions += 1
            assert client.post('/business-api/' + name, json=payload | {'owner_id':'b'}).status_code == 422; assertions += 1
            if any(f.kind == 'reference' for f in entity.fields):
                assert client.post('/business-api/' + name, json=payload, headers={'X-Test-Actor':'b'}).status_code == 422; assertions += 1
        for table in reversed(metadata.sorted_tables):
            name = table.name.removeprefix('biz_')
            assert client.delete(f'/business-api/{name}/{ids[name]}').status_code == 200; assertions += 1
    engine.dispose()
    return {'business_contract_sqlite': 'passed', 'assertions': assertions,
            'upstream_auth': 'not_run', 'postgres_integration': 'not_run', 'full_stack': 'not_run'}


if __name__ == '__main__':
    print(json.dumps(verify(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2))
