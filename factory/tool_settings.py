"""Administrator-owned integration settings consumed by both API and activities.

Only data fields are editable: no shell commands, Python callbacks or container
images. Temporal connection/worker settings remain startup configuration.
"""
from __future__ import annotations
import json
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .config import Settings
from .database import Database, ToolSetting
from .providers.registry import decrypt_secret, encrypt_secret

# Field tuples: settings key, label, input type. DB values override .env until reset.
TOOLS = {
    "fastapiadmin": ("https://fastapiadmin.com", "/api/v1/web/#/", [], "认证、权限与系统参数使用宿主管理页面；框架版本由模板 manifest 固定。"),
    "langgraph": ("https://docs.langchain.com/oss/python/langgraph/overview", "", [("model_timeout", "模型调用总超时（秒）", "number"), ("model_max_tokens", "默认最大输出 tokens", "number")], "进程内需求分析图；模型由模型配置页选择，无需另起 LangGraph 服务。"),
    "litellm": ("https://docs.litellm.ai/docs/", "http://localhost:4000/ui", [], "模型、凭据及 litellm_params 在模型配置页保存；全局网关预算/路由策略可进入 LiteLLM 原生管理台。"),
    "temporal": ("https://docs.temporal.io", "http://localhost:8233", [], "已预配 Compose Temporal。address/namespace/task_queue 属于 worker 启动参数，修改 .env 后重新创建 API/worker 容器；请先处理未完成任务。"),
    "openspec": ("https://github.com/Fission-AI/OpenSpec", "", [("openspec_required", "强制规格校验", "boolean")], "CLI 已装入镜像；完整模式始终要求验证回执。无需服务 URL。"),
    "diagrams": ("https://diagrams.mingrammer.com", "", [("diagrams_required", "强制生成部署图", "boolean")], "diagrams、Graphviz、字体由镜像预装。图文件可在运行详情预览。"),
    "structurizr": ("https://docs.structurizr.com", "http://localhost:8080", [("docker_host_data_dir", "Docker 宿主 data 绝对路径", "text")], "Compose architecture profile 提供浏览器；解析仍用固定镜像。worker 的 Docker socket 是高权限部署选项，不能由页面开启。"),
    "toolhive": ("https://docs.stacklok.com/toolhive", "", [], "ToolHive 代理进程由管理员部署；MCP 地址和令牌统一在 Serena 项目中配置，避免两份配置漂移。"),
    "serena": ("https://github.com/oraios/serena", "", [("serena_url", "ToolHive 管理的 Serena MCP URL", "url"), ("serena_token", "MCP Bearer Token", "secret")], "先运行 integrations/toolhive/prepare.sh 与 start.sh；容器访问宿主 loopback 的方式需按本机网络确认。"),
    "cube": ("https://github.com/TencentCloud/CubeSandbox", "", [("cube_api_url", "Cube API URL", "url"), ("cube_api_key", "Cube API Key", "secret"), ("cube_template", "全栈验收模板 ID", "text")], "需要真实 Cube 服务及带 envd 的全栈模板，不能自动在普通容器里创建 KVM。参见 integrations/cube/Dockerfile.fullstack。"),
    "coder": ("https://coder.com/docs", "http://localhost:7080", [("coder_url", "Coder API URL（服务器可达）", "url"), ("coder_token", "Coder Session Token", "secret"), ("coder_template_id", "自动源码导入模板 ID", "text"), ("coder_owner_id", "允许创建工作区的 FastapiAdmin 用户 ID", "text"), ("coder_auto_import", "验证源码自动导入", "boolean"), ("coder_factory_url", "工作区可达的平台根 URL", "url"), ("coder_import_timeout", "导入等待秒数", "number")], "先注册 integrations/coder 模板。平台会校验真实工作区与源码 SHA；填写设置不会自动产生费用或创建工作区。"),
}
SECRET_KEYS = {key for _,_,fields,_ in TOOLS.values() for key,_,kind in fields if kind == "secret"}
LIMITS = {"model_timeout": (10, 180), "model_max_tokens": (256, 128000), "coder_import_timeout": (30, 300)}


class ToolSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    values: dict[str, str | bool | int] = Field(default_factory=dict, max_length=20)


def check_url(value: str, *, browser: bool = False):
    if not value:
        return
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value) or "\\" in value:
        raise HTTPException(422, "服务地址不能包含空白、控制字符或反斜杠")
    try:
        parsed = urlsplit(value)
        parsed.port  # validate bracketed IPv6 and the port range before saving
    except ValueError:
        raise HTTPException(422, "服务地址格式或端口无效") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or (parsed.fragment and not browser):
        raise HTTPException(422, "服务地址必须是无内嵌凭据的 HTTP(S) URL")


