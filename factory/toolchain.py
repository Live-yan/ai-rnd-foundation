from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path
from uuid import UUID

from .config import Settings

TOOL_DESCRIPTIONS = [
    ("fastapiadmin", "FastapiAdmin", "交互底座 / 认证 / Vue 管理后台 / 生成模板"),
    ("langgraph", "LangGraph", "需求澄清与结构化规划的 Agent 图"),
    ("litellm", "LiteLLM", "OpenAI、Anthropic、Gemini、DeepSeek 等模型统一路由"),
    ("temporal", "Temporal", "跨阶段持久化工作流、重试、人工审批信号"),
    ("openspec", "OpenSpec", "需求/设计/任务规格包与严格验证门禁"),
    ("diagrams", "mingrammer/diagrams", "部署架构图可编辑源码与 SVG"),
    ("structurizr", "Structurizr DSL + C4", "C1/C2/C3 架构模型与 DSL 验证"),
    ("toolhive", "ToolHive", "MCP 服务隔离、代理和工具暴露边界"),
    ("serena", "Serena", "对固定 Golden Template 做只读符号级上下文理解"),
    ("cube", "CubeSandbox", "隔离沙箱内执行固定验收检查"),
    ("coder", "Coder", "生成完成后的长期 IDE 工作区"),
]


def _module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def toolchain_status(settings: Settings, provider_count: int = 0) -> list[dict]:
    configured = {
        "fastapiadmin": settings.upstream_dir.joinpath("LICENSE").exists(),
        "langgraph": _module("langgraph"),
        "litellm": provider_count > 0 or bool(settings.model_api_key),
        "temporal": _module("temporalio") and bool(settings.temporal_address),
        "openspec": bool(shutil.which("openspec")),
        "diagrams": _module("diagrams") and bool(shutil.which("dot")),
        "structurizr": bool(settings.structurizr_image and settings.docker_host_data_dir),
        "toolhive": bool(settings.serena_url),
        "serena": bool(settings.serena_url),
        "cube": bool(settings.cube_api_url and settings.cube_api_key and settings.cube_template),
        "coder": bool(settings.coder_url and settings.coder_token and settings.coder_template_id),
    }
    execution = {
        "fastapiadmin": "always", "langgraph": "always", "litellm": "clarify+plan", "temporal": "always",
        "openspec": "always", "diagrams": "always", "structurizr": "full",
        "toolhive": "full", "serena": "full", "cube": "full", "coder": "full-after-package",
    }
    hints = {
        "litellm": "在“模型供应商”页创建并测试一个配置。",
        "structurizr": "完整模式需要 worker Docker socket 和 FACTORY_DOCKER_HOST_DATA_DIR，用固定 Structurizr 镜像验证每次生成的 workspace.dsl。",
        "toolhive": "按 integrations/toolhive/README.md 启动 ToolHive 代理。",
        "serena": "FACTORY_SERENA_URL 必须指向 ToolHive 管理的只读 Serena MCP。",
        "cube": "配置 Cube API URL / Key / Template；完整模式默认使用 Cube。",
        "coder": "配置 Coder URL / Token / Template；自动创建仅允许 FACTORY_CODER_OWNER_ID。",
    }
    result = []
    for key, name, role in TOOL_DESCRIPTIONS:
        result.append({
            "id": key, "name": name, "role": role, "configured": configured[key],
            "execution": execution[key], "hint": hints.get(key, ""),
        })
    return result


def require_full_toolchain(settings: Settings, *, owner: str, provider_count: int, sandbox: str, provision_coder: bool) -> None:
    rows = {row["id"]: row for row in toolchain_status(settings, provider_count)}
    required = ["fastapiadmin", "langgraph", "litellm", "temporal", "openspec", "diagrams", "structurizr", "toolhive", "serena", "cube"]
    if sandbox != "cube":
        raise ValueError("完整工具链必须使用 CubeSandbox；Docker/static 仅用于基础模式")
    if provision_coder:
        required.append("coder")
        if not settings.coder_owner_id or owner != settings.coder_owner_id:
            raise ValueError("完整模式自动创建 Coder 仅允许 FACTORY_CODER_OWNER_ID 指定的管理员")
    missing = [rows[key]["name"] for key in required if not rows[key]["configured"]]
    if missing:
        raise ValueError("完整工具链尚未配置：" + "、".join(missing))


def validate_structurizr(analysis_root: Path, run_id: str, settings: Settings) -> dict:
    run_id = str(UUID(run_id))
    if not settings.docker_host_data_dir:
        raise RuntimeError("FACTORY_DOCKER_HOST_DATA_DIR is required for Structurizr validation")
    host_arch = Path(settings.docker_host_data_dir) / "runs" / run_id / "analysis" / "architecture"
    if not analysis_root.joinpath("architecture/workspace.dsl").is_file():
        raise RuntimeError("Generated Structurizr workspace.dsl is missing")
    args = [
        "docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--mount", f"type=bind,source={host_arch},target=/usr/local/structurizr,readonly",
        settings.structurizr_image, "validate", "-workspace", "workspace.dsl",
    ]
    result = subprocess.run(args, text=True, capture_output=True, timeout=90, env={"PATH": os.environ.get("PATH", "")})
    if result.returncode:
        raise RuntimeError("Structurizr DSL validation failed: " + (result.stderr + result.stdout)[-1800:])
    return {"tool": "structurizr", "validated": True, "image": settings.structurizr_image,
            "output": (result.stdout + result.stderr)[-1200:]}
