from __future__ import annotations

import json
import re

import httpx
from typing import Any

from ..config import Settings
from ..schemas import ProjectSpec
from .catalog import JSON_FORMAT_PROVIDERS, NO_KEY_PROVIDERS, PROVIDER_PREFIX
from .registry import ProviderRuntime

SYSTEM_PROMPT = """You are the planning engine of an AI software R&D platform.
Convert only the clarified requirements into the provided ProjectSpec JSON schema.
Be conservative. Never invent a business rule simply to make the schema pass.
Anything that cannot be faithfully implemented by the current bounded CRUD generator MUST be listed in unsupported_features.
Use lowercase snake_case identifiers and keep the graph of reference fields acyclic.
Return one JSON object and no markdown.
"""


def litellm_model(profile: ProviderRuntime) -> str:
    prefix = PROVIDER_PREFIX.get(profile.provider, "openai")
    model = profile.model.strip()
    if model.startswith(prefix + "/"):
        return model
    return f"{prefix}/{model}"


def _extract_json(text: str) -> dict[str, Any]:
    if len(text) > 100000:
        raise ValueError("Model response exceeds the 100,000 character limit")
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model response did not contain a JSON object")
        parsed = json.loads(value[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Model response must be a JSON object")
    return parsed


class ModelGateway:
    """LiteLLM SDK adapter. Provider credentials come from the encrypted per-user registry."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete_json(
        self,
        profile: ProviderRuntime,
        system: str,
        payload: dict[str, Any],
        *,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        from ..privacy import install_sdk_log_safety
        install_sdk_log_safety()
        try:
            import litellm
            litellm.turn_off_message_logging = True
            litellm.suppress_debug_info = True
            litellm.set_verbose = False
            from litellm import acompletion
        except ImportError as exc:
            raise RuntimeError("LiteLLM SDK is unavailable; rebuild the platform image after updating dependencies") from exc
        if not profile.api_key and profile.provider not in NO_KEY_PROVIDERS:
            raise ValueError("The selected cloud provider requires its own API key")
        if profile.provider == "azure_openai" and not profile.api_version:
            raise ValueError("Azure OpenAI requires an explicit API version")
        kwargs: dict[str, Any] = {
            "model": litellm_model(profile),
            "custom_llm_provider": PROVIDER_PREFIX.get(profile.provider, "openai"),
            "api_key": profile.api_key or "local-no-key",
            "num_retries": 0,
            "drop_params": True,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": profile.temperature,
            "max_tokens": max_tokens or profile.max_tokens,
            "timeout": self.settings.model_timeout,
        }
        if profile.api_version:
            kwargs["api_version"] = profile.api_version
        if profile.base_url:
            kwargs["api_base"] = profile.base_url.rstrip("/")
        if profile.provider in JSON_FORMAT_PROVIDERS:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = await acompletion(**kwargs)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            suffix = f" (HTTP {status})" if isinstance(status, int) else ""
            raise RuntimeError(f"Model provider request failed{suffix}; check provider configuration and quota") from None
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Model returned an empty response")
        return _extract_json(content)

    async def draft(
        self,
        requirements: str,
        profile: ProviderRuntime,
        context: str = "",
        error: str = "",
    ) -> dict:
        return await self.complete_json(
            profile,
            SYSTEM_PROMPT + "\nJSON schema:\n" + json.dumps(ProjectSpec.model_json_schema()),
            {
                "requirements": requirements,
                "read_only_template_context": context[:16000],
                "previous_validation_error": error[:2500],
            },
        )

    async def ping(self, profile: ProviderRuntime) -> dict:
        result = await self.complete_json(
            profile,
            'Return exactly a JSON object matching {"ok": true, "message": "..."}. Do not use markdown.',
            {"task": "provider connectivity test"},
            max_tokens=128,
        )
        if result.get("ok") is not True:
            raise RuntimeError("Provider test did not return the required ok=true acknowledgement")
        return {"ok": True, "message": "模型已完成真实 JSON 响应测试"}


class LiteLLMPlanner:
    """Backward-compatible OpenAI-compatible gateway used by existing probes/tests.

    New interactive workbench calls :class:`ModelGateway` with encrypted per-user ProviderProfiles.
    This adapter intentionally keeps the legacy env-only HTTP contract so upgrades do not break operators' probes.
    """

    def __init__(self, settings: Settings, transport=None):
        self.settings, self.transport = settings, transport

    async def draft(self, requirements: str, context: str = "", error: str = "") -> dict:
        if not self.settings.model_api_key:
            raise RuntimeError("FACTORY_MODEL_API_KEY is missing. Demo fallback is deliberately disabled.")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\nJSON schema:\n" + json.dumps(ProjectSpec.model_json_schema())},
            {"role": "user", "content": json.dumps({
                "requirements": requirements,
                "read_only_template_context": context[:16000],
                "previous_validation_error": error[:3000],
            }, ensure_ascii=False)},
        ]
        payload = {
            "model": self.settings.model_name, "messages": messages, "temperature": 0,
            "max_tokens": self.settings.model_max_tokens, "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(
            timeout=self.settings.model_timeout, transport=self.transport, follow_redirects=False
        ) as client:
            response = await client.post(
                self.settings.model_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.model_api_key}"}, json=payload,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Model gateway returned HTTP {response.status_code}; inspect gateway logs locally")
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            if not isinstance(text, str) or len(text) > 100000:
                raise ValueError("Invalid or oversized model response")
            return json.loads(text)
