"""Live model discovery for OpenAI-compatible and Ollama endpoints."""
from __future__ import annotations

import httpx
from fastapi import HTTPException

from ..config import Settings
from .catalog import NO_KEY_PROVIDERS, REQUIRE_BASE_URL
from .endpoint_policy import validate_model_origin

MAX_MODELS = 400


def _normalize_id(raw: str) -> str:
    return raw.strip()


async def discover_models(
    settings: Settings,
    provider: str,
    base_url: str,
    api_key: str = "",
) -> list[dict[str, str]]:
    url = (base_url or "").strip().rstrip("/")
    if provider in REQUIRE_BASE_URL and not url:
        raise HTTPException(422, f"{provider} requires an explicit Base URL for model discovery")
    if not url:
        raise HTTPException(422, "请先填写 Base URL 再发现模型")
    validate_model_origin(provider, url, settings)
    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif provider not in NO_KEY_PROVIDERS:
        raise HTTPException(422, "该供应商发现模型需要 API Key")

    timeout = httpx.Timeout(min(settings.model_timeout, 30.0))
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        if provider == "ollama" or url.rstrip("/").endswith(":11434") and "/v1" not in url:
            endpoint = url.rstrip("/") + "/api/tags"
            try:
                response = await client.get(endpoint, headers=headers)
            except httpx.HTTPError:
                raise HTTPException(502, "无法连接 Ollama，请检查 Base URL 与网络") from None
            if response.status_code >= 400:
                raise HTTPException(502, f"Ollama 返回 HTTP {response.status_code}")
            data = response.json()
            models = [
                {"id": _normalize_id(item.get("name") or item.get("model") or ""),
                 "label": _normalize_id(item.get("name") or item.get("model") or "")}
                for item in (data.get("models") or [])
            ]
        else:
            endpoint = url if url.endswith("/models") else url.rstrip("/") + "/models"
            # Some gateways expose models under the same /v1 root as chat completions.
            if not url.endswith("/v1") and "/v1/" not in url and not url.endswith("/openai/v1"):
                candidates = [url.rstrip("/") + "/v1/models", endpoint]
            else:
                candidates = [endpoint]
            response = None
            last_status = 0
            for candidate in candidates:
                try:
                    response = await client.get(candidate, headers=headers)
                except httpx.HTTPError:
                    response = None
                    last_status = 502
                    continue
                last_status = response.status_code
                if response.status_code < 400:
                    break
            if response is None or response.status_code >= 400:
                raise HTTPException(502, f"模型列表请求失败 (HTTP {last_status or 502})")
            data = response.json()
            items = data.get("data") if isinstance(data, dict) else None
            if not isinstance(items, list):
                items = []
            models = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                mid = _normalize_id(str(item.get("id") or item.get("name") or ""))
                if not mid:
                    continue
                owned = str(item.get("owned_by") or "").strip()
                models.append({"id": mid, "label": f"{mid}  ·  {owned}" if owned else mid})

    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in models:
        mid = item["id"]
        if mid in seen:
            continue
        seen.add(mid)
        cleaned.append({"id": mid, "label": item["label"]})
        if len(cleaned) >= MAX_MODELS:
            break
    if not cleaned:
        raise HTTPException(404, "端点未返回可用模型列表；可手动填写模型 ID")
    cleaned.sort(key=lambda item: item["id"].lower())
    return cleaned
