"""Environment and secret helpers for authentication."""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import HTTPException, status

from .constants import (
    DEFAULT_AUTH_SECRET,
    FALSE_ENV_VALUES,
    PRODUCTION_ENVIRONMENTS,
    TRUE_ENV_VALUES,
)


def _auth_secret() -> bytes:
    secret = os.getenv("AUTH_SECRET", DEFAULT_AUTH_SECRET)
    if is_production_environment() and not is_auth_secret_production_ready(secret):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AUTH_SECRET must be configured with a non-default value in production",
        )
    return secret.encode("utf-8")


def _env_auth_required() -> bool:
    explicit_value = os.getenv("AUTH_REQUIRED")
    if explicit_value is not None:
        return _env_bool_value(explicit_value, default=False)
    return is_production_environment()


def _env_bool_value(raw: Any, default: bool = False) -> bool:
    normalized = str(raw).strip().lower()
    if normalized in TRUE_ENV_VALUES:
        return True
    if normalized in FALSE_ENV_VALUES or normalized == "":
        return False
    return default


def is_production_environment() -> bool:
    return str(os.getenv("ENVIRONMENT", "")).strip().lower() in PRODUCTION_ENVIRONMENTS


def is_auth_secret_production_ready(secret: Optional[str] = None) -> bool:
    value = os.getenv("AUTH_SECRET", "") if secret is None else str(secret or "")
    return bool(value.strip()) and value != DEFAULT_AUTH_SECRET


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off", ""}
