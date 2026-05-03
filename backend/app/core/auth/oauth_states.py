"""OAuth state, redirect, and PKCE helpers."""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any, Optional

from backend.app.core.persistence import persistence_manager

from ._crypto import _b64url_encode
from .constants import AUTH_OAUTH_STATE_RECORD_TYPE


def _find_oauth_state_record(state: str) -> Optional[dict[str, Any]]:
    normalized = str(state or "").strip()
    if not normalized:
        return None
    for record in persistence_manager.list_records(
        record_type=AUTH_OAUTH_STATE_RECORD_TYPE, limit=500
    ):
        if str(record.get("record_key") or "").strip() == normalized:
            return record
    return None


def _persist_oauth_state(
    *,
    state: str,
    provider_id: str,
    code_verifier: str,
    redirect_uri: str,
    frontend_origin: str,
    expires_at: int,
) -> dict[str, Any]:
    return persistence_manager.put_record(
        record_type=AUTH_OAUTH_STATE_RECORD_TYPE,
        record_key=state,
        payload={
            "state": state,
            "provider_id": provider_id,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "frontend_origin": frontend_origin,
            "issued_at": int(time.time()),
            "expires_at": int(expires_at),
            "used_at": None,
        },
        record_id=f"{AUTH_OAUTH_STATE_RECORD_TYPE}:{state}",
    )


def _mark_oauth_state_used(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload") or {}
    return persistence_manager.put_record(
        record_type=AUTH_OAUTH_STATE_RECORD_TYPE,
        record_key=str(payload.get("state") or record.get("record_key")),
        payload={**payload, "used_at": int(time.time())},
        record_id=record.get("id"),
    )


def _backend_public_base_url() -> str:
    return str(
        os.getenv("BACKEND_PUBLIC_URL")
        or os.getenv("AUTH_PUBLIC_BASE_URL")
        or "http://127.0.0.1:8000"
    ).rstrip("/")


def _frontend_public_origin() -> str:
    return str(os.getenv("FRONTEND_ORIGIN") or "http://127.0.0.1:3000").rstrip("/")


def _pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(str(code_verifier or "").encode("utf-8")).digest()
    return _b64url_encode(digest)
