from __future__ import annotations

from typing import TypedDict
from pydantic import ValidationError
from .config import Settings
from .providers.llm import ModelGateway, ModelOutputError, validation_feedback
from .providers.mcp import SerenaClient
from .providers.registry import ProviderRuntime
from .schemas import ProjectSpec, demo_spec


class PlanState(TypedDict, total=False):
    requirements: str
    context: str
    attempt: int
    candidate: dict | None
    valid: bool
    error: str
    spec: dict


async def plan(
    requirements: str,
    provider: ProviderRuntime | str,
    use_serena: bool,
    settings: Settings,
    *,
    context: str | None = None,
) -> ProjectSpec:
    """Build a ProjectSpec with LangGraph.

    ``provider='demo'`` is kept only for deterministic unit tests. The interactive API no longer creates demo runs;
    it resolves an encrypted ProviderProfile before a project may leave clarification.
    """
    from langgraph.graph import END, START, StateGraph
    if isinstance(provider, str) and provider not in {"demo", "litellm"}:
        raise ValueError("Unknown planner provider")
    gateway = ModelGateway(settings)

    if isinstance(provider, str) and provider == "litellm":
        if not settings.model_api_key:
            raise ValueError("Legacy LiteLLM environment profile is not configured")
        provider = ProviderRuntime(
            id="system-litellm", name="系统 LiteLLM", provider="litellm_proxy",
            base_url=settings.model_base_url, model=settings.model_name, api_key=settings.model_api_key,
            temperature=0.1, max_tokens=settings.model_max_tokens, source="environment",
        )

    async def draft(state: PlanState):
        if provider == "demo":
            candidate = demo_spec().model_dump()
        else:
            try:
                candidate = await gateway.draft(
                    state["requirements"], provider, state.get("context", ""), state.get("error", ""), state.get("candidate")
                )
            except ModelOutputError as exc:
                return {"candidate": None, "valid": False, "error": str(exc), "attempt": state.get("attempt", 0) + 1}
        return {"candidate": candidate, "attempt": state.get("attempt", 0) + 1}

    def validate(state: PlanState):
        if state.get("candidate") is None:
            return {"valid": False}
        try:
            validated = ProjectSpec.model_validate(state["candidate"])
            return {"valid": True, "spec": validated.model_dump(), "error": ""}
        except ValidationError as exc:
            return {"valid": False, "error": validation_feedback(exc)}

    graph = StateGraph(PlanState)
    graph.add_node("draft", draft)
    graph.add_node("validate", validate)
    graph.add_edge(START, "draft")
    graph.add_edge("draft", "validate")
    graph.add_conditional_edges("validate", lambda s: END if s["valid"] or s["attempt"] >= 2 else "draft")
    resolved_context = context or ""
    if use_serena and context is None:
        resolved_context = await SerenaClient(settings).template_context()
    result = await graph.compile().ainvoke({"requirements": requirements, "context": resolved_context, "attempt": 0})
    if not result.get("valid"):
        raise ModelOutputError("模型在两次尝试后仍未生成有效的规格 JSON：" + result.get("error", "模型未返回有效结果") + " 请返回需求澄清调整计划；未自动删减字段或关系。")
    return ProjectSpec.model_validate(result["spec"])
