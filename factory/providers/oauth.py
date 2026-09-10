"""Owner-scoped, encrypted, restart-safe device authorization and subscription calls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from fastapi import HTTPException
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from ..config import ROOT, Settings
from ..database import Database, ProviderProfile
from .registry import encrypt_secret, decrypt_secret, ProviderRuntime

VERIFICATION_URL = "https://auth.openai.com/codex/device"


def isolated_job(data: dict, timeout: int = 40) -> dict:
    with tempfile.TemporaryDirectory(prefix="rnd-chatgpt-") as directory:
        Path(directory).chmod(0o700)
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT), "HOME": directory,
               "CHATGPT_TOKEN_DIR": directory, "CHATGPT_AUTH_FILE": "auth.json",
               "LITELLM_LOG": "ERROR", "LITELLM_LOCAL_MODEL_COST_MAP": "True",
               "CHATGPT_DEFAULT_INSTRUCTIONS": "Follow the supplied system message. Return the requested JSON object only."}
        try:
            result = subprocess.run([sys.executable, "-m", "factory.providers.subscription_worker"],
                input=json.dumps(data), text=True, capture_output=True, env=env, cwd=ROOT, timeout=timeout)
            if result.returncode or len(result.stdout) > 2000000:
                raise ValueError("Invalid child reply")
            value = json.loads(result.stdout)
            if value.get("error"):
                raise ValueError("Authorization failed")
            return value
        except (ValueError, OSError, subprocess.TimeoutExpired):
            raise HTTPException(502, "ChatGPT 授权或请求未完成；检查账号权限、设备授权设置和网络后重试") from None


class OAuthService:
    def __init__(self, db: Database, settings: Settings):
        self.db, self.settings = db, settings

    def operation(self, owner: str, profile_id: str, action: str, kwargs: dict | None = None) -> dict:
        # Hold the per-profile row lock across refresh/exchange. This serializes refresh
        # across API/worker processes and prevents disconnect/new login resurrection.
        with self.db.session() as session:
            row = session.scalar(select(ProviderProfile).where(ProviderProfile.id == profile_id,
                ProviderProfile.owner_id == owner).with_for_update())
            if row is None or row.provider != "chatgpt":
                raise HTTPException(404, "ChatGPT provider profile not found")
            config = dict(row.config or {})
            now = int(time.time())
            if action == "disconnect":
                config = {k:v for k,v in config.items() if not k.startswith("oauth_")}
            pending = json.loads(decrypt_secret(config.get("oauth_pending", ""), self.settings) or "{}")
            if pending and pending.get("expires_at", 0) <= now:
                config.pop("oauth_pending", None)
                config["oauth_status"] = "expired"
                pending = {}
            if action == "restart":
                pending = {}
                config = {k: v for k, v in config.items() if not k.startswith("oauth_")}
            if action in {"begin", "restart"} and not pending:
                # Validate encryption configuration BEFORE issuing external authorization.
                encrypt_secret("encryption-check", self.settings)
                reply = isolated_job({"operation": "begin"})["pending"]
                if reply.get("verification_url") != VERIFICATION_URL or not reply.get("user_code") or not reply.get("device_auth_id"):
                    raise HTTPException(502, "Unexpected device authorization response")
                pending = {**reply, "expires_at": now + 900, "next_poll": now + 5,
                           "interval": max(5, min(30, int(reply.get("interval", 5))))}
                config.update(oauth_pending=encrypt_secret(json.dumps(pending), self.settings), oauth_status="pending")
            if action == "poll" and pending and now >= pending["next_poll"]:
                reply = isolated_job({"operation": "poll", "pending": pending})
                if reply.get("tokens"):
                    config.update(oauth_tokens=encrypt_secret(json.dumps(reply["tokens"]), self.settings), oauth_status="connected")
                    config.pop("oauth_pending", None)
                    pending = {}
                else:
                    if reply.get("slow_down"):
                        pending["interval"] = min(60, pending["interval"] + 5)
                    pending["next_poll"] = now + pending["interval"]
                    config["oauth_pending"] = encrypt_secret(json.dumps(pending), self.settings)
            if action == "complete":
                if not row.enabled or config.get("oauth_status") != "connected":
                    raise HTTPException(409, "请在模型供应商页先完成 ChatGPT 网页登录")
                tokens = json.loads(decrypt_secret(config.get("oauth_tokens", ""), self.settings) or "{}")
                reply = isolated_job({"operation": "complete", "tokens": tokens, "kwargs": kwargs}, timeout=200)
                config["oauth_tokens"] = encrypt_secret(json.dumps(reply["tokens"]), self.settings)
                row.config = config
                return {"content": reply["content"]}
            row.config = config
            return {"status": config.get("oauth_status", "not_connected"),
                    "verification_url": VERIFICATION_URL if pending else None,
                    "user_code": pending.get("user_code"), "expires_at": pending.get("expires_at"),
                    "interval": pending.get("interval", 5)}


async def subscription_completion(settings: Settings, profile: ProviderRuntime, system: str, payload: dict) -> str:
    model = profile.model if profile.model.startswith("chatgpt/") else "chatgpt/" + profile.model
    kwargs = {"model": model, "custom_llm_provider": "chatgpt", "num_retries": 0, "timeout": min(180, int(profile.litellm_params.get("timeout", settings.model_timeout))),
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}
    if profile.litellm_params.get("reasoning_effort"):
        kwargs["reasoning_effort"] = profile.litellm_params["reasoning_effort"]
    # Tokens are never part of the LangGraph state, Temporal args, or ProviderRuntime.
    def call():
        db = Database(settings.database_url)
        try:
            return OAuthService(db, settings).operation(profile.owner_id, profile.id, "complete", kwargs)["content"]
        finally:
            db.engine.dispose()
    return await run_in_threadpool(call)
