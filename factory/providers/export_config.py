"""Portable LiteLLM config without secrets or unsafe callback/module settings."""
from .catalog import PROVIDER_PREFIX
from .options import option_kwargs


def export_config(profiles: list[dict]) -> dict:
    import yaml
    models, variables = [], []
    for profile in profiles:
        if not profile["enabled"]:
            continue
        prefix = PROVIDER_PREFIX[profile["provider"]]
        model = profile["model"]
        if not model.startswith(prefix + "/"):
            model = prefix + "/" + model
        params = {**option_kwargs(profile["provider"], profile.get("litellm_params", {})),
                  "model": model, "temperature": profile["temperature"], "max_tokens": profile["max_tokens"]}
        for key in ("api_version", "base_url"):
            if profile.get(key):
                params["api_base" if key == "base_url" else key] = profile[key]
        fields = list(profile.get("credential_fields", []))
        if profile["has_api_key"]:
            fields.append("api_key")
        for key in fields:
            name = "RND_" + profile["id"].replace("-", "_").upper() + "_" + key.upper()
            variables.append(name)
            params[key] = "os.environ/" + name
        if profile["provider"] == "chatgpt":
            params.pop("max_tokens", None); params.pop("temperature", None)
        models.append({"model_name": profile["name"], "litellm_params": params})
    value = {"model_list": models, "litellm_settings": {"drop_params": True},
             "general_settings": {"master_key": "os.environ/LITELLM_MASTER_KEY"}}
    return {"yaml": yaml.safe_dump(value, allow_unicode=True, sort_keys=False),
            "environment_variables": ["LITELLM_MASTER_KEY", *variables],
            "note": "平台立即使用保存的 LiteLLM SDK 配置。此文件是 Proxy 部署配置，不自动覆盖独立网关；ChatGPT 需在独立网关重新授权，账号令牌不会导出。"}
