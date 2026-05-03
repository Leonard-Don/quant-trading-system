"""Authentication policy persistence helpers."""

from __future__ import annotations

import os
import time
from typing import Any

from backend.app.core.persistence import persistence_manager

from .constants import AUTH_POLICY_RECORD_TYPE
from .secrets import _env_auth_required, _env_bool_value, is_production_environment


def _load_policy() -> dict[str, Any]:
    records = persistence_manager.list_records(record_type=AUTH_POLICY_RECORD_TYPE, limit=1)
    payload = (records[0].get("payload") or {}) if records else {}
    required = bool(payload.get("required", _env_auth_required()))
    production_mode = is_production_environment()
    if production_mode and not _env_bool_value(
        os.getenv("AUTH_ALLOW_ANONYMOUS_IN_PRODUCTION"), default=False
    ):
        required = True
    return {
        "required": required,
        "mode": "local_jwt",
        "production_enforced": production_mode and required,
        "updated_at": payload.get("updated_at")
        or (records[0].get("updated_at") if records else None),
        "updated_by": payload.get("updated_by"),
        "note": (
            "Authentication is required for protected API calls"
            if required
            else "Authentication is optional; anonymous research access is allowed"
        ),
    }


def get_auth_policy() -> dict[str, Any]:
    return _load_policy()


def update_auth_policy(required: bool, updated_by: str = "system") -> dict[str, Any]:
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
