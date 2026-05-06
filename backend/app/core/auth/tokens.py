"""JWT and refresh-session helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any, Optional

from fastapi import HTTPException, status

from backend.app.core.persistence import persistence_manager

from ._crypto import _b64url_decode, _b64url_encode, _hash_token
from .constants import ACCESS_TOKEN_TYPE, AUTH_REFRESH_RECORD_TYPE, REFRESH_TOKEN_TYPE
from .secrets import _auth_secret
from .users import _find_user_record, _sanitize_user


def _default_access_ttl() -> int:
    return max(300, min(int(os.getenv("AUTH_ACCESS_TOKEN_TTL", "86400")), 60 * 60 * 24 * 30))


def _default_refresh_ttl() -> int:
    return max(
        3600,
        min(int(os.getenv("AUTH_REFRESH_TOKEN_TTL", str(60 * 60 * 24 * 30))), 60 * 60 * 24 * 180),
    )


def _normalize_scope_items(scopes: Optional[list[str] | str]) -> list[str]:
    if isinstance(scopes, str):
        raw_items = scopes.replace(",", " ").split()
    else:
        raw_items = list(scopes or [])
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _find_refresh_session(session_id: str) -> Optional[dict[str, Any]]:
    normalized = str(session_id or "").strip()
    if not normalized:
        return None
    for record in persistence_manager.list_records(
        record_type=AUTH_REFRESH_RECORD_TYPE, limit=1000
    ):
        if str(record.get("record_key") or "").strip() == normalized:
            return record
    return None


def _sanitize_refresh_session(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload") or {}
    return {
        "id": record.get("id"),
        "session_id": payload.get("session_id") or record.get("record_key"),
        "subject": payload.get("subject"),
        "role": payload.get("role"),
        "scope": payload.get("scope") or "",
        "issued_at": payload.get("issued_at"),
        "expires_at": payload.get("expires_at"),
        "last_used_at": payload.get("last_used_at"),
        "revoked_at": payload.get("revoked_at"),
        "grant_type": payload.get("grant_type") or "password",
        "metadata": payload.get("metadata") or {},
    }


def list_refresh_sessions(subject: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
    sessions = []
    for record in persistence_manager.list_records(
        record_type=AUTH_REFRESH_RECORD_TYPE, limit=limit
    ):
        session = _sanitize_refresh_session(record)
        if subject and session.get("subject") != subject:
            continue
        sessions.append(session)
    return sorted(sessions, key=lambda item: int(item.get("issued_at") or 0), reverse=True)


def create_access_token(
    subject: str,
    role: str = "researcher",
    expires_in_seconds: int = 86400,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    body = {
        "sub": str(subject or "researcher"),
        "role": str(role or "researcher"),
        "typ": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + max(60, min(int(expires_in_seconds or 86400), 60 * 60 * 24 * 30)),
    }
    if extra_claims:
        body.update(extra_claims)
    signing_input = f"{_b64url_encode(json.dumps(header, separators=(',', ':')).encode())}.{_b64url_encode(json.dumps(body, separators=(',', ':')).encode())}"
    signature = hmac.new(_auth_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def create_refresh_token(
    subject: str,
    role: str = "researcher",
    session_id: Optional[str] = None,
    expires_in_seconds: Optional[int] = None,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    normalized_session = str(session_id or uuid.uuid4().hex)
    body = {
        "sub": str(subject or "researcher"),
        "role": str(role or "researcher"),
        "typ": REFRESH_TOKEN_TYPE,
        "jti": normalized_session,
        "iat": now,
        "exp": now
        + max(3600, min(int(expires_in_seconds or _default_refresh_ttl()), 60 * 60 * 24 * 180)),
    }
    if extra_claims:
        body.update(extra_claims)
    signing_input = f"{_b64url_encode(json.dumps(header, separators=(',', ':')).encode())}.{_b64url_encode(json.dumps(body, separators=(',', ':')).encode())}"
    signature = hmac.new(_auth_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def verify_access_token(token: str) -> dict[str, Any]:
    try:
        header_raw, payload_raw, signature_raw = token.split(".", 2)
        signing_input = f"{header_raw}.{payload_raw}"
        expected = _b64url_encode(
            hmac.new(_auth_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(expected, signature_raw):
            raise ValueError("invalid token signature")
        header = json.loads(_b64url_decode(header_raw))
        payload = json.loads(_b64url_decode(payload_raw))
        if header.get("alg") != "HS256":
            raise ValueError("unsupported token algorithm")
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("token expired")
        return payload
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}"
        ) from exc


def refresh_access_token(
    refresh_token: str,
    expires_in_seconds: Optional[int] = None,
    refresh_expires_in_seconds: Optional[int] = None,
) -> dict[str, Any]:
    payload = verify_access_token(refresh_token)
    if payload.get("typ") != REFRESH_TOKEN_TYPE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required"
        )

    session_id = str(payload.get("jti") or "").strip()
    record = _find_refresh_session(session_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session not found"
        )

    session_payload = record.get("payload") or {}
    if session_payload.get("revoked_at"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session has been revoked"
        )
    if int(session_payload.get("expires_at") or 0) < int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session expired"
        )
    if session_payload.get("token_hash") != _hash_token(refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token mismatch"
        )

    user_record = _find_user_record(str(payload.get("sub") or ""))
    if not user_record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    user_payload = user_record.get("payload") or {}
    if not user_payload.get("enabled", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")

    user = _sanitize_user(user_record)
    revoke_refresh_session(session_id, revoked_by=user.get("subject") or "system")
    refreshed = _issue_token_bundle(
        user,
        access_expires_in_seconds=expires_in_seconds,
        refresh_expires_in_seconds=refresh_expires_in_seconds,
        grant_type="refresh_token",
        metadata={
            "rotated_from": session_id,
        },
    )
    return {
        **refreshed,
        "rotated_session_id": session_id,
    }


def _persist_refresh_session(
    *,
    session_id: str,
    refresh_token: str,
    user: dict[str, Any],
    grant_type: str,
    expires_at: int,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload = {
        "session_id": session_id,
        "subject": user.get("subject"),
        "role": user.get("role"),
        "scope": " ".join(user.get("scopes") or []),
        "scopes": user.get("scopes") or [],
        "display_name": user.get("display_name"),
        "token_hash": _hash_token(refresh_token),
        "grant_type": grant_type,
        "issued_at": int(time.time()),
        "expires_at": int(expires_at),
        "last_used_at": None,
        "revoked_at": None,
        "metadata": metadata or {},
    }
    return persistence_manager.put_record(
        record_type=AUTH_REFRESH_RECORD_TYPE,
        record_key=session_id,
        payload=payload,
        record_id=f"{AUTH_REFRESH_RECORD_TYPE}:{session_id}",
    )


def revoke_refresh_session(session_id: str, revoked_by: str = "system") -> Optional[dict[str, Any]]:
    record = _find_refresh_session(session_id)
    if not record:
        return None
    payload = record.get("payload") or {}
    saved = persistence_manager.put_record(
        record_type=AUTH_REFRESH_RECORD_TYPE,
        record_key=str(payload.get("session_id") or session_id),
        payload={
            **payload,
            "revoked_at": int(time.time()),
            "revoked_by": revoked_by,
        },
        record_id=record.get("id"),
    )
    return _sanitize_refresh_session(saved)


def _issue_token_bundle(
    user: dict[str, Any],
    *,
    access_expires_in_seconds: Optional[int] = None,
    refresh_expires_in_seconds: Optional[int] = None,
    grant_type: str = "password",
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    access_ttl = max(
        60, min(int(access_expires_in_seconds or _default_access_ttl()), 60 * 60 * 24 * 30)
    )
    refresh_ttl = max(
        3600, min(int(refresh_expires_in_seconds or _default_refresh_ttl()), 60 * 60 * 24 * 180)
    )
    scope_items = [str(item).strip() for item in (user.get("scopes") or []) if str(item).strip()]
    user_metadata = user.get("metadata") if isinstance(user.get("metadata"), dict) else {}
    org_id = user_metadata.get("org_id") or user_metadata.get("organization_id")
    session_id = uuid.uuid4().hex
    shared_claims = {
        "scope": " ".join(scope_items),
        "display_name": user.get("display_name"),
    }
    if org_id:
        shared_claims["org_id"] = str(org_id)
    refresh_token = create_refresh_token(
        subject=user["subject"],
        role=user["role"],
        session_id=session_id,
        expires_in_seconds=refresh_ttl,
        extra_claims={
            **shared_claims,
        },
    )
    access_token = create_access_token(
        subject=user["subject"],
        role=user["role"],
        expires_in_seconds=access_ttl,
        extra_claims={
            **shared_claims,
            "scopes": scope_items,
            "session_id": session_id,
        },
    )
    _persist_refresh_session(
        session_id=session_id,
        refresh_token=refresh_token,
        user=user,
        grant_type=grant_type,
        expires_at=int(time.time()) + refresh_ttl,
        metadata=metadata,
    )
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in_seconds": access_ttl,
        "refresh_token": refresh_token,
        "refresh_token_type": "Bearer",
        "refresh_expires_in_seconds": refresh_ttl,
        "scope": " ".join(scope_items),
        "user": user,
    }
