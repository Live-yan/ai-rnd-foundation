"""Model discovery contract tests with mocked HTTP (not live provider receipts)."""
import asyncio

import httpx
import pytest
from fastapi import HTTPException

from factory.config import Settings
from factory.providers.discover import discover_models


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        model_allowed_origins=["http://gateway:4000", "http://host.docker.internal:11434"],
    )


def test_openai_compatible_discover(settings, monkeypatch):
    def respond(request):
        assert request.url.path.endswith("/models")
        assert request.headers["authorization"] == "Bearer sk-test"
        return httpx.Response(200, json={
            "data": [
                {"id": "gpt-4.1-mini", "owned_by": "openai"},
                {"id": "deepseek-chat", "owned_by": "deepseek"},
            ]
        })

    async def run():
        transport = httpx.MockTransport(respond)
        original = httpx.AsyncClient

        class Patched(original):
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = transport
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", Patched)
        return await discover_models(settings, "custom_openai", "http://gateway:4000/v1", "sk-test")

    models = asyncio.run(run())
    assert [m["id"] for m in models] == ["deepseek-chat", "gpt-4.1-mini"]


def test_ollama_discover(settings, monkeypatch):
    def respond(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "qwen2.5-coder:latest"}, {"name": "llama3.1"}]})

    async def run():
        transport = httpx.MockTransport(respond)
        original = httpx.AsyncClient

        class Patched(original):
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = transport
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", Patched)
        return await discover_models(settings, "ollama", "http://host.docker.internal:11434", "")

    models = asyncio.run(run())
    assert models[0]["id"] == "llama3.1"
    assert models[1]["id"] == "qwen2.5-coder:latest"


def test_discover_rejects_unapproved_origin(settings):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(discover_models(settings, "custom_openai", "http://evil.local/v1", "k"))
    assert exc.value.status_code == 422


def test_discover_requires_base_url(settings):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(discover_models(settings, "ollama", "", ""))
    assert exc.value.status_code == 422
