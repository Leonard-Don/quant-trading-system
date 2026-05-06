"""OAuth authorization-code flow helpers."""

from __future__ import annotations

import secrets
import time
from typing import Any, Optional
from urllib.parse import urlencode

import requests
from fastapi import HTTPException, status

from .oauth_providers import (
    _find_oauth_provider_record,
    _oauth_provider_preset,
    _sanitize_oauth_provider,
)
from .oauth_states import (
    _backend_public_base_url,
    _find_oauth_state_record,
    _frontend_public_origin,
    _mark_oauth_state_used,
    _persist_oauth_state,
    _pkce_challenge,
)
from .tokens import _issue_token_bundle
from .users import _upsert_oauth_user


def begin_oauth_authorization(
    provider_id: str,
    *,
    redirect_uri: Optional[str] = None,
    frontend_origin: Optional[str] = None,
) -> dict[str, Any]:
    record = _find_oauth_provider_record(provider_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OAuth provider not found"
        )
    provider = _sanitize_oauth_provider(record)
    if not provider.get("enabled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth provider is disabled"
        )

    normalized_redirect_uri = str(
        redirect_uri
        or provider.get("redirect_uri")
        or f"{_backend_public_base_url()}/infrastructure/auth/oauth/providers/{provider['provider_id']}/callback"
    ).strip()
    normalized_frontend_origin = str(
        frontend_origin or provider.get("frontend_origin") or _frontend_public_origin()
    ).strip()
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


def _resolve_oauth_user_identity(
    provider: dict[str, Any], userinfo: dict[str, Any]
) -> dict[str, Optional[str]]:
    subject = str(
        userinfo.get(provider.get("subject_field") or "sub")
        or userinfo.get("sub")
        or userinfo.get("id")
        or ""
    ).strip()
    display_name = str(
        userinfo.get(provider.get("display_name_field") or "name")
        or userinfo.get("name")
        or userinfo.get("login")
        or userinfo.get("email")
        or subject
    ).strip()
    email = (
        str(userinfo.get(provider.get("email_field") or "email") or userinfo.get("email") or "")
        .strip()
        .lower()
        or None
    )
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OAuth provider response is missing a subject identifier",
        )
    return {
        "subject": subject,
        "display_name": display_name or subject,
        "email": email,
    }


def _fetch_oauth_userinfo(provider: dict[str, Any], access_token: str) -> dict[str, Any]:
    if not provider.get("userinfo_url"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth provider userinfo_url is not configured",
        )
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
                    (
                        item.get("email")
                        for item in emails
                        if isinstance(item, dict) and item.get("email")
                    ),
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
) -> dict[str, Any]:
    provider_record = _find_oauth_provider_record(provider_id)
    if not provider_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="OAuth provider not found"
        )
    provider = _sanitize_oauth_provider(provider_record)
    if not provider.get("enabled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth provider is disabled"
        )
    state_record = _find_oauth_state_record(state)
    if not state_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="OAuth state not found"
        )
    state_payload = state_record.get("payload") or {}
    if str(state_payload.get("provider_id") or "").strip().lower() != provider["provider_id"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="OAuth state/provider mismatch"
        )
    if state_payload.get("used_at"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="OAuth state has already been used"
        )
    if int(state_payload.get("expires_at") or 0) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OAuth state expired")

    normalized_redirect_uri = str(
        redirect_uri or state_payload.get("redirect_uri") or provider.get("redirect_uri") or ""
    ).strip()
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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OAuth token response missing access_token",
        )

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
        "frontend_origin": state_payload.get("frontend_origin")
        or provider.get("frontend_origin")
        or _frontend_public_origin(),
    }
