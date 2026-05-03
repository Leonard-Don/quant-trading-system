"""Local and OAuth-linked user persistence helpers."""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import HTTPException, status

from backend.app.core.persistence import persistence_manager

from ._crypto import _hash_password, _verify_password
from .constants import AUTH_USER_RECORD_TYPE


def _issue_token_bundle(*args, **kwargs):
    from .tokens import _issue_token_bundle as issue

    return issue(*args, **kwargs)


def _find_user_record(subject: str) -> Optional[dict[str, Any]]:
    normalized = str(subject or "").strip()
    if not normalized:
        return None
    for record in persistence_manager.list_records(record_type=AUTH_USER_RECORD_TYPE, limit=500):
        if str(record.get("record_key") or "").strip() == normalized:
            return record
    return None


def _sanitize_user(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload") or {}
    return {
        "id": record.get("id"),
        "subject": payload.get("subject") or record.get("record_key"),
        "display_name": payload.get("display_name")
        or payload.get("subject")
        or record.get("record_key"),
        "role": payload.get("role") or "researcher",
        "enabled": payload.get("enabled", True),
        "scopes": payload.get("scopes") or [],
        "metadata": payload.get("metadata") or {},
        "last_login_at": payload.get("last_login_at"),
        "login_count": int(payload.get("login_count") or 0),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def list_local_users() -> list[dict[str, Any]]:
    records = persistence_manager.list_records(record_type=AUTH_USER_RECORD_TYPE, limit=500)
    users = [_sanitize_user(record) for record in records]
    return sorted(users, key=lambda item: (item.get("role") != "admin", item.get("subject") or ""))


def upsert_local_user(
    subject: str,
    role: str = "researcher",
    password: Optional[str] = None,
    enabled: bool = True,
    display_name: Optional[str] = None,
    scopes: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
    updated_by: str = "system",
) -> dict[str, Any]:
    normalized_subject = str(subject or "").strip()
    if not normalized_subject:
        raise ValueError("subject is required")
    existing = _find_user_record(normalized_subject)
    existing_payload = (existing or {}).get("payload") or {}
    password_hash = existing_payload.get("password_hash")
    if password:
        password_hash = _hash_password(password)
    if not password_hash:
        raise ValueError("password is required when creating a new user")
    normalized_scopes = [
        str(item).strip()
        for item in (scopes if scopes is not None else existing_payload.get("scopes") or [])
        if str(item).strip()
    ]
    payload = {
        **existing_payload,
        "subject": normalized_subject,
        "display_name": str(
            display_name or existing_payload.get("display_name") or normalized_subject
        ).strip()
        or normalized_subject,
        "role": str(role or existing_payload.get("role") or "researcher"),
        "enabled": bool(enabled),
        "scopes": normalized_scopes,
        "metadata": metadata if metadata is not None else existing_payload.get("metadata") or {},
        "password_hash": password_hash,
        "updated_by": updated_by,
    }
    record = persistence_manager.put_record(
        record_type=AUTH_USER_RECORD_TYPE,
        record_key=normalized_subject,
        payload=payload,
        record_id=f"{AUTH_USER_RECORD_TYPE}:{normalized_subject}",
    )
    return _sanitize_user(record)


def authenticate_local_user(
    subject: str,
    password: str,
    expires_in_seconds: int = 86_400,
    refresh_expires_in_seconds: Optional[int] = None,
) -> dict[str, Any]:
    record = _find_user_record(subject)
    if not record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
    payload = record.get("payload") or {}
    if not payload.get("enabled", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")
    if not _verify_password(password, payload.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    updated_payload = {
        **payload,
        "last_login_at": int(time.time()),
        "login_count": int(payload.get("login_count") or 0) + 1,
    }
    saved = persistence_manager.put_record(
        record_type=AUTH_USER_RECORD_TYPE,
        record_key=str(payload.get("subject") or subject),
        payload=updated_payload,
        record_id=record.get("id"),
    )
    user = _sanitize_user(saved)
    return _issue_token_bundle(
        user,
        access_expires_in_seconds=expires_in_seconds,
        refresh_expires_in_seconds=refresh_expires_in_seconds,
        grant_type="password",
        metadata={
            "login_subject": subject,
        },
    )


def _find_linked_oauth_user(
    provider_id: str, external_subject: str, email: Optional[str]
) -> Optional[dict[str, Any]]:
    for record in persistence_manager.list_records(record_type=AUTH_USER_RECORD_TYPE, limit=500):
        payload = record.get("payload") or {}
        metadata = payload.get("metadata") or {}
        identities = metadata.get("oauth_identities") or {}
        if str(identities.get(provider_id) or "").strip() == external_subject:
            return record
        metadata_email = str(metadata.get("email") or "").strip().lower()
        if email and metadata_email and metadata_email == email:
            return record
    return None


def _upsert_oauth_user(
    provider: dict[str, Any],
    *,
    external_subject: str,
    display_name: str,
    email: Optional[str],
    userinfo: dict[str, Any],
) -> dict[str, Any]:
    existing = _find_linked_oauth_user(provider["provider_id"], external_subject, email)
    if not existing and not provider.get("auto_create_user", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="OAuth user auto-provisioning is disabled"
        )
    existing_payload = (existing or {}).get("payload") or {}
    metadata = dict(existing_payload.get("metadata") or {})
    oauth_identities = dict(metadata.get("oauth_identities") or {})
    oauth_identities[provider["provider_id"]] = external_subject
    metadata.update(
        {
            "oauth_identities": oauth_identities,
            "oauth_provider": provider["provider_id"],
            "oauth_profile": userinfo,
        }
    )
    if email:
        metadata["email"] = email
    subject = str(
        existing_payload.get("subject")
        or (existing.get("record_key") if existing else "")
        or f"oauth:{provider['provider_id']}:{external_subject}"
    ).strip()
    payload = {
        **existing_payload,
        "subject": subject,
        "display_name": display_name or subject,
        "role": str(existing_payload.get("role") or provider.get("default_role") or "researcher"),
        "enabled": existing_payload.get("enabled", True),
        "scopes": existing_payload.get("scopes") or provider.get("default_scopes") or [],
        "metadata": metadata,
        "password_hash": existing_payload.get("password_hash") or _hash_password(uuid.uuid4().hex),
        "updated_by": "oauth_callback",
        "last_login_at": int(time.time()),
        "login_count": int(existing_payload.get("login_count") or 0) + 1,
    }
    record = persistence_manager.put_record(
        record_type=AUTH_USER_RECORD_TYPE,
        record_key=subject,
        payload=payload,
        record_id=existing.get("id") if existing else f"{AUTH_USER_RECORD_TYPE}:{subject}",
    )
    return _sanitize_user(record)
