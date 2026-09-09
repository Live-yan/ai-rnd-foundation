from __future__ import annotations

import asyncio
import time
from urllib.parse import quote, urlsplit

import httpx

from ..config import Settings


class CoderClient:
    def __init__(self, settings: Settings, transport=None):
        self.settings, self.transport = settings, transport

    @staticmethod
    def imported(data: dict, sha: str) -> bool:
        build = data.get("latest_build") or {}
        if build.get("status") != "running":
            return False
        for resource in build.get("resources", []):
            for agent in resource.get("agents", []):
                if agent.get("status") != "connected":
                    continue
                for item in agent.get("metadata", []):
                    result = item.get("result") or {}
                    if ((item.get("description") or {}).get("key") == "rnd_source_sha256"
                            and not result.get("error") and str(result.get("value", "")).strip() == sha):
                        return True
        return False

    async def create_workspace(self, run_id: str, *, source: dict | None = None) -> dict:
        s = self.settings
        if not all([s.coder_url, s.coder_token, s.coder_template_id]):
            raise ValueError("Configure Coder URL, session token and an administrator-tested template ID")
        parsed = urlsplit(s.coder_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Invalid Coder URL")
        name = "rnd-" + run_id.replace("-", "")[:24]
        headers = {"Coder-Session-Token": s.coder_token}
        async with httpx.AsyncClient(base_url=s.coder_url.rstrip("/"), timeout=45,
                                     transport=self.transport, follow_redirects=False) as client:
            async def request(method: str, path: str, **kwargs) -> httpx.Response:
                response = await client.request(method, path, headers=headers, **kwargs)
                return response

            lookup = "/api/v2/users/me/workspace/" + quote(name, safe="")
            data = None
            if source:
                response = await request("GET", lookup)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("template_id") != s.coder_template_id:
                        raise RuntimeError("Existing workspace uses a different template; refusing to reuse")
                elif response.status_code != 404:
                    raise RuntimeError(f"Coder workspace lookup returned HTTP {response.status_code}")
            if data is None:
                body = {"name": name, "template_id": s.coder_template_id}
                if source:
                    body["rich_parameter_values"] = [
                        {"name": "rnd_source_url", "value": source["url"]},
                        {"name": "rnd_source_token", "value": source["token"]},
                        {"name": "rnd_source_sha256", "value": source["sha256"]},
                    ]
                response = await request("POST", "/api/v2/users/me/workspaces", json=body)
                # A lost response/retry must not create a second workspace.
                if response.status_code == 409 and source:
                    response = await request("GET", lookup)
                if response.status_code >= 400:
                    raise RuntimeError(f"Coder workspace creation returned HTTP {response.status_code}")
                data = response.json()
            result = {
                "workspace_id": data["id"], "name": data.get("name", name),
                "url": s.coder_url.rstrip("/") + "/@" + quote(data["owner_name"], safe="") + "/" + quote(data.get("name", name), safe=""),
                "source_import": "manual_zip_upload", "readiness": "created_not_build_verified",
            }
            if not source:
                result["instruction"] = "此兼容操作只创建工作区。完整流水线使用自动源码导入模板。"
                return result
            deadline = time.monotonic() + s.coder_import_timeout
            while True:
                # The single-workspace endpoint does not populate agent metadata.
                # Explicitly expand the receipt on the list API, then match the exact ID.
                response = await request("GET", "/api/v2/workspaces", params={
                    "q": f"owner:me name:{name} include_agent_metadata:rnd_source_sha256", "limit": 100,
                })
                if response.status_code != 200:
                    raise RuntimeError(f"Coder metadata lookup returned HTTP {response.status_code}; verify server support for include_agent_metadata")
                matches = [item for item in response.json().get("workspaces", []) if item.get("id") == data["id"]]
                if len(matches) != 1:
                    raise RuntimeError("Coder metadata lookup did not return the requested workspace")
                data = matches[0]
                if data.get("template_id") != s.coder_template_id:
                    raise RuntimeError("Coder workspace template mismatch")
                if self.imported(data, source["sha256"]):
                    return result | {"source_import": "sha256_verified", "readiness": "running_source_imported",
                                     "source_sha256": source["sha256"], "business_acceptance": "see_quality_report"}
                state = (data.get("latest_build") or {}).get("status")
                if state in {"failed", "canceled", "deleted", "stopped"}:
                    raise RuntimeError(f"Coder workspace stopped in state {state}")
                if time.monotonic() >= deadline:
                    raise RuntimeError("Coder import was not confirmed before timeout; inspect workspace startup logs and rnd_source_sha256 metadata")
                await asyncio.sleep(2)
                response = await request("GET", "/api/v2/workspaces/" + quote(str(data["id"]), safe=""))
                if response.status_code != 200:
                    raise RuntimeError(f"Coder readiness check returned HTTP {response.status_code}")
                data = response.json()
