from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from uuid import uuid4
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..config import Settings
from ..database import Database, ProviderProfile
from ..schemas import ProviderInput, ProviderUpdate
from .catalog import REQUIRE_BASE_URL
from ..schemas import LiteLLMOptions, ProviderCredentials
from .endpoint_policy import validate_model_origin


@dataclass(frozen=True)
class ProviderRuntime:
    id: str
    name: str
    provider: str
    base_url: str
    model: str
    api_key: str = field(repr=False)
    temperature: float
    max_tokens: int
    source: str = "database"
    api_version: str = ""
    litellm_params: dict = field(default_factory=dict)
    credentials: dict = field(default_factory=dict, repr=False)
    owner_id: str = ""


def _fernet(settings: Settings) -> Fernet:
    if len(settings.credential_encryption_key) < 24:
        raise HTTPException(503, "FACTORY_CREDENTIAL_ENCRYPTION_KEY is missing; run scripts/init_env.py and restart")
    digest = hashlib.sha256(settings.credential_encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str, settings: Settings) -> str:
    if not value:
        return ""
    return _fernet(settings).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str, settings: Settings) -> str:
    if not value:
        return ""
    try:
        return _fernet(settings).decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise HTTPException(503, "Provider credential cannot be decrypted with the current platform key") from exc


def validate_endpoint(provider: str, base_url: str) -> str:
    value = base_url.strip()
    if provider == "chatgpt" and value:
        raise HTTPException(422, "ChatGPT 登录只连接固定官方端点，不接受自定义 Base URL")
    if provider in REQUIRE_BASE_URL and not value:
        raise HTTPException(422, f"{provider} requires an explicit Base URL")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(422, "Provider Base URL must be an absolute http(s) URL")
    if parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise HTTPException(422, "Provider Base URL must not contain credentials, a query string, or a URL fragment")
    return value.rstrip("/")


def validate_credentials(provider: str, api_key: str, values: dict) -> None:
    active = {key for key, value in values.items() if value}
    allowed = ({"aws_access_key_id", "aws_secret_access_key", "aws_session_token"} if provider == "bedrock"
               else {"vertex_credentials"} if provider == "vertex_ai" else set())
    if active - allowed or (provider in {"chatgpt", "bedrock", "vertex_ai"} and api_key):
        raise HTTPException(422, "凭据类型与供应商不匹配；账号授权、云凭据和 API Key 不能混用")
    ProviderCredentials.model_validate(values)


