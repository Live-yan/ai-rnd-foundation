from __future__ import annotations

import json
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from .config import Settings
from .providers.llm import ModelGateway
from .providers.registry import ProviderRuntime
from .schemas import ClarificationResult

CLARIFICATION_PROMPT = """You are the requirements analyst of an AI software R&D platform.
Your job is NOT to write code yet. First determine whether the user's requirement is precise enough to design and verify.
Return only JSON matching the supplied ClarificationResult schema.

Rules:
1. Ask only blocking, decision-relevant questions. Group related ambiguity; normally 1-6 questions.
2. For a business application, explicitly resolve users/roles/data ownership, core entities and operations, critical business rules,
   external systems, deployment/runtime constraints, and acceptance conditions when they materially affect implementation.
3. Never silently assume payments, approval workflows, realtime ingestion, device protocols, security boundaries, or production deployment.
4. ready=true only when there are no blocking questions and acceptance_criteria is concrete and testable.
5. Record non-blocking assumptions and risks separately. suggested_stack may preserve the selected FastapiAdmin/Vue3/FastAPI/PostgreSQL template.
6. The current deterministic generator is strongest at typed CRUD and acyclic parent-child relationships. Do not hide richer requirements;
   capture them so the later planner can mark unsupported features or route them to coding agents.
"""


class ClarifyState(TypedDict, total=False):
    conversation: str
    previous: dict
    profile: ProviderRuntime
    result: dict
    error: str
    attempt: int


def _conversation(messages: list[dict]) -> str:
    parts = []
    for message in messages:
        role = str(message.get("role", "user"))
        content = str(message.get("content", "")).strip()
        if content:
            parts.append(f"{role.upper()}: {content}")
    return "\n\n".join(parts)[-40000:]


async def clarify(messages: list[dict], previous: dict | None, profile: ProviderRuntime, settings: Settings) -> ClarificationResult:
    gateway = ModelGateway(settings)

    async def analyze(state: ClarifyState) -> dict:
        error = state.get("error", "")
        result = await gateway.complete_json(
            profile,
            CLARIFICATION_PROMPT + "\nJSON schema:\n" + json.dumps(ClarificationResult.model_json_schema()),
            {
                "conversation": state["conversation"],
                "previous_analysis": state.get("previous") or {},
                "previous_validation_error": error[:2500],
                "selected_template": "FastapiAdmin + Vue3 + FastAPI + PostgreSQL + uv",
            },
            max_tokens=min(profile.max_tokens, 5000),
        )
        try:
            validated = ClarificationResult.model_validate(result)
            return {"result": validated.model_dump(), "error": "", "attempt": state.get("attempt", 0) + 1}
        except ValidationError as exc:
            return {"result": {}, "error": str(exc), "attempt": state.get("attempt", 0) + 1}

    def route(state: ClarifyState) -> str:
        if state.get("result"):
            return "done"
        if state.get("attempt", 0) >= 2:
            return "done"
        return "retry"

    graph = StateGraph(ClarifyState)
    graph.add_node("analyze", analyze)
    graph.add_edge(START, "analyze")
    graph.add_conditional_edges("analyze", route, {"retry": "analyze", "done": END})
    state = await graph.compile().ainvoke({
        "conversation": _conversation(messages), "previous": previous or {}, "profile": profile, "attempt": 0,
    })
    if not state.get("result"):
        raise RuntimeError("AI requirement clarification failed schema validation: " + state.get("error", "unknown error"))
    return ClarificationResult.model_validate(state["result"])
