"""Runtime auth status and FastAPI dependency helpers."""

from __future__ import annotations

import hmac
import os
import time
from typing import Any, Optional

from fastapi import Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .constants import ACCESS_TOKEN_TYPE
from .oauth_providers import _env_oauth_provider_specs, list_oauth_providers
from .policy import get_auth_policy
from .secrets import is_auth_secret_production_ready, is_production_environment
from .tokens import list_refresh_sessions, verify_access_token
from .users import list_local_users

oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/infrastructure/oauth/token",
    auto_error=False,
)


def auth_status() -> dict[str, Any]:
    users = list_local_users()
    policy = get_auth_policy()
    sessions = list_refresh_sessions(limit=500)
    oauth_providers = list_oauth_providers()
    env_oauth_candidates = _env_oauth_provider_specs()
    production_mode = is_production_environment()
    auth_secret_ready = is_auth_secret_production_ready()
    api_key_configured = bool(os.getenv("API_KEY"))
    bootstrap_api_key_configured = bool(os.getenv("BOOTSTRAP_API_KEY") or os.getenv("API_KEY"))
    bootstrap_deadline = str(os.getenv("BOOTSTRAP_DEADLINE_EPOCH", "")).strip()
    bootstrap_required = not any(item.get("enabled") for item in users)
    active_sessions = [
        item
        for item in sessions
        if not item.get("revoked_at") and int(item.get("expires_at") or 0) >= int(time.time())
    ]
    readiness_findings: list[dict[str, str]] = []
    if production_mode and not policy["required"]:
        readiness_findings.append(
            {
                "severity": "high",
                "message": "Production environment must require authentication.",
            }
        )
    if production_mode and not auth_secret_ready:
        readiness_findings.append(
            {
                "severity": "critical",
                "message": "Set AUTH_SECRET to a strong non-default value before issuing tokens.",
            }
        )
    if production_mode and not bootstrap_api_key_configured and bootstrap_required:
        readiness_findings.append(
            {
                "severity": "critical",
                "message": "Configure BOOTSTRAP_API_KEY or API_KEY before production bootstrap.",
            }
        )
    if production_mode and bootstrap_required and not bootstrap_deadline:
        readiness_findings.append(
            {
                "severity": "high",
                "message": "Set BOOTSTRAP_DEADLINE_EPOCH to keep the production bootstrap window time-boxed.",
            }
        )
    return {
        "required": policy["required"],
        "api_key_configured": api_key_configured,
        "bootstrap_api_key_configured": bootstrap_api_key_configured,
        "bootstrap_deadline_epoch": bootstrap_deadline or None,
        "jwt_secret_configured": bool(os.getenv("AUTH_SECRET")),
        "jwt_secret_production_ready": auth_secret_ready,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "production_mode": production_mode,
        "production_ready": not readiness_findings,
        "readiness_findings": readiness_findings,
        "supported": [
            "Local user + password",
            "OAuth2 password grant",
            "OAuth2 authorization code + PKCE",
            "Bearer HS256 token",
            "Refresh token rotation",
            "X-API-Key",
        ],
        "local_user_count": len(users),
        "enabled_users": sum(1 for item in users if item.get("enabled")),
        "oauth_provider_count": len(oauth_providers),
        "oauth_enabled_providers": sum(1 for item in oauth_providers if item.get("enabled")),
        "oauth_env_candidates": len(env_oauth_candidates),
        "bootstrap_required": bootstrap_required,
        "active_refresh_sessions": len(active_sessions),
        "policy": policy,
    }


async def get_current_user_optional(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    configured_api_key = os.getenv("API_KEY")
    auth_required = get_auth_policy()["required"]

    if configured_api_key and x_api_key:
        if hmac.compare_digest(configured_api_key, x_api_key):
            return {"sub": "api-key-user", "role": "service", "auth_method": "api_key"}
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    if authorization and authorization.lower().startswith("bearer "):
        payload = verify_access_token(authorization.split(" ", 1)[1].strip())
        if payload.get("typ") != ACCESS_TOKEN_TYPE:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token required"
            )
        return {**payload, "auth_method": "bearer"}

    if auth_required:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    return {"sub": "anonymous", "role": "researcher", "auth_method": "optional"}
