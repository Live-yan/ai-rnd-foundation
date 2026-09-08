from __future__ import annotations

from typing import TypedDict
from .config import Settings
from .providers.llm import LiteLLMPlanner
from .providers.mcp import SerenaClient
from .schemas import ProjectSpec, demo_spec


class PlanState(TypedDict, total=False):
    requirements: str
    context: str
    attempt: int
    candidate: dict
    valid: bool
    error: str
    spec: dict


async def plan(requirements: str, provider: str, use_serena: bool, settings: Settings) -> ProjectSpec:
    # Import lazily: unit tests can exercise the deterministic factory without an installed agent runtime.
    from langgraph.graph import END, START, StateGraph
    if provider not in {"demo", "litellm"}:
        raise ValueError("Unknown planner provider")
    gateway = LiteLLMPlanner(settings)

    async def draft(state: PlanState):
        if provider == "demo":
            candidate = demo_spec().model_dump()
        else:
            candidate = await gateway.draft(state["requirements"], state.get("context", ""), state.get("error", ""))
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
    context = ""
    if use_serena:
        context = await SerenaClient(settings).template_context()
    # Temporal owns durable stage state. This small graph does NOT start a second checkpoint lifecycle.
    result = await graph.compile().ainvoke({"requirements": requirements, "context": context, "attempt": 0})
    if not result.get("valid"):
        raise ValueError("The model did not produce a supported, valid schema after two attempts")
    return ProjectSpec.model_validate(result["spec"])
