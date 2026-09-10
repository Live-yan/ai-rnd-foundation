from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from ..config import Settings

TEMPLATE_PATHS = [
    "backend/app/__init__.py",
    "backend/app/modules/ai/chat/controller.py",
    "backend/app/modules/system/user/model.py",
    "backend/app/modules/system/role/service.py",
]


@asynccontextmanager
async def mcp_session(url: str, token: str):
    if not url or urlparse(url).scheme not in {"http", "https"}:
        raise ValueError("Configure an HTTP(S) MCP endpoint")
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    headers = {"Authorization": "Bearer " + token} if token else None
    async with asyncio.timeout(40):
        async with streamablehttp_client(url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def validate_c4(settings: Settings, dsl: str) -> dict:
    async with mcp_session(settings.structurizr_mcp_url, settings.structurizr_mcp_token) as session:
        names = {tool.name for tool in (await session.list_tools()).tools}
        name = "structurizr-validate" if "structurizr-validate" in names else "validate"
        if name not in names:
            raise RuntimeError("Configured MCP server does not expose Structurizr validate")
        result = await session.call_tool(name, {"dsl": dsl})
        text = "\n".join(getattr(part, "text", "") for part in result.content).strip()
        # Structurizr also returns parser errors as text with isError=false.
        if result.isError or text != "OK":
            raise RuntimeError("Structurizr MCP rejected the generated DSL")
        return {"tool": "structurizr", "validated": True, "transport": "mcp", "output": text}


class SerenaClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def template_context(self) -> str:
        chunks: list[str] = []
        async with mcp_session(self.settings.serena_url, self.settings.serena_token) as session:
            names = {tool.name for tool in (await session.list_tools()).tools}
            selected = "serena-get_symbols_overview" if "serena-get_symbols_overview" in names else "get_symbols_overview"
            if selected not in names:
                raise RuntimeError("Configured MCP server does not expose the expected read-only Serena tool")
            for relative_path in TEMPLATE_PATHS:
                result = await session.call_tool(selected, {"relative_path": relative_path, "depth": 1})
                if result.isError:
                    raise RuntimeError(f"Serena symbol lookup failed for the pinned template path: {relative_path}")
                text = "\n".join(getattr(part, "text", "") for part in result.content).strip()
                if not text or text in {"[]", "{}"}:
                    raise RuntimeError(f"Serena returned no symbols for {relative_path}")
                chunks.append(f"# {relative_path}\n{text}")
        value = "\n\n".join(chunks)
        if not value.strip():
            raise RuntimeError("Serena returned an empty template context")
        return value[:16000]
