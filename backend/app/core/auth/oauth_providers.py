"""OAuth provider registry helpers."""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import HTTPException, status

from backend.app.core.persistence import persistence_manager

from .constants import (
    AUTH_OAUTH_PROVIDER_RECORD_TYPE,
    ENV_OAUTH_PROVIDER_MAPPINGS,
    OAUTH_PROVIDER_PRESETS,
)
from .oauth_states import _backend_public_base_url, _frontend_public_origin
from .secrets import _env_flag
from .tokens import _normalize_scope_items


def _oauth_provider_preset(provider_type: str) -> dict[str, Any]:
    return OAUTH_PROVIDER_PRESETS.get(str(provider_type or "generic").strip().lower(), {})


def _env_oauth_provider_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
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
                "frontend_origin": str(
                    os.getenv(mapping["frontend_origin_env"], _frontend_public_origin())
                ).strip(),
                "scopes": _normalize_scope_items(
                    os.getenv(mapping["scopes_env"], " ".join(preset.get("scopes") or []))
                ),
                "default_scopes": _normalize_scope_items(
                    os.getenv(mapping["default_scopes_env"], "quant:read quant:write")
                ),
                "default_role": str(os.getenv(mapping["default_role_env"], "researcher")).strip()
                or "researcher",
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


def _find_oauth_provider_record(provider_id: str) -> Optional[dict[str, Any]]:
    normalized = str(provider_id or "").strip().lower()
    if not normalized:
        return None
    for record in persistence_manager.list_records(
        record_type=AUTH_OAUTH_PROVIDER_RECORD_TYPE, limit=200
    ):
        if str(record.get("record_key") or "").strip().lower() == normalized:
            return record
    return None


def _sanitize_oauth_provider(record: dict[str, Any]) -> dict[str, Any]:
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
        "display_name_field": payload.get("display_name_field")
        or preset.get("display_name_field")
        or "name",
        "email_field": payload.get("email_field") or preset.get("email_field") or "email",
        "extra_params": payload.get("extra_params") or {},
        "metadata": payload.get("metadata") or {},
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def list_oauth_providers(enabled_only: bool = False) -> list[dict[str, Any]]:
    providers = []
    for record in persistence_manager.list_records(
        record_type=AUTH_OAUTH_PROVIDER_RECORD_TYPE, limit=200
    ):
        provider = _sanitize_oauth_provider(record)
        if enabled_only and not provider.get("enabled"):
            continue
        providers.append(provider)
    return sorted(
        providers, key=lambda item: (not item.get("enabled"), item.get("provider_id") or "")
    )


def sync_env_oauth_providers(updated_by: str = "env_sync") -> list[dict[str, Any]]:
    synced: list[dict[str, Any]] = []
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


def diagnose_oauth_provider(provider_id: str) -> dict[str, Any]:
    record = _find_oauth_provider_record(provider_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OAuth provider not found"
        )
    provider = _sanitize_oauth_provider(record)
    expected_redirect_uri = (
        provider.get("redirect_uri")
        or f"{_backend_public_base_url()}/infrastructure/auth/oauth/providers/{provider['provider_id']}/callback"
    )
    findings: list[dict[str, Any]] = []
    if not provider.get("client_secret_configured"):
        findings.append(
            {"severity": "high", "message": "Client secret 未配置，无法完成授权码换 token"}
        )
    if not provider.get("frontend_origin"):
        findings.append(
            {
                "severity": "medium",
                "message": "Frontend origin 未配置，popup 回调将回退到默认 localhost:3000",
            }
        )
    if not provider.get("redirect_uri"):
        findings.append(
            {
                "severity": "low",
                "message": "Redirect URI 未显式配置，将使用自动生成的 backend callback URL",
            }
        )
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
    scopes: Optional[list[str] | str] = None,
    auto_create_user: bool = True,
    default_role: str = "researcher",
    default_scopes: Optional[list[str] | str] = None,
    subject_field: Optional[str] = None,
    display_name_field: Optional[str] = None,
    email_field: Optional[str] = None,
    extra_params: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
    updated_by: str = "system",
) -> dict[str, Any]:
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
        "label": str(label or existing_payload.get("label") or normalized_provider_id).strip()
        or normalized_provider_id,
        "provider_type": normalized_type,
        "enabled": bool(enabled),
        "client_id": normalized_client_id,
        "client_secret": str(client_secret or existing_payload.get("client_secret") or "").strip(),
        "auth_url": str(
            auth_url or existing_payload.get("auth_url") or preset.get("auth_url") or ""
        ).strip(),
        "token_url": str(
            token_url or existing_payload.get("token_url") or preset.get("token_url") or ""
        ).strip(),
        "userinfo_url": str(
            userinfo_url or existing_payload.get("userinfo_url") or preset.get("userinfo_url") or ""
        ).strip(),
        "redirect_uri": str(redirect_uri or existing_payload.get("redirect_uri") or "").strip(),
        "frontend_origin": str(
            frontend_origin or existing_payload.get("frontend_origin") or ""
        ).strip(),
        "scopes": _normalize_scope_items(
            scopes
            if scopes is not None
            else existing_payload.get("scopes") or preset.get("scopes") or []
        ),
        "auto_create_user": bool(auto_create_user),
        "default_role": str(default_role or existing_payload.get("default_role") or "researcher"),
        "default_scopes": _normalize_scope_items(
            default_scopes
            if default_scopes is not None
            else existing_payload.get("default_scopes") or []
        ),
        "subject_field": str(
            subject_field
            or existing_payload.get("subject_field")
            or preset.get("subject_field")
            or "sub"
        ).strip(),
        "display_name_field": str(
            display_name_field
            or existing_payload.get("display_name_field")
            or preset.get("display_name_field")
            or "name"
        ).strip(),
        "email_field": str(
            email_field
            or existing_payload.get("email_field")
            or preset.get("email_field")
            or "email"
        ).strip(),
        "extra_params": extra_params
        if extra_params is not None
        else existing_payload.get("extra_params") or {},
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
