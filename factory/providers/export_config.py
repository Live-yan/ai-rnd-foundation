"""Portable LiteLLM config without secrets or unsafe callback/module settings."""
from .catalog import PROVIDER_PREFIX
from .options import option_kwargs


def export_config(profiles: list[dict]) -> dict:
    import yaml
    models, variables, skipped = [], [], []
    for profile in profiles:
        if not profile["enabled"]:
            continue
        if profile["provider"] == "chatgpt":
            skipped.append({"id": profile["id"], "reason": "owner_scoped_subscription_not_shareable"})
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
        models.append({"model_name": profile["name"], "litellm_params": params})
    value = {"model_list": models, "litellm_settings": {"drop_params": True},
             "general_settings": {"master_key": "os.environ/LITELLM_MASTER_KEY"}}
    return {"yaml": yaml.safe_dump(value, allow_unicode=True, sort_keys=False),
            "environment_variables": ["LITELLM_MASTER_KEY", *variables],
            "skipped": skipped,
            "note": "此文件仅导出 API/云凭据模型到 Proxy，密钥以环境变量引用。ChatGPT 订阅账号已排除，不能把个人授权变成共享网关账号。不会自动覆盖或重启现有网关。"}
