from __future__ import annotations

from typing import TypedDict
from .config import Settings
from .providers.llm import ModelGateway
from .providers.mcp import SerenaClient
from .providers.registry import ProviderRuntime
from .schemas import ProjectSpec, demo_spec


class PlanState(TypedDict, total=False):
    requirements: str
    context: str
    attempt: int
    candidate: dict
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
            candidate = await gateway.draft(
                state["requirements"], provider, state.get("context", ""), state.get("error", "")
            )
        return {"candidate": candidate, "attempt": state.get("attempt", 0) + 1}

    def validate(state: PlanState):
        try:
            validated = ProjectSpec.model_validate(state["candidate"])
            return {"valid": True, "spec": validated.model_dump(), "error": ""}
        except ValueError as exc:
            return {"valid": False, "error": str(exc)[:3000]}

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
        raise ValueError("The model did not produce a supported, valid schema after two attempts")
    return ProjectSpec.model_validate(result["spec"])
