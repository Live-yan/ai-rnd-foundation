"""Verify a GENERATED product against disposable PostgreSQL/Redis and its built UI.

This command is intentionally not a production startup command. It creates two
throwaway users in a NEW test database and runs the genuine FastapiAdmin auth
stack. No dependency override or test identity header is accepted by the product.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys


def verify(root: Path) -> dict:
    if os.environ.get("FACTORY_ACCEPTANCE_DISPOSABLE") != "1" or not os.environ.get("DATABASE_NAME", "").startswith("rnd_acceptance_"):
        raise RuntimeError("Use a disposable rnd_acceptance_* database and FACTORY_ACCEPTANCE_DISPOSABLE=1")
    backend = root / "backend"
    sys.path.insert(0, str(backend))
    os.chdir(backend)
    # Test configuration is process-local; delivered source configuration stays unchanged.
    os.environ.update(ENVIRONMENT="dev", CAPTCHA_ENABLE="False", IP_LOCATION_ENABLE="False",
                      DEMO_ENABLE="False", DEBUG="False", SCHEDULER_ALLOW_CODE_EXEC="False")
    subprocess.run([sys.executable, "-m", "alembic", "-c", "business-alembic.ini", "upgrade", "head"], check=True, timeout=60)
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from delivery_db import make_engine
    from delivery_entry import create_app
    from business_runtime import build_metadata
    from business_schema import ProjectSpec
    from app.modules.system.user.model import UserModel
    from app.utils.password_util import PwdUtil

    spec = ProjectSpec.model_validate_json((backend / "business_spec.json").read_text())
    engine = make_engine()
    users = [("rnd_" + secrets.token_hex(6), secrets.token_urlsafe(24)) for _ in range(2)]
    assertions = 0
    app = create_app()
    with TestClient(app) as client:
        with Session(engine) as session, session.begin():
            for username, password in users:
                session.add(UserModel(username=username, name=username, password=PwdUtil.hash_password(password), status=0, is_superuser=True))
        headers = []
        for username, password in users:
            response = client.post("/api/v1/system/auth/login", data={"username": username, "password": password})
            assert response.status_code == 200, "Native login HTTP status"
            data = response.json()
            assert data["code"] == 0 and data["data"]["access_token"], "Native login result"
            headers.append({"Authorization": "Bearer " + data["data"]["access_token"]})
            assertions += 1
        assert client.get("/api/v1/web/").status_code == 200, "Built frontend is not mounted"
        assertions += 1
        metadata = build_metadata(spec)
        ids = {}
        for table in metadata.sorted_tables:
            name = table.name.removeprefix("biz_")
            entity = next(e for e in spec.entities if e.name == name)
            path = "/api/v1/business-api/" + name
            payload = {}
            examples = {"string": "acceptance", "text": "test notes", "integer": 1, "number": 1.5,
                        "boolean": True, "date": "2026-09-09", "datetime": "2026-09-09T00:00:00Z"}
            for field in entity.fields:
                payload[field.name] = ids[field.references] if field.kind == "reference" else examples[field.kind]
            assert client.get(path).status_code == 401, "Business endpoint accepted unauthenticated access"
            response = client.post(path, json=payload, headers=headers[0])
            assert response.status_code == 201, "Authenticated create failed"
            ids[name] = response.json()["id"]
            assert client.get(path, headers=headers[0]).json()["total"] == 1
            assert client.get(path, headers=headers[1]).json()["total"] == 0
            assert client.patch(f"{path}/{ids[name]}", json={}, headers=headers[1]).status_code == 404
            assert client.delete(f"{path}/{ids[name]}", headers=headers[1]).status_code == 404
            assert client.post(path, json=payload | {"owner_id": "forged"}, headers=headers[0]).status_code == 422
            with engine.connect() as connection:
                assert connection.execute(select(table.c.id).where(table.c.id == ids[name])).scalar_one() == ids[name]
            assertions += 8
            if any(f.kind == "reference" for f in entity.fields):
                assert client.post(path, json=payload, headers=headers[1]).status_code == 422
                assertions += 1
        for table in reversed(metadata.sorted_tables):
            name = table.name.removeprefix("biz_")
            assert client.delete(f"/api/v1/business-api/{name}/{ids[name]}", headers=headers[0]).status_code == 200
            assertions += 1
    engine.dispose()
    return {"postgres_integration": "passed", "upstream_auth": "passed", "redis_sessions": "passed",
            "business_owner_isolation": "passed", "frontend_mount": "passed", "assertions": assertions,
            "transport": "genuine_ASGI_TestClient", "browser_interactions": "not_run", "production_ready": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report_path = args.report.resolve()
    result = verify(args.product.resolve())
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print("Generated product: genuine PostgreSQL, Redis and FastapiAdmin authentication checks passed")
