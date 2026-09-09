"""Preserve the curated provider directory; add explicit authentication capabilities."""
from . import catalog_defaults as defaults

CATEGORY_ORDER = defaults.CATEGORY_ORDER
HOSTED_ORIGINS = defaults.HOSTED_ORIGINS
REQUIRE_BASE_URL = defaults.REQUIRE_BASE_URL
JSON_FORMAT_PROVIDERS = defaults.JSON_FORMAT_PROVIDERS
PROVIDER_PREFIX = {**defaults.PROVIDER_PREFIX, "chatgpt": "chatgpt"}
NO_KEY_PROVIDERS = defaults.NO_KEY_PROVIDERS | {"chatgpt", "bedrock", "vertex_ai"}
CHATGPT = {
    "id": "chatgpt", "name": "OpenAI · ChatGPT / Codex 登录", "category": "主流云端",
    "description": "官方网页登录 / 设备码授权；使用账号可用的订阅模型，不是 OpenAI API Key。",
    "requires_api_key": False, "requires_base_url": False, "supports_discover": False,
    "docs": "https://docs.litellm.ai/docs/providers/chatgpt", "models": [],
}
PROVIDER_CATALOG = [CHATGPT, *defaults.PROVIDER_CATALOG]
PROVIDER_KINDS = tuple(item["id"] for item in PROVIDER_CATALOG)


def catalog_payload() -> dict:
    value = defaults.catalog_payload()
    value["providers"].insert(0, {**CHATGPT, "base_url": "", "default_base_url": "",
        "litellm_prefix": "chatgpt", "is_local": False, "extra_hint": "", "discover_path": "openai"})
    for item in value["providers"]:
        item["requires_api_key"] = item["id"] not in NO_KEY_PROVIDERS
        item["auth_mode"] = ("device_oauth" if item["id"] == "chatgpt" else
                             "cloud_credentials" if item["id"] in {"bedrock", "vertex_ai"} else "api_key")
    return value
