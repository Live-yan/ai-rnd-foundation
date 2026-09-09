"""Disposable CI integration: genuine platform/Temporal/template, FIXTURE model HTTP.

Run only via compose.ci.yaml. This does not claim live paid-model, Cube, Serena or
Coder acceptance. Those are operator-run using scripts/smoke_e2e.py and full mode.
"""
from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4
from zipfile import ZipFile


def require(condition: bool, message: str):
    if not condition:
        raise RuntimeError(message)


class FixtureModel(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Do not log auth headers or prompts.

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        require(0 < length < 500000, "CI fixture request size")
        request = json.loads(self.rfile.read(length))
        payload = json.loads(request["messages"][-1]["content"])
        if "conversation" in payload:
            ready = payload["conversation"].count("USER:") >= 2
            result = {"ready": ready, "understanding": "设备与维护记录，各用户只管理自己的数据。",
                      "questions": [] if ready else ["请确认只需要设备和维护记录的 CRUD、每人数据隔离，无审批或实时采集。"],
                      "acceptance_criteria": ["登录用户可新增设备并记录维护", "另一用户不能读取、更新或删除前者数据"],
                      "assumptions": [], "risks": [], "suggested_stack": ["FastapiAdmin", "PostgreSQL"]}
        elif payload.get("task") == "provider connectivity test":
            result = {"ok": True}
        else:
            from factory.schemas import demo_spec
            result = demo_spec().model_dump()
        content = json.dumps({"id": "ci-fixture", "object": "chat.completion", "created": int(time.time()),
                              "model": request["model"], "choices": [{"index": 0, "finish_reason": "stop",
                                  "message": {"role": "assistant", "content": json.dumps(result, ensure_ascii=False)}}],
                              "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers(); self.wfile.write(content)


def main():
    require(os.environ.get("FACTORY_ACCEPTANCE_DISPOSABLE") == "1", "Only run against disposable CI services")
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from factory.config import get_settings
    from factory.host import create_app
    from app.modules.system.user.model import UserModel
    from app.utils.password_util import PwdUtil

    settings = get_settings()
    engine = create_engine(settings.database_url)
    app = create_app()
    server = ThreadingHTTPServer(("0.0.0.0", 9010), FixtureModel)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    reports = Path("/app/data/ci-reports")
    reports.mkdir(parents=True, exist_ok=True)
    try:
        with TestClient(app) as client:
            username, password = "ci_" + secrets.token_hex(6), secrets.token_urlsafe(24)
            with Session(engine) as session, session.begin():
                session.add(UserModel(username=username, name=username, password=PwdUtil.hash_password(password), status=0, is_superuser=True))
            response = client.post("/api/v1/system/auth/login", data={"username": username, "password": password})
            require(response.status_code == 200 and response.json().get("code") == 0, "Native platform login failed")
            headers = {"Authorization": "Bearer " + response.json()["data"]["access_token"]}
            def api(method, path, expected=200, **kwargs):
                result = client.request(method, "/api/v1/factory" + path, headers=headers, **kwargs)
                require(result.status_code == expected, f"{method} {path}: unexpected HTTP {result.status_code}")
                if expected in {200, 201, 202}:
                    require(result.json().get("code") == 0, "Native response envelope failed")
                    return result.json()["data"]
                return result
            provider = api("POST", "/providers", 201, json={"name": "CI fixture model", "provider": "custom_openai",
                "model": "fixture-planner", "api_key": "ci-fixture-not-a-paid-credential", "base_url": "http://acceptance:9010/v1", "is_default": True})
            api("POST", f'/providers/{provider["id"]}/test')
            project = api("POST", "/projects", 201, json={"title": "CI 设备检修", "requirement": "设备台账与维护记录，每位用户仅管理自己的数据。"})
            run_body = {"provider_id": provider["id"], "provider": "litellm", "pipeline_mode": "core", "sandbox": "static",
                        "use_serena": False, "provision_coder": False, "idempotency_key": str(uuid4())}
            api("POST", f'/projects/{project["id"]}/runs', 409, json=run_body)
            project = api("POST", f'/projects/{project["id"]}/clarify', json={"provider_id": provider["id"]})
            require(project["clarification_status"] == "WAITING_USER", "Initial analysis did not ask for confirmation")
            api("POST", f'/projects/{project["id"]}/messages', json={"content": "确认上述范围。只需要 CRUD，不需要审批、采集或支付；用户数据隔离。"})
            project = api("POST", f'/projects/{project["id"]}/clarify', json={"provider_id": provider["id"]})
            require(project["clarification_status"] == "READY", "Answered requirement was not analyzed")
            run = api("POST", f'/projects/{project["id"]}/runs', 202, json=run_body)
            def wait_for(status):
                deadline = time.monotonic() + 300
                while time.monotonic() < deadline:
                    value = api("GET", f'/runs/{run["id"]}')
                    require(value["status"] not in {"FAILED", "REJECTED"}, "Pipeline failed: " + str(value.get("error")))
                    if value["status"] == status:
                        return value
                    time.sleep(1)
                raise RuntimeError("Temporal pipeline did not reach " + status)
            waiting = wait_for("AWAITING_APPROVAL")
            artifacts = api("GET", f'/runs/{run["id"]}/analysis')
            require("architecture/er.svg" in artifacts and "openspec/changes/create-product/requirements.md" in artifacts, "Actual review artifacts missing")
            approval = {"spec_digest": waiting["spec_digest"], "approve": True, "accept_limitations": True}
            api("POST", f'/runs/{run["id"]}/decision', 409, json=approval | {"spec_digest": "0" * 64})
            api("POST", f'/runs/{run["id"]}/decision', json=approval)
            finished = wait_for("READY")
            download = client.get(f'/api/v1/factory/runs/{run["id"]}/download', headers=headers)
            require(download.status_code == 200, "Source download failed")
            require(hashlib.sha256(download.content).hexdigest() == finished["artifact_sha256"], "ZIP digest mismatch")
            (reports / "platform-run.json").write_text(json.dumps(finished, ensure_ascii=False, indent=2))
            with tempfile.TemporaryDirectory(prefix="rnd-acceptance-") as directory:
                product = Path(directory) / "product"
                # Our own archive was just hash-checked; still use the bounded safe importer.
                from integrations.coder.import_source import extract_verified
                archive = Path(directory) / "product.zip"
                archive.write_bytes(download.content)
                extract_verified(archive, product, finished["artifact_sha256"])
                frontend = product / "frontend/web"
                (frontend / "node_modules").symlink_to("/opt/rnd-node/node_modules", target_is_directory=True)
                (frontend / ".env.production").write_text("VITE_APP_ENV=prod\nVITE_ACCESS_MODE=mixed\nVITE_BASE_URL=/api/v1/web/\nVITE_APP_BASE_API=/api/v1\n")
                subprocess.run(["pnpm", "exec", "vite", "build", "--mode", "production"], cwd=frontend, check=True, timeout=180)
                subprocess.run(["pnpm", "exec", "vue-tsc", "--noEmit"], cwd=frontend, check=True, timeout=120)
                shutil.copytree(frontend / "dist", product / "backend/dist")
                # Separate new database; never drop, reset or reuse an operator's product database.
                database = "rnd_acceptance_" + secrets.token_hex(6)
                with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                    connection.execute(text(f'CREATE DATABASE "{database}"'))
                env = dict(os.environ, DATABASE_NAME=database, SECRET_KEY=secrets.token_hex(48))
                # Product imports must come from the delivered ZIP, not the platform host.
                env.pop("PYTHONPATH", None)
                subprocess.run([sys.executable, "/app/scripts/verify_delivery_stack.py", str(product),
                                "--report", str(reports / "product-stack.json")], env=env, check=True, timeout=180)
            (reports / "coverage.json").write_text(json.dumps({"platform_api": "real_FastapiAdmin", "temporal": "real_service",
                "langgraph": "real_runtime", "litellm": "real_SDK_with_fixture_HTTP_not_live_AI", "openspec": "real_CLI",
                "diagrams": "real_renderer", "generated_template": "pinned_FastapiAdmin", "product_frontend_build": "passed",
                "external_cube_coder_serena": "not_run", "structurizr_in_core_mode": "not_run", "production_ready": False}, indent=2))
            print("CI core flow and independent generated-product acceptance completed")
    finally:
        server.shutdown(); server.server_close(); engine.dispose()


if __name__ == "__main__":
    main()
