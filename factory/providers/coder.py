from __future__ import annotations

import httpx
from ..config import Settings


class CoderClient:
    def __init__(self, settings: Settings, transport=None):
        self.settings, self.transport = settings, transport

    async def create_workspace(self, run_id: str) -> dict:
        s = self.settings
        if not all([s.coder_url, s.coder_token, s.coder_template_id]):
            raise ValueError("Configure Coder URL, session token and an administrator-tested template ID")
        async with httpx.AsyncClient(base_url=s.coder_url.rstrip("/"), timeout=45,
                                     transport=self.transport, follow_redirects=False) as client:
            name = "rnd-" + run_id.replace("-", "")[:16]
            response = await client.post("/api/v2/users/me/workspaces",
                                         headers={"Coder-Session-Token": s.coder_token},
                                         json={"name": name, "template_id": s.coder_template_id})
            if response.status_code >= 400:
                raise RuntimeError(f"Coder workspace creation returned HTTP {response.status_code}")
            data = response.json()
            return {"workspace_id": data["id"], "name": data.get("name", name),
                    "url": s.coder_url.rstrip("/") + "/@" + data["owner_name"] + "/" + data.get("name", name),
                    "source_import": "manual_zip_upload", "readiness": "created_not_build_verified",
                    "instruction": "打开 Coder，上传已下载源码 ZIP 并解压；本版本不会把平台令牌交给工作区。"}