def public_provider(row: ProviderProfile) -> dict:
    config = row.config or {}
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "base_url": row.base_url,
        "model": row.model,
        "enabled": row.enabled,
        "is_default": row.is_default,
        "has_api_key": bool(row.api_key_ciphertext),
        "temperature": float(config.get("temperature", 0.1)),
        "max_tokens": int(config.get("max_tokens", 6000)),
        "api_version": str(config.get("api_version", "")),
        "litellm_params": config.get("litellm_params", {}),
        "credential_fields": config.get("credential_fields", []),
        "auth_status": config.get("oauth_status", "not_connected") if row.provider == "chatgpt" else "api_key",
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class ProviderService:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self._settings = settings

    @property
    def settings(self) -> Settings:
        from ..tool_settings import ToolSettingsService
        return ToolSettingsService(self.db, self._settings).effective()

    def list(self, owner: str) -> list[dict]:
        with self.db.session() as session:
            rows = session.scalars(
                select(ProviderProfile).where(ProviderProfile.owner_id == owner).order_by(
                    ProviderProfile.is_default.desc(), ProviderProfile.created_at.desc()
                )
            )
            return [public_provider(row) for row in rows]

    def create(self, owner: str, value: ProviderInput) -> dict:
        settings = self.settings
        validate_credentials(value.provider, value.api_key, value.credentials.model_dump())
        base_url = validate_endpoint(value.provider, value.base_url)
        validate_model_origin(value.provider, base_url, settings)
        if value.api_key:
            encrypted = encrypt_secret(value.api_key, settings)
        else:
            encrypted = ""
        try:
            with self.db.session() as session:
                if value.is_default:
                    session.execute(update(ProviderProfile).where(ProviderProfile.owner_id == owner).values(is_default=False))
                row = ProviderProfile(
                    id=str(uuid4()), owner_id=owner, name=value.name, provider=value.provider,
                    base_url=base_url, model=value.model.strip(), api_key_ciphertext=encrypted,
                    enabled=value.enabled, is_default=value.is_default and value.enabled,
                    config={"temperature": value.temperature, "max_tokens": value.max_tokens, "api_version": value.api_version,
                            "litellm_params": value.litellm_params.model_dump(exclude_none=True),
                            "credentials_ciphertext": encrypt_secret(value.credentials.model_dump_json(), settings) if any(value.credentials.model_dump().values()) else "",
                            "credential_fields": [k for k,v in value.credentials.model_dump().items() if v]},
                )
                session.add(row)
                session.flush()
                return public_provider(row)
        except IntegrityError as exc:
            raise HTTPException(409, "A provider profile with this name already exists") from exc

    def update(self, owner: str, provider_id: str, value: ProviderUpdate) -> dict:
        settings = self.settings
        with self.db.session() as session:
            row = session.scalar(select(ProviderProfile).where(
                ProviderProfile.id == provider_id, ProviderProfile.owner_id == owner
            ).with_for_update())
            if not row:
                raise HTTPException(404, "Provider profile not found")
            values = value.model_dump(exclude_unset=True, exclude_none=True)
            if values.get("provider", row.provider) != row.provider:
                raise HTTPException(422, "更换供应商请新建配置，不能复用旧供应商凭据")
            if "is_default" in values:
                make_default = bool(values.pop("is_default"))
                if make_default:
                    session.execute(update(ProviderProfile).where(ProviderProfile.owner_id == owner).values(is_default=False))
                row.is_default = make_default
            if "api_key" in values:
                api_key = values.pop("api_key")
                row.api_key_ciphertext = encrypt_secret(api_key or "", settings)
            config = dict(row.config or {})
            if "credentials" in values:
                new = values.pop("credentials")
                old = json.loads(decrypt_secret(config.get("credentials_ciphertext", ""), settings) or "{}")
                merged = ProviderCredentials.model_validate({**old, **new}).model_dump()
                config["credentials_ciphertext"] = encrypt_secret(json.dumps(merged), settings) if any(merged.values()) else ""
                config["credential_fields"] = [k for k, v in merged.items() if v]
            validate_credentials(row.provider, decrypt_secret(row.api_key_ciphertext, settings),
                                 json.loads(decrypt_secret(config.get("credentials_ciphertext", ""), settings) or "{}"))
            for key in ("temperature", "max_tokens", "api_version", "litellm_params"):
                if key in values:
                    config[key] = values.pop(key)
            for key, item in values.items():
                setattr(row, key, item)
            row.base_url = validate_endpoint(row.provider, row.base_url)
            validate_model_origin(row.provider, row.base_url, settings)
            if not row.enabled:
                row.is_default = False
            row.config = config
            session.flush()
            return public_provider(row)

    def delete(self, owner: str, provider_id: str) -> None:
        with self.db.session() as session:
            row = session.scalar(select(ProviderProfile).where(
                ProviderProfile.id == provider_id, ProviderProfile.owner_id == owner
            ))
            if not row:
                raise HTTPException(404, "Provider profile not found")
            session.delete(row)

    def set_default(self, owner: str, provider_id: str) -> dict:
        with self.db.session() as session:
            row = session.scalar(select(ProviderProfile).where(
                ProviderProfile.id == provider_id, ProviderProfile.owner_id == owner, ProviderProfile.enabled.is_(True)
            ).with_for_update())
            if not row:
                raise HTTPException(404, "Enabled provider profile not found")
            session.execute(update(ProviderProfile).where(ProviderProfile.owner_id == owner).values(is_default=False))
            row.is_default = True
            session.flush()
            return public_provider(row)

    def runtime(self, owner: str, provider_id: str | None = None) -> ProviderRuntime:
        settings = self.settings
        with self.db.session() as session:
            stmt = select(ProviderProfile).where(
                ProviderProfile.owner_id == owner, ProviderProfile.enabled.is_(True)
            )
            if provider_id:
                stmt = stmt.where(ProviderProfile.id == provider_id)
            else:
                stmt = stmt.order_by(ProviderProfile.is_default.desc(), ProviderProfile.created_at.asc())
            row = session.scalar(stmt.limit(1))
            if row:
                config = row.config or {}
                if row.provider == "chatgpt" and config.get("oauth_status") != "connected":
                    raise HTTPException(409, "请先在供应商页面完成 ChatGPT / Codex 登录")
                validate_endpoint(row.provider, row.base_url)
                validate_model_origin(row.provider, row.base_url, settings)
                api_key = decrypt_secret(row.api_key_ciphertext, settings)
                credentials = ProviderCredentials.model_validate(json.loads(decrypt_secret(
                    config.get("credentials_ciphertext", ""), settings) or "{}")).model_dump(exclude_defaults=True)
                validate_credentials(row.provider, api_key, credentials)
                return ProviderRuntime(
                    id=row.id, name=row.name, provider=row.provider, base_url=row.base_url, model=row.model,
                    api_key=api_key,
                    temperature=float(config.get("temperature", 0.1)),
                    max_tokens=int(config.get("max_tokens", settings.model_max_tokens)),
                    api_version=str(config.get("api_version", "")),
                    litellm_params=LiteLLMOptions.model_validate(config.get("litellm_params", {})).model_dump(exclude_none=True),
                    credentials=credentials,
                    owner_id=owner,
                )
        if provider_id and provider_id != "system-litellm":
            raise HTTPException(404, "Selected provider is unavailable, disabled, or belongs to another user")
        if settings.model_api_key:
            return ProviderRuntime(
                id="system-litellm", name="系统 LiteLLM", provider="litellm_proxy",
                base_url=settings.model_base_url, model=settings.model_name,
                api_key=settings.model_api_key, temperature=0.1,
                max_tokens=settings.model_max_tokens, source="environment",
            )
        raise HTTPException(422, "请先在“模型供应商”中配置并启用一个模型；严谨流程不会自动退回固定 Demo")
