"""Read-only, bounded diagnostics. A probe is not a full workflow receipt."""
import importlib.util
import os
import shutil
import subprocess

import httpx
from starlette.concurrency import run_in_threadpool
from .config import Settings


async def probe(tool: str, settings: Settings) -> dict:
    try:
        if tool in {"fastapiadmin", "langgraph", "litellm", "diagrams", "openspec", "structurizr"}:
            modules = {"langgraph": "langgraph", "litellm": "litellm", "diagrams": "diagrams"}
            commands = {"openspec": "openspec", "diagrams": "dot", "structurizr": "docker"}
            if tool in modules and importlib.util.find_spec(modules[tool]) is None:
                raise RuntimeError("Package missing")
            if tool == "fastapiadmin" and not settings.upstream_dir.joinpath("LICENSE").is_file():
                raise RuntimeError("Template missing")
            if tool in commands:
                binary = shutil.which(commands[tool])
                if not binary:
                    raise RuntimeError("Executable missing")
                result = await run_in_threadpool(subprocess.run, [binary, "-V" if tool == "diagrams" else "--version"],
                    capture_output=True, timeout=15, env={"PATH": os.environ.get("PATH", ""), "CI": "1", "OPENSPEC_TELEMETRY": "0", "HOME": "/tmp"})
                if result.returncode:
                    raise RuntimeError("Version check failed")
            return {"status": "local_ready", "message": "本地依赖可用；远端连接、模型权限与运行级回执仍在实际任务中验证。"}
        if tool in {"toolhive", "serena"}:
            from .providers.mcp import SerenaClient
            context = await SerenaClient(settings).template_context()
            return {"status": "reachable", "message": f"MCP 模板符号读取完成（{len(context)} 字符）；请确保该端点由 ToolHive 管理。"}
        if tool == "temporal":
            from temporalio.client import Client
            from temporalio.api.workflowservice.v1 import GetSystemInfoRequest
            import asyncio
            async with asyncio.timeout(15):
                client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
                await client.workflow_service.get_system_info(GetSystemInfoRequest())
            return {"status": "reachable", "message": "Temporal 服务连接成功；worker 队列执行在运行日志中确认。"}
        if tool == "coder":
            if not settings.coder_url:
                raise RuntimeError("URL missing")
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                response = await client.get(settings.coder_url.rstrip("/") + "/api/v2/buildinfo")
                if response.status_code != 200:
                    raise RuntimeError("Server unavailable")
            return {"status": "reachable", "message": "Coder 服务可达；本次没有创建工作区，模板和源码导入仍需完整任务验证。"}
        return {"status": "requires_run", "message": "Cube 模板需要在完整流程中创建实际沙箱验证；本次不会偷偷创建可能计费的资源。"}
    except Exception:
        return {"status": "failed", "message": "检查未通过。请核对已保存配置、组件部署、容器到服务的网络和版本；错误正文不记录凭据。"}
