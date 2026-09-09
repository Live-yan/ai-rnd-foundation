from pathlib import Path
import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from factory.config import Settings
from factory.database import Database
from factory.api import create_router
from factory.schemas import demo_spec
from factory.product_runtime import build_metadata, create_business_router


@pytest.fixture
def db():
    db = Database('sqlite:///:memory:',test_only=True)
    db.initialize_for_tests()
    yield db
    db.engine.dispose()


@pytest.fixture
def fake_upstream(tmp_path):
    """MINIMAL TEST FIXTURE, not the actual upstream and never shipped as a runnable template."""
    root = tmp_path / 'fixture-upstream'
    values = {'LICENSE':'TEST FIXTURE ONLY - NOT FASTAPIADMIN SOURCE\n',
              'backend/app/__init__.py':'def create_app():\n    raise RuntimeError("test fixture only")\n',
              'backend/pyproject.toml':'[project]\nname="test-fixture"\nversion="0.0.0"\nrequires-python=">=3.12"\ndependencies=[]\n',
              'frontend/web/src/router/index.ts':'export const router = {addRoute: (value: unknown) => value};\n',
              'frontend/web/src/router/MenuProcessor.ts':'import type { AppRouteRecord } from "@/types/router";\nexport const builtinFrontendRoutes: AppRouteRecord[] = [];\n',
              'frontend/web/package.json':'{"name":"test-fixture","version":"0.0.0"}\n'}
    for name,text in values.items():
        path = root / name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text)
    return root


@pytest.fixture
def platform(db,tmp_path,fake_upstream):
    settings = Settings(_env_file=None,data_dir=tmp_path / 'data',upstream_dir=fake_upstream,
                        openspec_required=False,diagrams_required=False)
    settings.ensure_paths()
    app = FastAPI()
    def actor(x_actor: str | None = Header(None)):
        if not x_actor:
            raise HTTPException(401,'unit-test identity header required')
        return x_actor
    app.include_router(create_router(db,settings,actor))
    with TestClient(app) as client:
        yield client,settings


@pytest.fixture
def business():
    spec = demo_spec()
    engine = create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    @event.listens_for(engine,'connect')
    def fk(connection,record):
        connection.execute('PRAGMA foreign_keys=ON')
    build_metadata(spec).create_all(engine)
    app = FastAPI()
    def actor(x_actor: str = Header('a')):
        return x_actor
    app.include_router(create_business_router(engine,spec,actor))
    with TestClient(app) as client:
        yield client
    engine.dispose()
