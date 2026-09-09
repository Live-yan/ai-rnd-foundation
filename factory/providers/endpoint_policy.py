"""Only administrator-approved custom model origins can receive server-side requests.

This is an allowlist, not a DNS-based SSRF guarantee. Approved endpoints remain an
administrator trust boundary; production deployments also need egress controls.
"""
from urllib.parse import urlsplit

from fastapi import HTTPException

from ..config import Settings

HOSTED_ORIGINS = {
    "openai": {"https://api.openai.com"},
    "anthropic": {"https://api.anthropic.com"},
    "google": {"https://generativelanguage.googleapis.com"},
    "deepseek": {"https://api.deepseek.com"},
    "groq": {"https://api.groq.com"},
    "openrouter": {"https://openrouter.ai"},
    "mistral": {"https://api.mistral.ai"},
    "xai": {"https://api.x.ai"},
}


def origin(value: str) -> str:
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        raise HTTPException(422, "Invalid model endpoint port") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(422, "Model endpoint must be an absolute HTTP(S) URL")
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    suffix = f":{port}" if port and port != (443 if parsed.scheme == "https" else 80) else ""
    return f"{parsed.scheme}://{host}{suffix}"


def validate_model_origin(provider: str, base_url: str, settings: Settings) -> None:
    if not base_url:
        return
    selected = origin(base_url)
    if selected in HOSTED_ORIGINS.get(provider, set()):
        return
    parsed = urlsplit(base_url)
    if provider == "azure_openai" and parsed.scheme == "https" and parsed.port in {None, 443}:
        if parsed.hostname and parsed.hostname.endswith(".openai.azure.com"):
            return
    allowed = {origin(value) for value in settings.model_allowed_origins}
    if selected not in allowed:
        raise HTTPException(422, "自定义模型地址未获管理员批准。请将其 origin 加入 FACTORY_MODEL_ALLOWED_ORIGINS 后重启 API/worker")
