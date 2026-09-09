from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from ..config import Settings

READ_TOOLS = {"get_symbols_overview", "find_symbol", "search_for_pattern", "list_dir"}
TEMPLATE_PATHS = [
    "backend/app/__init__.py",
    "backend/app/modules/ai/chat/controller.py",
    "frontend/web/src/api/module_ai/chat.ts",
    "frontend/web/src/router/MenuProcessor.ts",
]


class SerenaClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def template_context(self) -> str:
        url = self.settings.serena_url
        if not url or urlparse(url).scheme not in {"http", "https"}:
            raise ValueError("Configure FACTORY_SERENA_URL to a ToolHive streamable-HTTP endpoint")
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        headers = ({"Authorization": "Bearer " + self.settings.serena_token} if self.settings.serena_token else None)
        chunks: list[str] = []
        async with asyncio.timeout(40):
            async with streamablehttp_client(url, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    names = {tool.name for tool in tools.tools}
                    selected = "get_symbols_overview"
                    if selected not in names or selected not in READ_TOOLS:
                        raise RuntimeError("Configured MCP server does not expose the expected read-only Serena tool")
                    for relative_path in TEMPLATE_PATHS:
                        result = await session.call_tool(selected, {"relative_path": relative_path, "depth": 1})
                        if result.isError:
                            raise RuntimeError(f"Serena symbol lookup failed for the pinned template path: {relative_path}")
                        text = "\n".join(getattr(part, "text", "") for part in result.content).strip()
                        chunks.append(f"# {relative_path}\n{text}")
        value = "\n\n".join(chunks)
        if not value.strip():
            raise RuntimeError("Serena returned an empty template context")
        return value[:16000]
