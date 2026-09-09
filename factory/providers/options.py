"""Allowlisted LiteLLM kwargs; definitions also travel with self-contained product schemas."""
from ..schemas import LiteLLMOptions


def option_kwargs(provider: str, values: dict) -> dict:
    options = LiteLLMOptions.model_validate(values).model_dump(exclude_none=True, exclude_unset=True)
    for key in list(options):
        if key.startswith("aws_") and provider != "bedrock":
            options.pop(key)
        elif key.startswith("vertex_") and provider != "vertex_ai":
            options.pop(key)
    return options
