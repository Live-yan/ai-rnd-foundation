"""Expiring, single-artifact download capabilities for a Coder workspace.

No login token, model key or Coder session token is sent to the workspace.
The capability cannot list projects, approve runs, or read a different archive.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from uuid import UUID

from fastapi import HTTPException

from .config import Settings


def _sign(payload: str, settings: Settings) -> str:
    if len(settings.credential_encryption_key) < 24:
        raise ValueError("Configure the platform credential key before enabling Coder source handoff")
    return hmac.new(settings.credential_encryption_key.encode(),
                    ("rnd-coder-source-v1:" + payload).encode(), hashlib.sha256).hexdigest()


def issue_source_ticket(run_id: str, sha256: str, settings: Settings, *, now: int | None = None) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({
        "run": str(UUID(run_id)), "sha256": sha256, "exp": (int(time.time()) if now is None else now) + 900,
    }, sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")
    return payload + "." + _sign(payload, settings)


def verify_source_ticket(token: str, run_id: str, sha256: str, settings: Settings, *, now: int | None = None) -> None:
    try:
        if len(token) > 1024:
            raise ValueError("Oversized ticket")
        payload, signature = token.split(".", 1)
        if not hmac.compare_digest(_sign(payload, settings), signature):
            raise ValueError("Invalid signature")
        value = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        current = int(time.time()) if now is None else now
        if value != {"run": str(UUID(run_id)), "sha256": sha256, "exp": value.get("exp")}:
            raise ValueError("Ticket scope mismatch")
        if not current < int(value["exp"]) <= current + 900:
            raise ValueError("Ticket expired")
    except (ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(403, "Invalid or expired source-download capability") from None
