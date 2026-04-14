"""Auth helpers for API-key, JWT tokens, local users and OAuth providers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode
import uuid
from typing import Any, Dict, List, Optional

import requests
from fastapi import Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from backend.app.core.persistence import persistence_manager

AUTH_USER_RECORD_TYPE = "auth_user"
AUTH_POLICY_RECORD_TYPE = "auth_policy"
AUTH_REFRESH_RECORD_TYPE = "auth_refresh_session"
AUTH_OAUTH_PROVIDER_RECORD_TYPE = "auth_oauth_provider"
AUTH_OAUTH_STATE_RECORD_TYPE = "auth_oauth_state"
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/infrastructure/oauth/token", auto_error=False)


OAUTH_PROVIDER_PRESETS: Dict[str, Dict[str, Any]] = {
    "github": {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "email_url": "https://api.github.com/user/emails",
        "scopes": ["read:user", "user:email"],
        "subject_field": "login",
        "display_name_field": "name",
        "email_field": "email",
    },
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scopes": ["openid", "email", "profile"],
        "subject_field": "sub",
        "display_name_field": "name",
        "email_field": "email",
    },
}

ENV_OAUTH_PROVIDER_MAPPINGS: Dict[str, Dict[str, Any]] = {
    "github": {
        "provider_id": "github",
        "provider_type": "github",
        "label": "GitHub",
        "client_id_env": "GITHUB_OAUTH_CLIENT_ID",
        "client_secret_env": "GITHUB_OAUTH_CLIENT_SECRET",
        "redirect_uri_env": "GITHUB_OAUTH_REDIRECT_URI",
        "frontend_origin_env": "GITHUB_OAUTH_FRONTEND_ORIGIN",
        "scopes_env": "GITHUB_OAUTH_SCOPES",
        "default_scopes_env": "GITHUB_OAUTH_DEFAULT_SCOPES",
        "default_role_env": "GITHUB_OAUTH_DEFAULT_ROLE",
        "auto_create_user_env": "GITHUB_OAUTH_AUTO_CREATE_USER",
        "enabled_env": "GITHUB_OAUTH_ENABLED",
    },
    "google": {
        "provider_id": "google",
        "provider_type": "google",
        "label": "Google",
        "client_id_env": "GOOGLE_OAUTH_CLIENT_ID",
        "client_secret_env": "GOOGLE_OAUTH_CLIENT_SECRET",
        "redirect_uri_env": "GOOGLE_OAUTH_REDIRECT_URI",
        "frontend_origin_env": "GOOGLE_OAUTH_FRONTEND_ORIGIN",
        "scopes_env": "GOOGLE_OAUTH_SCOPES",
        "default_scopes_env": "GOOGLE_OAUTH_DEFAULT_SCOPES",
        "default_role_env": "GOOGLE_OAUTH_DEFAULT_ROLE",
        "auto_create_user_env": "GOOGLE_OAUTH_AUTO_CREATE_USER",
        "enabled_env": "GOOGLE_OAUTH_ENABLED",
    },
}


def _b64url_encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _b64url_decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode((payload + padding).encode("ascii"))


def _auth_secret() -> bytes:
    return os.getenv("AUTH_SECRET", "dev-only-change-me").encode("utf-8")


def _env_auth_required() -> bool:
    return os.getenv("AUTH_REQUIRED", "false").lower() == "true"


def _hash_password(password: str, iterations: int = 200_000) -> str:
    if not password:
        raise ValueError("password is required")
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = str(encoded or "").split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            str(password or "").encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        ).hex()
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


def _load_policy() -> Dict[str, Any]:
    records = persistence_manager.list_records(record_type=AUTH_POLICY_RECORD_TYPE, limit=1)
    payload = (records[0].get("payload") or {}) if records else {}
    required = bool(payload.get("required", _env_auth_required()))
    return {
        "required": required,
        "mode": "local_jwt",
        "updated_at": payload.get("updated_at") or (records[0].get("updated_at") if records else None),
        "updated_by": payload.get("updated_by"),
        "note": (
            "Authentication is required for protected API calls"
            if required
            else "Authentication is optional; anonymous research access is allowed"
        ),
    }


def _hash_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _default_access_ttl() -> int:
    return max(300, min(int(os.getenv("AUTH_ACCESS_TOKEN_TTL", "86400")), 60 * 60 * 24 * 30))


def _default_refresh_ttl() -> int:
    return max(3600, min(int(os.getenv("AUTH_REFRESH_TOKEN_TTL", str(60 * 60 * 24 * 30))), 60 * 60 * 24 * 180))


def _normalize_scope_items(scopes: Optional[List[str] | str]) -> List[str]:
    if isinstance(scopes, str):
        raw_items = scopes.replace(",", " ").split()
    else:
        raw_items = list(scopes or [])
    return [str(item).strip() for item in raw_items if str(item).strip()]


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off", ""}


def _oauth_provider_preset(provider_type: str) -> Dict[str, Any]:
    return OAUTH_PROVIDER_PRESETS.get(str(provider_type or "generic").strip().lower(), {})


def _env_oauth_provider_specs() -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    for mapping in ENV_OAUTH_PROVIDER_MAPPINGS.values():
        client_id = str(os.getenv(mapping["client_id_env"], "")).strip()
        if not client_id:
            continue
        provider_type = mapping["provider_type"]
        preset = _oauth_provider_preset(provider_type)
        provider_id = mapping["provider_id"]
        specs.append(
            {
                "provider_id": provider_id,
                "label": mapping["label"],
                "provider_type": provider_type,
                "enabled": _env_flag(mapping["enabled_env"], True),
                "client_id": client_id,
                "client_secret": str(os.getenv(mapping["client_secret_env"], "")).strip() or None,
                "redirect_uri": str(
                    os.getenv(
                        mapping["redirect_uri_env"],
                        f"{_backend_public_base_url()}/infrastructure/auth/oauth/providers/{provider_id}/callback",
                    )
                ).strip(),
                "frontend_origin": str(os.getenv(mapping["frontend_origin_env"], _frontend_public_origin())).strip(),
                "scopes": _normalize_scope_items(os.getenv(mapping["scopes_env"], " ".join(preset.get("scopes") or []))),
                "default_scopes": _normalize_scope_items(os.getenv(mapping["default_scopes_env"], "quant:read quant:write")),
                "default_role": str(os.getenv(mapping["default_role_env"], "researcher")).strip() or "researcher",
                "auto_create_user": _env_flag(mapping["auto_create_user_env"], True),
                "auth_url": preset.get("auth_url"),
                "token_url": preset.get("token_url"),
                "userinfo_url": preset.get("userinfo_url"),
                "subject_field": preset.get("subject_field"),
                "display_name_field": preset.get("display_name_field"),
                "email_field": preset.get("email_field"),
                "extra_params": {},
                "metadata": {
                    "source": "env",
                    "client_id_env": mapping["client_id_env"],
                    "client_secret_env": mapping["client_secret_env"],
                },
            }
        )
    return specs


def _find_oauth_provider_record(provider_id: str) -> Optional[Dict[str, Any]]:
    normalized = str(provider_id or "").strip().lower()
    if not normalized:
        return None
    for record in persistence_manager.list_records(record_type=AUTH_OAUTH_PROVIDER_RECORD_TYPE, limit=200):
        if str(record.get("record_key") or "").strip().lower() == normalized:
            return record
    return None


def _sanitize_oauth_provider(record: Dict[str, Any]) -> Dict[str, Any]:
    payload = record.get("payload") or {}
    provider_type = str(payload.get("provider_type") or "generic").strip().lower()
    preset = _oauth_provider_preset(provider_type)
    scopes = _normalize_scope_items(payload.get("scopes") or preset.get("scopes") or [])
    return {
        "id": record.get("id"),
        "provider_id": payload.get("provider_id") or record.get("record_key"),
        "label": payload.get("label") or payload.get("provider_id") or record.get("record_key"),
        "provider_type": provider_type,
        "enabled": payload.get("enabled", True),
        "client_id": payload.get("client_id") or "",
        "client_secret_configured": bool(payload.get("client_secret")),
        "auth_url": payload.get("auth_url") or preset.get("auth_url") or "",
        "token_url": payload.get("token_url") or preset.get("token_url") or "",
        "userinfo_url": payload.get("userinfo_url") or preset.get("userinfo_url") or "",
        "redirect_uri": payload.get("redirect_uri") or "",
        "frontend_origin": payload.get("frontend_origin") or "",
        "scopes": scopes,
        "auto_create_user": payload.get("auto_create_user", True),
        "default_role": payload.get("default_role") or "researcher",
        "default_scopes": _normalize_scope_items(payload.get("default_scopes") or []),
        "subject_field": payload.get("subject_field") or preset.get("subject_field") or "sub",
        "display_name_field": payload.get("display_name_field") or preset.get("display_name_field") or "name",
        "email_field": payload.get("email_field") or preset.get("email_field") or "email",
        "extra_params": payload.get("extra_params") or {},
        "metadata": payload.get("metadata") or {},
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def list_oauth_providers(enabled_only: bool = False) -> List[Dict[str, Any]]:
    providers = []
    for record in persistence_manager.list_records(record_type=AUTH_OAUTH_PROVIDER_RECORD_TYPE, limit=200):
        provider = _sanitize_oauth_provider(record)
        if enabled_only and not provider.get("enabled"):
            continue
        providers.append(provider)
    return sorted(providers, key=lambda item: (not item.get("enabled"), item.get("provider_id") or ""))


def sync_env_oauth_providers(updated_by: str = "env_sync") -> List[Dict[str, Any]]:
    synced: List[Dict[str, Any]] = []
    for spec in _env_oauth_provider_specs():
        synced.append(
            upsert_oauth_provider(
                provider_id=spec["provider_id"],
                label=spec["label"],
                provider_type=spec["provider_type"],
                enabled=spec["enabled"],
                client_id=spec["client_id"],
                client_secret=spec["client_secret"],
                auth_url=spec["auth_url"],
                token_url=spec["token_url"],
                userinfo_url=spec["userinfo_url"],
                redirect_uri=spec["redirect_uri"],
                frontend_origin=spec["frontend_origin"],
                scopes=spec["scopes"],
                auto_create_user=spec["auto_create_user"],
                default_role=spec["default_role"],
                default_scopes=spec["default_scopes"],
                subject_field=spec["subject_field"],
                display_name_field=spec["display_name_field"],
                email_field=spec["email_field"],
                extra_params=spec["extra_params"],
                metadata=spec["metadata"],
                updated_by=updated_by,
            )
        )
    return synced


def diagnose_oauth_provider(provider_id: str) -> Dict[str, Any]:
    record = _find_oauth_provider_record(provider_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OAuth provider not found")
    provider = _sanitize_oauth_provider(record)
    expected_redirect_uri = provider.get("redirect_uri") or f"{_backend_public_base_url()}/infrastructure/auth/oauth/providers/{provider['provider_id']}/callback"
    findings: List[Dict[str, Any]] = []
    if not provider.get("client_secret_configured"):
        findings.append({"severity": "high", "message": "Client secret 未配置，无法完成授权码换 token"})
    if not provider.get("frontend_origin"):
        findings.append({"severity": "medium", "message": "Frontend origin 未配置，popup 回调将回退到默认 localhost:3000"})
    if not provider.get("redirect_uri"):
        findings.append({"severity": "low", "message": "Redirect URI 未显式配置，将使用自动生成的 backend callback URL"})
    if not provider.get("enabled"):
        findings.append({"severity": "medium", "message": "Provider 当前处于禁用状态"})
    for field_name in ("auth_url", "token_url", "userinfo_url"):
        if not provider.get(field_name):
            findings.append({"severity": "high", "message": f"{field_name} 未配置"})
    return {
        "provider": provider,
        "expected_redirect_uri": expected_redirect_uri,
        "frontend_origin": provider.get("frontend_origin") or _frontend_public_origin(),
        "env_candidates": [
            {
                "provider_id": item["provider_id"],
                "source": "env",
                "client_id_present": bool(item.get("client_id")),
                "client_secret_present": bool(item.get("client_secret")),
            }
            for item in _env_oauth_provider_specs()
            if item["provider_id"] == provider["provider_id"]
        ],
        "findings": findings,
        "ready": not any(item["severity"] == "high" for item in findings),
    }


def upsert_oauth_provider(
    provider_id: str,
    *,
    label: str = "",
    provider_type: str = "generic",
    enabled: bool = True,
    client_id: str,
    client_secret: Optional[str] = None,
    auth_url: Optional[str] = None,
    token_url: Optional[str] = None,
    userinfo_url: Optional[str] = None,
    redirect_uri: str = "",
    frontend_origin: str = "",
    scopes: Optional[List[str] | str] = None,
    auto_create_user: bool = True,
    default_role: str = "researcher",
    default_scopes: Optional[List[str] | str] = None,
    subject_field: Optional[str] = None,
    display_name_field: Optional[str] = None,
    email_field: Optional[str] = None,
    extra_params: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    updated_by: str = "system",
) -> Dict[str, Any]:
    normalized_provider_id = str(provider_id or "").strip().lower()
    if not normalized_provider_id:
        raise ValueError("provider_id is required")
    normalized_client_id = str(client_id or "").strip()
    if not normalized_client_id:
        raise ValueError("client_id is required")
    normalized_type = str(provider_type or "generic").strip().lower()
    preset = _oauth_provider_preset(normalized_type)
    existing = _find_oauth_provider_record(normalized_provider_id)
    existing_payload = (existing or {}).get("payload") or {}
    payload = {
        **existing_payload,
        "provider_id": normalized_provider_id,
        "label": str(label or existing_payload.get("label") or normalized_provider_id).strip() or normalized_provider_id,
        "provider_type": normalized_type,
        "enabled": bool(enabled),
        "client_id": normalized_client_id,
        "client_secret": str(client_secret or existing_payload.get("client_secret") or "").strip(),
        "auth_url": str(auth_url or existing_payload.get("auth_url") or preset.get("auth_url") or "").strip(),
        "token_url": str(token_url or existing_payload.get("token_url") or preset.get("token_url") or "").strip(),
        "userinfo_url": str(userinfo_url or existing_payload.get("userinfo_url") or preset.get("userinfo_url") or "").strip(),
        "redirect_uri": str(redirect_uri or existing_payload.get("redirect_uri") or "").strip(),
        "frontend_origin": str(frontend_origin or existing_payload.get("frontend_origin") or "").strip(),
        "scopes": _normalize_scope_items(scopes if scopes is not None else existing_payload.get("scopes") or preset.get("scopes") or []),
        "auto_create_user": bool(auto_create_user),
        "default_role": str(default_role or existing_payload.get("default_role") or "researcher"),
        "default_scopes": _normalize_scope_items(default_scopes if default_scopes is not None else existing_payload.get("default_scopes") or []),
        "subject_field": str(subject_field or existing_payload.get("subject_field") or preset.get("subject_field") or "sub").strip(),
        "display_name_field": str(display_name_field or existing_payload.get("display_name_field") or preset.get("display_name_field") or "name").strip(),
        "email_field": str(email_field or existing_payload.get("email_field") or preset.get("email_field") or "email").strip(),
        "extra_params": extra_params if extra_params is not None else existing_payload.get("extra_params") or {},
        "metadata": metadata if metadata is not None else existing_payload.get("metadata") or {},
        "updated_by": updated_by,
    }
    if not payload["auth_url"] or not payload["token_url"]:
        raise ValueError("auth_url and token_url are required")
    record = persistence_manager.put_record(
        record_type=AUTH_OAUTH_PROVIDER_RECORD_TYPE,
        record_key=normalized_provider_id,
        payload=payload,
        record_id=f"{AUTH_OAUTH_PROVIDER_RECORD_TYPE}:{normalized_provider_id}",
    )
    return _sanitize_oauth_provider(record)


def _find_oauth_state_record(state: str) -> Optional[Dict[str, Any]]:
    normalized = str(state or "").strip()
    if not normalized:
        return None
    for record in persistence_manager.list_records(record_type=AUTH_OAUTH_STATE_RECORD_TYPE, limit=500):
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
) -> Dict[str, Any]:
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


def _mark_oauth_state_used(record: Dict[str, Any]) -> Dict[str, Any]:
    payload = record.get("payload") or {}
    return persistence_manager.put_record(
        record_type=AUTH_OAUTH_STATE_RECORD_TYPE,
        record_key=str(payload.get("state") or record.get("record_key")),
        payload={**payload, "used_at": int(time.time())},
        record_id=record.get("id"),
    )


def _backend_public_base_url() -> str:
    return str(os.getenv("BACKEND_PUBLIC_URL") or os.getenv("AUTH_PUBLIC_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")


def _frontend_public_origin() -> str:
    return str(os.getenv("FRONTEND_ORIGIN") or "http://127.0.0.1:3000").rstrip("/")


def _pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(str(code_verifier or "").encode("utf-8")).digest()
    return _b64url_encode(digest)

def get_auth_policy() -> Dict[str, Any]:
    return _load_policy()


def update_auth_policy(required: bool, updated_by: str = "system") -> Dict[str, Any]:
    payload = {
        "required": bool(required),
        "updated_by": updated_by,
        "updated_at": int(time.time()),
    }
    persistence_manager.put_record(
        record_type=AUTH_POLICY_RECORD_TYPE,
        record_key="default",
        payload=payload,
        record_id=f"{AUTH_POLICY_RECORD_TYPE}:default",
    )
    return get_auth_policy()


def _find_user_record(subject: str) -> Optional[Dict[str, Any]]:
    normalized = str(subject or "").strip()
    if not normalized:
        return None
    for record in persistence_manager.list_records(record_type=AUTH_USER_RECORD_TYPE, limit=500):
        if str(record.get("record_key") or "").strip() == normalized:
            return record
    return None


def _sanitize_user(record: Dict[str, Any]) -> Dict[str, Any]:
    payload = record.get("payload") or {}
    return {
        "id": record.get("id"),
        "subject": payload.get("subject") or record.get("record_key"),
        "display_name": payload.get("display_name") or payload.get("subject") or record.get("record_key"),
        "role": payload.get("role") or "researcher",
        "enabled": payload.get("enabled", True),
        "scopes": payload.get("scopes") or [],
        "metadata": payload.get("metadata") or {},
        "last_login_at": payload.get("last_login_at"),
        "login_count": int(payload.get("login_count") or 0),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def _find_refresh_session(session_id: str) -> Optional[Dict[str, Any]]:
    normalized = str(session_id or "").strip()
    if not normalized:
        return None
    for record in persistence_manager.list_records(record_type=AUTH_REFRESH_RECORD_TYPE, limit=1000):
        if str(record.get("record_key") or "").strip() == normalized:
            return record
    return None


def _sanitize_refresh_session(record: Dict[str, Any]) -> Dict[str, Any]:
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


def list_refresh_sessions(subject: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    sessions = []
    for record in persistence_manager.list_records(record_type=AUTH_REFRESH_RECORD_TYPE, limit=limit):
        session = _sanitize_refresh_session(record)
        if subject and session.get("subject") != subject:
            continue
        sessions.append(session)
    return sorted(sessions, key=lambda item: int(item.get("issued_at") or 0), reverse=True)


def list_local_users() -> List[Dict[str, Any]]:
    records = persistence_manager.list_records(record_type=AUTH_USER_RECORD_TYPE, limit=500)
    users = [_sanitize_user(record) for record in records]
    return sorted(users, key=lambda item: (item.get("role") != "admin", item.get("subject") or ""))


def upsert_local_user(
    subject: str,
    role: str = "researcher",
    password: Optional[str] = None,
    enabled: bool = True,
    display_name: Optional[str] = None,
    scopes: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    updated_by: str = "system",
) -> Dict[str, Any]:
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
        "display_name": str(display_name or existing_payload.get("display_name") or normalized_subject).strip() or normalized_subject,
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
) -> Dict[str, Any]:
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


def auth_status() -> Dict[str, Any]:
    users = list_local_users()
    policy = get_auth_policy()
    sessions = list_refresh_sessions(limit=500)
    oauth_providers = list_oauth_providers()
    env_oauth_candidates = _env_oauth_provider_specs()
    active_sessions = [
        item for item in sessions
        if not item.get("revoked_at") and int(item.get("expires_at") or 0) >= int(time.time())
    ]
    return {
        "required": policy["required"],
        "api_key_configured": bool(os.getenv("API_KEY")),
        "jwt_secret_configured": bool(os.getenv("AUTH_SECRET")),
        "supported": ["Local user + password", "OAuth2 password grant", "OAuth2 authorization code + PKCE", "Bearer HS256 token", "Refresh token rotation", "X-API-Key"],
        "local_user_count": len(users),
        "enabled_users": sum(1 for item in users if item.get("enabled")),
        "oauth_provider_count": len(oauth_providers),
        "oauth_enabled_providers": sum(1 for item in oauth_providers if item.get("enabled")),
        "oauth_env_candidates": len(env_oauth_candidates),
        "bootstrap_required": not any(item.get("enabled") for item in users),
        "active_refresh_sessions": len(active_sessions),
        "policy": policy,
    }


def create_access_token(
    subject: str,
    role: str = "researcher",
    expires_in_seconds: int = 86400,
    extra_claims: Optional[Dict[str, Any]] = None,
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
    extra_claims: Optional[Dict[str, Any]] = None,
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
        "exp": now + max(3600, min(int(expires_in_seconds or _default_refresh_ttl()), 60 * 60 * 24 * 180)),
    }
    if extra_claims:
        body.update(extra_claims)
    signing_input = f"{_b64url_encode(json.dumps(header, separators=(',', ':')).encode())}.{_b64url_encode(json.dumps(body, separators=(',', ':')).encode())}"
    signature = hmac.new(_auth_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def verify_access_token(token: str) -> Dict[str, Any]:
    try:
        header_raw, payload_raw, signature_raw = token.split(".", 2)
        signing_input = f"{header_raw}.{payload_raw}"
        expected = _b64url_encode(hmac.new(_auth_secret(), signing_input.encode("ascii"), hashlib.sha256).digest())
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}") from exc


def refresh_access_token(
    refresh_token: str,
    expires_in_seconds: Optional[int] = None,
    refresh_expires_in_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    payload = verify_access_token(refresh_token)
    if payload.get("typ") != REFRESH_TOKEN_TYPE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required")

    session_id = str(payload.get("jti") or "").strip()
    record = _find_refresh_session(session_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session not found")

    session_payload = record.get("payload") or {}
    if session_payload.get("revoked_at"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session has been revoked")
    if int(session_payload.get("expires_at") or 0) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session expired")
    if session_payload.get("token_hash") != _hash_token(refresh_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token mismatch")

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
    user: Dict[str, Any],
    grant_type: str,
    expires_at: int,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
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


def revoke_refresh_session(session_id: str, revoked_by: str = "system") -> Optional[Dict[str, Any]]:
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
    user: Dict[str, Any],
    *,
    access_expires_in_seconds: Optional[int] = None,
    refresh_expires_in_seconds: Optional[int] = None,
    grant_type: str = "password",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    access_ttl = max(60, min(int(access_expires_in_seconds or _default_access_ttl()), 60 * 60 * 24 * 30))
    refresh_ttl = max(3600, min(int(refresh_expires_in_seconds or _default_refresh_ttl()), 60 * 60 * 24 * 180))
    scope_items = [str(item).strip() for item in (user.get("scopes") or []) if str(item).strip()]
    session_id = uuid.uuid4().hex
    refresh_token = create_refresh_token(
        subject=user["subject"],
        role=user["role"],
        session_id=session_id,
        expires_in_seconds=refresh_ttl,
        extra_claims={
            "scope": " ".join(scope_items),
            "display_name": user.get("display_name"),
        },
    )
    access_token = create_access_token(
        subject=user["subject"],
        role=user["role"],
        expires_in_seconds=access_ttl,
        extra_claims={
            "scope": " ".join(scope_items),
            "scopes": scope_items,
            "display_name": user.get("display_name"),
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


def begin_oauth_authorization(
    provider_id: str,
    *,
    redirect_uri: Optional[str] = None,
    frontend_origin: Optional[str] = None,
) -> Dict[str, Any]:
    record = _find_oauth_provider_record(provider_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OAuth provider not found")
    provider = _sanitize_oauth_provider(record)
    if not provider.get("enabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth provider is disabled")

    normalized_redirect_uri = (
        str(redirect_uri or provider.get("redirect_uri") or f"{_backend_public_base_url()}/infrastructure/auth/oauth/providers/{provider['provider_id']}/callback").strip()
    )
    normalized_frontend_origin = str(frontend_origin or provider.get("frontend_origin") or _frontend_public_origin()).strip()
    code_verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(24)
    expires_at = int(time.time()) + 600
    _persist_oauth_state(
        state=state,
        provider_id=provider["provider_id"],
        code_verifier=code_verifier,
        redirect_uri=normalized_redirect_uri,
        frontend_origin=normalized_frontend_origin,
        expires_at=expires_at,
    )

    params = {
        "response_type": "code",
        "client_id": provider.get("client_id"),
        "redirect_uri": normalized_redirect_uri,
        "scope": " ".join(provider.get("scopes") or []),
        "state": state,
        "code_challenge": _pkce_challenge(code_verifier),
        "code_challenge_method": "S256",
    }
    for key, value in (provider.get("extra_params") or {}).items():
        if value not in (None, ""):
            params[str(key)] = value
    authorization_url = f"{provider.get('auth_url')}?{urlencode(params)}"
    return {
        "provider": provider,
        "state": state,
        "redirect_uri": normalized_redirect_uri,
        "frontend_origin": normalized_frontend_origin,
        "authorization_url": authorization_url,
        "expires_at": expires_at,
    }


def _resolve_oauth_user_identity(provider: Dict[str, Any], userinfo: Dict[str, Any]) -> Dict[str, Optional[str]]:
    subject = str(userinfo.get(provider.get("subject_field") or "sub") or userinfo.get("sub") or userinfo.get("id") or "").strip()
    display_name = str(
        userinfo.get(provider.get("display_name_field") or "name")
        or userinfo.get("name")
        or userinfo.get("login")
        or userinfo.get("email")
        or subject
    ).strip()
    email = str(userinfo.get(provider.get("email_field") or "email") or userinfo.get("email") or "").strip().lower() or None
    if not subject:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="OAuth provider response is missing a subject identifier")
    return {
        "subject": subject,
        "display_name": display_name or subject,
        "email": email,
    }


def _find_linked_oauth_user(provider_id: str, external_subject: str, email: Optional[str]) -> Optional[Dict[str, Any]]:
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
    provider: Dict[str, Any],
    *,
    external_subject: str,
    display_name: str,
    email: Optional[str],
    userinfo: Dict[str, Any],
) -> Dict[str, Any]:
    existing = _find_linked_oauth_user(provider["provider_id"], external_subject, email)
    if not existing and not provider.get("auto_create_user", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="OAuth user auto-provisioning is disabled")
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


def _fetch_oauth_userinfo(provider: Dict[str, Any], access_token: str) -> Dict[str, Any]:
    if not provider.get("userinfo_url"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth provider userinfo_url is not configured")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    response = requests.get(provider["userinfo_url"], headers=headers, timeout=20)
    response.raise_for_status()
    userinfo = response.json()
    if provider.get("provider_type") == "github" and not userinfo.get("email"):
        email_url = _oauth_provider_preset("github").get("email_url")
        if email_url:
            email_response = requests.get(email_url, headers=headers, timeout=20)
            email_response.raise_for_status()
            emails = email_response.json()
            if isinstance(emails, list) and emails:
                primary = next(
                    (
                        item.get("email")
                        for item in emails
                        if isinstance(item, dict) and item.get("primary") and item.get("verified")
                    ),
                    None,
                )
                fallback = next(
                    (item.get("email") for item in emails if isinstance(item, dict) and item.get("email")),
                    None,
                )
                userinfo["email"] = primary or fallback
    return userinfo if isinstance(userinfo, dict) else {}


def exchange_oauth_authorization_code(
    provider_id: str,
    *,
    code: str,
    state: str,
    redirect_uri: Optional[str] = None,
    expires_in_seconds: Optional[int] = None,
    refresh_expires_in_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    provider_record = _find_oauth_provider_record(provider_id)
    if not provider_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OAuth provider not found")
    provider = _sanitize_oauth_provider(provider_record)
    if not provider.get("enabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth provider is disabled")
    state_record = _find_oauth_state_record(state)
    if not state_record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OAuth state not found")
    state_payload = state_record.get("payload") or {}
    if str(state_payload.get("provider_id") or "").strip().lower() != provider["provider_id"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OAuth state/provider mismatch")
    if state_payload.get("used_at"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OAuth state has already been used")
    if int(state_payload.get("expires_at") or 0) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OAuth state expired")

    normalized_redirect_uri = str(redirect_uri or state_payload.get("redirect_uri") or provider.get("redirect_uri") or "").strip()
    token_payload = {
        "grant_type": "authorization_code",
        "code": str(code or "").strip(),
        "redirect_uri": normalized_redirect_uri,
        "client_id": provider.get("client_id"),
        "code_verifier": state_payload.get("code_verifier"),
    }
    client_secret = (provider_record.get("payload") or {}).get("client_secret")
    if client_secret:
        token_payload["client_secret"] = client_secret
    token_response = requests.post(
        provider["token_url"],
        data=token_payload,
        headers={"Accept": "application/json"},
        timeout=20,
    )
    if token_response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OAuth token exchange failed: {token_response.text[:240]}",
        )
    token_data = token_response.json()
    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="OAuth token response missing access_token")

    userinfo = _fetch_oauth_userinfo(provider, access_token)
    identity = _resolve_oauth_user_identity(provider, userinfo)
    local_user = _upsert_oauth_user(
        provider,
        external_subject=identity["subject"],
        display_name=identity["display_name"] or identity["subject"],
        email=identity["email"],
        userinfo=userinfo,
    )
    _mark_oauth_state_used(state_record)
    issued = _issue_token_bundle(
        local_user,
        access_expires_in_seconds=expires_in_seconds,
        refresh_expires_in_seconds=refresh_expires_in_seconds,
        grant_type="oauth_authorization_code",
        metadata={
            "oauth_provider": provider["provider_id"],
            "oauth_subject": identity["subject"],
            "oauth_email": identity["email"],
        },
    )
    return {
        **issued,
        "oauth_provider": provider["provider_id"],
        "oauth_profile": {
            "external_subject": identity["subject"],
            "display_name": identity["display_name"],
            "email": identity["email"],
            "userinfo": userinfo,
        },
        "frontend_origin": state_payload.get("frontend_origin") or provider.get("frontend_origin") or _frontend_public_origin(),
    }

async def get_current_user_optional(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    configured_api_key = os.getenv("API_KEY")
    auth_required = get_auth_policy()["required"]

    if configured_api_key and x_api_key:
        if hmac.compare_digest(configured_api_key, x_api_key):
            return {"sub": "api-key-user", "role": "service", "auth_method": "api_key"}
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    if authorization and authorization.lower().startswith("bearer "):
        payload = verify_access_token(authorization.split(" ", 1)[1].strip())
        if payload.get("typ") != ACCESS_TOKEN_TYPE:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token required")
        return {**payload, "auth_method": "bearer"}

    if auth_required:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    return {"sub": "anonymous", "role": "researcher", "auth_method": "optional"}