class ToolSettingsService:
    def __init__(self, db: Database, defaults: Settings):
        self.db, self.defaults = db, defaults

    def _values(self, row: ToolSetting | None) -> dict:
        return json.loads(decrypt_secret(row.ciphertext, self.defaults)) if row else {}

    def _effective(self, rows: list[ToolSetting]) -> Settings:
        values = {}
        for row in rows:
            if row.id in TOOLS:
                allowed = {key for key, _, _ in TOOLS[row.id][2]}
                values.update({key: value for key, value in self._values(row).items() if key in allowed})
        return self.defaults.model_copy(update=values)

    def effective(self) -> Settings:
        with self.db.session() as session:
            return self._effective(list(session.scalars(select(ToolSetting))))

    def describe(self, tool: str, *, editable: bool) -> dict:
        if tool not in TOOLS:
            raise HTTPException(404, "Unknown integration")
        docs, web, fields, note = TOOLS[tool]
        # One SELECT: values and revision must be from the same DB snapshot.
        # Reading them separately lets a stale value acquire a newer revision.
        with self.db.session() as session:
            rows = list(session.scalars(select(ToolSetting)))
            settings = self._effective(rows)
            row = next((item for item in rows if item.id == tool), None)
            version = row.revision if row else 0
            stored = self._values(row)
            if "web_url" in stored:
                web = stored["web_url"]  # an explicit empty URL hides the link
            elif row and row.web_url:
                web = row.web_url  # compatibility with pre-reset-fix rows
        result = []
        for key, label, kind in fields:
            value = getattr(settings, key)
            result.append({"key": key, "label": label, "kind": kind,
                           "value": ("" if kind == "secret" else value) if editable else None,
                           "configured": bool(value), "minimum": LIMITS.get(key, (None,None))[0],
                           "maximum": LIMITS.get(key, (None,None))[1]})
        return {"id": tool, "docs": docs, "web_url": web, "note": note, "fields": result,
                "revision": version, "editable": editable, "requires_restart": tool == "temporal",
                "startup_values": {"temporal_address": settings.temporal_address, "temporal_namespace": settings.temporal_namespace,
                                   "task_queue": settings.task_queue} if tool == "temporal" and editable else {}}

    def save(self, tool: str, body: ToolSettingsInput) -> dict:
        if tool not in TOOLS:
            raise HTTPException(404, "Unknown integration")
        types = {key:kind for key,_,kind in TOOLS[tool][2]} | {"web_url": "url"}
        if any(key not in types for key in body.values):
            raise HTTPException(422, "Unknown or startup-only integration setting")
        for key, value in body.values.items():
            kind = types[key]
            if kind == "boolean" and type(value) is not bool:
                raise HTTPException(422, "Expected a boolean")
            if kind == "number" and (type(value) is not int or not LIMITS[key][0] <= value <= LIMITS[key][1]):
                raise HTTPException(422, "Number outside the supported range")
            if kind in {"text", "url", "secret"} and (not isinstance(value, str) or len(value) > (16000 if kind == "secret" else 1024)):
                raise HTTPException(422, "Invalid text field")
            if kind == "url":
                if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value) or "\\" in value:
                    raise HTTPException(422, "Invalid URL characters")
                # Relative same-origin routes are allowed only for browser navigation.
                if not (key == "web_url" and value.startswith("/") and not value.startswith("//")):
                    check_url(value, browser=key == "web_url")
            if key == "docker_host_data_dir" and value and (not value.startswith("/") or "," in value or ".." in value.split("/")):
                raise HTTPException(422, "Use an absolute Linux/WSL host path without '..' or commas")
        return self._write(tool, body.expected_revision, dict(body.values))

    def _write(self, tool: str, expected_revision: int, patch: dict, *, reset: bool = False) -> dict:
        if tool not in TOOLS:
            raise HTTPException(404, "Unknown integration")
        if type(expected_revision) is not int or expected_revision < 0:
            raise HTTPException(422, "Expected a nonnegative revision")
        conflict = "设置已被其他管理员修改，请刷新后重试"
        try:
            with self.db.session() as session:
                row = session.get(ToolSetting, tool)
                revision = row.revision if row else 0
                if revision != expected_revision:
                    raise HTTPException(409, conflict)
                values = {} if reset else self._values(row)
                if not reset:
                    values.update(patch)
                web_url = "" if reset else patch.get("web_url", row.web_url if row else "")
                encrypted = encrypt_secret(json.dumps(values), self.defaults)
                if row is None:
                    # A reset at revision zero also creates a tombstone. Never
                    # delete this row or recycle versions (the ABA problem).
                    session.add(ToolSetting(id=tool, revision=1, ciphertext=encrypted, web_url=web_url))
                else:
                    # SQL-level compare-and-swap works on PostgreSQL and SQLite.
                    # A SELECT FOR UPDATE alone is not portable to SQLite.
                    result = session.execute(update(ToolSetting).where(
                        ToolSetting.id == tool, ToolSetting.revision == expected_revision
                    ).values(revision=expected_revision + 1, ciphertext=encrypted, web_url=web_url),
                        execution_options={"synchronize_session": False})
                    if result.rowcount != 1:
                        raise HTTPException(409, conflict)
        except IntegrityError:
            raise HTTPException(409, conflict) from None
        return self.describe(tool, editable=True)

    def reset(self, tool: str, revision: int) -> dict:
        """Remove overrides and secrets, retaining a monotonically increasing version."""
        return self._write(tool, revision, {}, reset=True)
