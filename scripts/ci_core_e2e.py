"""Disposable CI integration: genuine platform/Temporal/template, FIXTURE model HTTP.

Run only via compose.ci.yaml. This does not claim live paid-model, Cube, Serena or
Coder acceptance. Those are operator-run using scripts/smoke_e2e.py and full mode.
"""
from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4


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
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from factory.config import get_settings
    from factory.host import create_app
    from app.modules.system.user.model import UserModel
    from app.modules.system.log.model import OperationLogModel
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
            invalid_secret = "invalid-payload-sentinel-not-a-real-key"
            invalid = client.post("/api/v1/factory/providers", headers=headers,
                                  json={"api_key": invalid_secret, "provider": "not-a-provider"})
            require(invalid.status_code == 422 and invalid_secret not in invalid.text, "Validation response exposed input")
            api("POST", f'/providers/{provider["id"]}/test')
            with Session(engine) as session:
                audit = session.scalars(select(OperationLogModel).where(
                    OperationLogModel.request_path.like("%/factory/providers%"))).all()
                require(len(audit) >= 3, "Native operation logs were not persisted")
                serialized = json.dumps([{ "request": row.request_payload, "response": row.response_json } for row in audit])
                require(invalid_secret not in serialized and "ci-fixture-not-a-paid-credential" not in serialized,
                        "Provider credentials leaked into native operation logs")
            (reports / "credential-audit.json").write_text(json.dumps({"native_operation_log": "passed",
                "invalid_request_input": "not_logged", "provider_key": "not_logged", "records_checked": len(audit)}, indent=2))
            project = api("POST", "/projects", 201, json={"title": "CI 设备检修", "requirement": "设备台账与维护记录，每位用户仅管理自己的数据。"})
            run_body = {"provider_id": provider["id"], "provider": "litellm", "pipeline_mode": "core", "sandbox": "static",
                        "use_serena": False, "provision_coder": False, "idempotency_key": str(uuid4())}
            run_body["expected_revision"] = project["revision"]
            api("POST", f'/projects/{project["id"]}/runs', 409, json=run_body)
            project = api("POST", f'/projects/{project["id"]}/clarify', json={"provider_id": provider["id"]})
            require(project["clarification_status"] == "WAITING_USER", "Initial analysis did not ask for confirmation")
            api("POST", f'/projects/{project["id"]}/messages', json={"content": "确认上述范围。只需要 CRUD，不需要审批、采集或支付；用户数据隔离。"})
            project = api("POST", f'/projects/{project["id"]}/clarify', json={"provider_id": provider["id"]})
            require(project["clarification_status"] == "READY", "Answered requirement was not analyzed")
            # A second browser tab must not start a new analysis using an old revision.
            api("POST", f'/projects/{project["id"]}/runs', 409, json=run_body)
            run_body["expected_revision"] = project["revision"]
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
                archive = Path(directory) / "product.zip"
                archive.write_bytes(download.content)
                # Run the SAME baked, offline verifier used inside a full-mode Cube VM.
                # No operator DB credentials or model secrets are inherited by its children.
                subprocess.run([sys.executable, "/opt/rnd-verifier/full_stack.py", "--archive", str(archive),
                                "--sha256", finished["artifact_sha256"], "--report", str(reports / "product-stack.json")],
                               check=True, timeout=660)
            (reports / "coverage.json").write_text(json.dumps({"platform_api": "real_FastapiAdmin", "temporal": "real_service",
                "langgraph": "real_runtime", "litellm": "real_SDK_with_fixture_HTTP_not_live_AI", "openspec": "real_CLI",
                "diagrams": "real_renderer", "generated_template": "pinned_FastapiAdmin", "product_frontend_build": "passed",
                "offline_fullstack_verifier": "passed_in_disposable_container", "external_cube_coder_serena": "not_run", "structurizr_in_core_mode": "not_run", "production_ready": False}, indent=2))
            print("CI core flow and independent generated-product acceptance completed")
    finally:
        server.shutdown(); server.server_close(); engine.dispose()


if __name__ == "__main__":
    main()
