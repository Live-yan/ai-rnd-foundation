from __future__ import annotations

import asyncio
from urllib.parse import urlparse
from ..config import Settings

READ_TOOLS = {"get_symbols_overview", "find_symbol", "search_for_pattern", "list_dir"}


class SerenaClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def template_context(self) -> str:
        """The configured server MUST be read-only and scoped to the Golden Template, not all workspaces."""
        url = self.settings.serena_url
        if not url or urlparse(url).scheme not in {"http", "https"}:
            raise ValueError("Configure FACTORY_SERENA_URL to a ToolHive streamable-HTTP endpoint")
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        headers = ({"Authorization": "Bearer " + self.settings.serena_token}
                   if self.settings.serena_token else None)
        async with asyncio.timeout(30):
            async with streamablehttp_client(url, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    names = {tool.name for tool in tools.tools}
                    selected = "get_symbols_overview"
                    if selected not in names or selected not in READ_TOOLS:
                        raise RuntimeError("Configured MCP server does not expose the expected read-only Serena tool")
                    result = await session.call_tool(selected, {"relative_path": "backend/app/__init__.py", "depth": 1})
                    if result.isError:
                        raise RuntimeError("Serena tool call failed; verify project scope and Python language server")
                    return "\n".join(getattr(part, "text", "") for part in result.content)[:16000]
