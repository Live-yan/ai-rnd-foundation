"""Operator acceptance using a real signed-in user's provider and the native API.

Set FACTORY_USER_JWT locally (never commit it). Unlike the legacy smoke script,
this tool does not manufacture a fixed demo specification or bypass clarification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--requirement", type=Path, required=True)
    parser.add_argument("--answers", type=Path, help="Optional JSON array of answers; otherwise ask in the terminal")
    parser.add_argument("--full", action="store_true", help="Require all integrations, including Cube and verified Coder import")
    parser.add_argument("--approve", action="store_true", help="Explicitly approve the displayed specification")
    parser.add_argument("--accept-limitations", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("data/operator-acceptance"))
    args = parser.parse_args()
    token = os.environ.get("FACTORY_USER_JWT", "")
    if not token:
        raise SystemExit("Set FACTORY_USER_JWT to your local FastapiAdmin login JWT; do not paste it into an issue")
    answers = iter(json.loads(args.answers.read_text(encoding="utf-8"))) if args.answers else None
    with httpx.Client(base_url=args.base_url.rstrip("/") + "/api/v1/factory/", timeout=210,
                      headers={"Authorization": "Bearer " + token}, follow_redirects=False) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.status_code >= 400:
                raise RuntimeError(f"{method} {path}: HTTP {response.status_code}; inspect the workbench error and worker logs")
            data = response.json()
            if data.get("code") != 0:
                raise RuntimeError(f"{method} {path}: platform rejected the operation")
            return data["data"]
        project = request("POST", "projects", json={"title": "Operator acceptance", "requirement": args.requirement.read_text(encoding="utf-8")})
        for _ in range(12):
            project = request("POST", f'projects/{project["id"]}/clarify', json={"provider_id": args.provider_id})
            print(json.dumps(project["clarification"], ensure_ascii=False, indent=2))
            if project["clarification_status"] == "READY":
                break
            answer = next(answers, None) if answers is not None else input("请回答以上问题：\n")
            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError("An actual user answer is required; continue this project in the workbench")
            request("POST", f'projects/{project["id"]}/messages', json={"content": answer})
        else:
            raise RuntimeError("Clarification remains unresolved; no generation task was created")
        body = {"expected_revision": project["revision"], "provider_id": args.provider_id, "provider": "litellm", "idempotency_key": str(uuid4()),
                "pipeline_mode": "full" if args.full else "core", "sandbox": "cube" if args.full else "static",
                "use_serena": args.full, "provision_coder": args.full}
        run = request("POST", f'projects/{project["id"]}/runs', json=body)
        deadline = time.monotonic() + 1800
        approved = False
        while time.monotonic() < deadline:
            run = request("GET", f'runs/{run["id"]}')
            if run["status"] in {"FAILED", "REJECTED", "CANCELLED"}:
                raise RuntimeError("Run did not complete: " + str(run.get("error") or run["status"]))
            if run["status"] == "AWAITING_APPROVAL" and not approved:
                print(json.dumps(run["spec"], ensure_ascii=False, indent=2))
                if not args.approve:
                    raise RuntimeError("Awaiting approval. Review this run in the UI, or explicitly invoke with --approve for a new acceptance run")
                request("POST", f'runs/{run["id"]}/decision', json={"spec_digest": run["spec_digest"], "approve": True,
                        "accept_limitations": args.accept_limitations})
                approved = True
            if run["status"] == "READY":
                break
            time.sleep(2)
        else:
            raise RuntimeError("Run is still pending; its durable state remains available in the workbench")
        response = client.get(f'runs/{run["id"]}/download')
        response.raise_for_status()
        sha = hashlib.sha256(response.content).hexdigest()
        if sha != run["artifact_sha256"]:
            raise RuntimeError("Downloaded source archive failed integrity verification")
        if args.full:
            checks, stages = run["checks"], run["stage_details"]
            if not (checks.get("full_stack") == "passed" and checks.get("frontend_build") == "passed"
                    and checks["sandbox"].get("scope") == "generated_crud_stack"
                    and stages["context"].get("used") and stages["architecture"].get("c4_dsl") == "parser_validated"
                    and checks["sandbox"].get("provider") == "cube"
                    and checks["coder"].get("source_import") == "sha256_verified"
                    and checks["coder"].get("source_sha256") == sha):
                raise RuntimeError("Full toolchain receipt is incomplete")
        output = args.output / run["id"]
        output.mkdir(parents=True, exist_ok=False)
        (output / "product.zip").write_bytes(response.content)
        (output / "run-receipt.json").write_text(json.dumps(run, ensure_ascii=False, indent=2))
        (output / "events.json").write_text(json.dumps(request("GET", f'runs/{run["id"]}/events'), ensure_ascii=False, indent=2))
        print(f"Verified delivery written to {output}. Review full_stack and production_ready separately.")


if __name__ == "__main__":
    main()
