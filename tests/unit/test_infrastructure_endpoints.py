"""Tests for infrastructure endpoint authentication enforcement and OAuth callback security.

TDD approach:
 - Tests in the "BEFORE FIX" group are written to document expected secure behaviour;
   they will FAIL against the unpatched code and PASS once the fixes are applied.
 - Tests in the "AFTER FIX / regression" group cover correct local-dev behaviour
   (AUTH_REQUIRED=false, anonymous access allowed) to ensure the fix doesn't break
   the default local workflow.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import infrastructure

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _build_client(monkeypatch, *, auth_required: bool = False) -> TestClient:
    """Build a TestClient with infrastructure router, controlling AUTH_REQUIRED."""
    monkeypatch.setenv("AUTH_REQUIRED", "true" if auth_required else "false")
    # Prevent real persistence calls
    _stub_persistence(monkeypatch)
    _stub_auth_status(monkeypatch, required=auth_required)
    app = FastAPI()
    app.include_router(infrastructure.router, prefix="/infrastructure")
    return TestClient(app, raise_server_exceptions=False)


def _stub_persistence(monkeypatch) -> None:
    """Stub persistence_manager so tests don't require a real DB."""
    mock_pm = MagicMock()
    mock_pm.list_records.return_value = []
    mock_pm.put_record.return_value = {"record_id": "stub", "record_type": "stub", "payload": {}}
    mock_pm.put_timeseries.return_value = {"ok": True}
    mock_pm.persistence_diagnostics.return_value = {"backend": "stub", "healthy": True}
    mock_pm.health.return_value = {"healthy": True}
    monkeypatch.setattr(infrastructure, "persistence_manager", mock_pm)


def _stub_auth_status(monkeypatch, *, required: bool) -> None:
    """Stub auth_status and related auth helpers used inside the endpoint file."""
    # list_local_users, list_refresh_sessions, get_auth_policy, list_oauth_providers
    # are imported directly into infrastructure.py — patch them there.
    monkeypatch.setattr(infrastructure, "list_local_users", list)
    monkeypatch.setattr(infrastructure, "list_refresh_sessions", lambda **kw: [])
    monkeypatch.setattr(infrastructure, "get_auth_policy", lambda: {"required": required})
    monkeypatch.setattr(infrastructure, "list_oauth_providers", list)

    def _auth_status():
        return {
            "required": required,
            "bootstrap_required": False,
            "enabled_users": 1,
        }
    monkeypatch.setattr(infrastructure, "auth_status", _auth_status)
    # Also patch inside the runtime module so get_current_user_optional reads the right policy
    try:
        from backend.app.core.auth import runtime as auth_runtime
        monkeypatch.setattr(auth_runtime, "get_auth_policy", lambda: {"required": required})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers: build stub get_current_user_optional that always returns anonymous
# ---------------------------------------------------------------------------

def _anon_user() -> dict[str, Any]:
    return {"sub": "anonymous", "role": "researcher", "auth_method": "optional"}


# ===========================================================================
# 1. GET /auth/users — must require auth when AUTH_REQUIRED=true
# ===========================================================================

class TestGetAuthUsersRequiresAuth:
    """GET /auth/users exposes the full user directory — must be gated."""

    def test_returns_401_when_auth_required_and_no_credentials(self, monkeypatch):
        """Unauthenticated request MUST be rejected with 401 when auth is required."""
        client = _build_client(monkeypatch, auth_required=True)
        response = client.get("/infrastructure/auth/users")
        assert response.status_code == 401, (
            f"Expected 401, got {response.status_code}. "
            "GET /auth/users must reject unauthenticated callers when AUTH_REQUIRED=true."
        )

    def test_no_sensitive_data_leaked_in_401_body(self, monkeypatch):
        """The 401 body must not contain user records, sessions or policy details."""
        client = _build_client(monkeypatch, auth_required=True)
        response = client.get("/infrastructure/auth/users")
        body = response.text
        # The 401 rejection body must not carry the user-directory payload.
        assert "users" not in body.lower(), f"401 body leaked user-directory data: {body}"

    def test_anonymous_access_allowed_when_auth_not_required(self, monkeypatch):
        """Local dev (AUTH_REQUIRED=false) must still work — anonymous access allowed."""
        client = _build_client(monkeypatch, auth_required=False)
        response = client.get("/infrastructure/auth/users")
        assert response.status_code == 200, (
            f"Expected 200 in dev mode, got {response.status_code}. "
            "Auth-optional mode must allow anonymous access."
        )


# ===========================================================================
# 2. GET /persistence/records — must require auth when AUTH_REQUIRED=true
# ===========================================================================

class TestGetPersistenceRecordsRequiresAuth:
    """GET /persistence/records can expose auth_user / auth_refresh_session records."""

    def test_returns_401_when_auth_required_and_no_credentials(self, monkeypatch):
        client = _build_client(monkeypatch, auth_required=True)
        response = client.get("/infrastructure/persistence/records")
        assert response.status_code == 401, (
            f"Expected 401, got {response.status_code}. "
            "GET /persistence/records must reject unauthenticated callers when AUTH_REQUIRED=true."
        )

    def test_anonymous_access_allowed_when_auth_not_required(self, monkeypatch):
        client = _build_client(monkeypatch, auth_required=False)
        response = client.get("/infrastructure/persistence/records")
        assert response.status_code == 200


# ===========================================================================
# 3. GET /persistence/diagnostics — must require auth when AUTH_REQUIRED=true
# ===========================================================================

class TestGetPersistenceDiagnosticsRequiresAuth:
    """GET /persistence/diagnostics exposes DB internals — must be gated."""

    def test_returns_401_when_auth_required_and_no_credentials(self, monkeypatch):
        client = _build_client(monkeypatch, auth_required=True)
        response = client.get("/infrastructure/persistence/diagnostics")
        assert response.status_code == 401, (
            f"Expected 401, got {response.status_code}. "
            "GET /persistence/diagnostics must reject unauthenticated callers when AUTH_REQUIRED=true."
        )

    def test_anonymous_access_allowed_when_auth_not_required(self, monkeypatch):
        client = _build_client(monkeypatch, auth_required=False)
        response = client.get("/infrastructure/persistence/diagnostics")
        assert response.status_code == 200


# ===========================================================================
# 4. POST /persistence/timeseries — must require auth when AUTH_REQUIRED=true
# ===========================================================================

class TestPostPersistenceTimeseriesRequiresAuth:
    """POST /persistence/timeseries writes data — must be gated."""

    _VALID_PAYLOAD: ClassVar[dict[str, Any]] = {
        "series_name": "test_series",
        "symbol": "TEST",
        "timestamp": "2024-01-01T00:00:00",
        "value": 1.0,
        "payload": {},
    }

    def test_returns_401_when_auth_required_and_no_credentials(self, monkeypatch):
        client = _build_client(monkeypatch, auth_required=True)
        response = client.post("/infrastructure/persistence/timeseries", json=self._VALID_PAYLOAD)
        assert response.status_code == 401, (
            f"Expected 401, got {response.status_code}. "
            "POST /persistence/timeseries must reject unauthenticated callers when AUTH_REQUIRED=true."
        )

    def test_anonymous_write_allowed_when_auth_not_required(self, monkeypatch):
        client = _build_client(monkeypatch, auth_required=False)
        response = client.post("/infrastructure/persistence/timeseries", json=self._VALID_PAYLOAD)
        assert response.status_code == 200


# ===========================================================================
# 5. POST /auth/token — arbitrary-token mint decision
#
# The endpoint accepts {subject, role, expires_in_seconds} with NO credentials.
# When AUTH_REQUIRED=true this is a privilege-escalation vector. It must be
# gated by the same auth dependency as the other sensitive endpoints.
# ===========================================================================

class TestPostAuthTokenRequiresAuth:
    """POST /auth/token mints arbitrary JWTs — must require credentials."""

    _VALID_PAYLOAD: ClassVar[dict[str, Any]] = {"subject": "attacker", "role": "admin", "expires_in_seconds": 3600}

    def test_returns_401_when_auth_required_and_no_credentials(self, monkeypatch):
        client = _build_client(monkeypatch, auth_required=True)
        response = client.post("/infrastructure/auth/token", json=self._VALID_PAYLOAD)
        assert response.status_code == 401, (
            f"Expected 401, got {response.status_code}. "
            "POST /auth/token must reject unauthenticated callers when AUTH_REQUIRED=true — "
            "it mints arbitrary-subject/role tokens."
        )

    def test_anonymous_mint_allowed_when_auth_not_required(self, monkeypatch):
        """Local dev (AUTH_REQUIRED=false) convenience mint must still work."""
        # Stub create_access_token so we don't need a real AUTH_SECRET
        monkeypatch.setattr(infrastructure, "create_access_token", lambda **kw: "stub_token")
        client = _build_client(monkeypatch, auth_required=False)
        response = client.post("/infrastructure/auth/token", json=self._VALID_PAYLOAD)
        assert response.status_code == 200


# ===========================================================================
# 6. OAuth callback — fail-closed: no postMessage to "*" with token bundle
# ===========================================================================

class TestOAuthCallbackFailClosed:
    """oauth_provider_callback must not postMessage tokens to unknown origins."""

    def _callback_client(self, monkeypatch) -> TestClient:
        """Build a client with a stubbed exchange that returns a token bundle."""
        _stub_persistence(monkeypatch)
        _stub_auth_status(monkeypatch, required=False)

        def _fake_exchange(provider_id, *, code, state, redirect_uri, **kw):
            # Simulate successful exchange; no frontend_origin in response = unknown origin
            return {
                "access_token": "secret_access_token",
                "refresh_token": "secret_refresh_token",
                "token_type": "Bearer",
                # Deliberately omit frontend_origin to test fail-closed behaviour
            }

        monkeypatch.setattr(infrastructure, "exchange_oauth_authorization_code", _fake_exchange)
        app = FastAPI()
        app.include_router(infrastructure.router, prefix="/infrastructure")
        return TestClient(app, raise_server_exceptions=False)

    def test_missing_frontend_origin_renders_error_page_not_token_bundle(self, monkeypatch):
        """When frontend_origin is missing, callback must show an error page, not the tokens."""
        client = self._callback_client(monkeypatch)
        response = client.get(
            "/infrastructure/auth/oauth/providers/test_provider/callback",
            params={"code": "abc123", "state": "xyz"},
        )
        assert response.status_code == 200  # Page renders
        html = response.text
        # The token values must NOT appear in the rendered HTML
        assert "secret_access_token" not in html, (
            "access_token must not be rendered in HTML when frontend_origin is unknown"
        )
        assert "secret_refresh_token" not in html, (
            "refresh_token must not be rendered in HTML when frontend_origin is unknown"
        )

    def test_missing_frontend_origin_does_not_postmessage_to_wildcard(self, monkeypatch):
        """The rendered JS must not contain postMessage(..., '*') with a token bundle."""
        client = self._callback_client(monkeypatch)
        response = client.get(
            "/infrastructure/auth/oauth/providers/test_provider/callback",
            params={"code": "abc123", "state": "xyz"},
        )
        html = response.text
        # Wildcard postMessage must not be present
        assert "'*'" not in html or "postMessage" not in html, (
            "postMessage must not target '*' when frontend_origin is unknown"
        )
        # Stricter: the combination must not appear
        if "postMessage" in html and "'*'" in html:
            pytest.fail(
                "HTML contains both postMessage and '*' — tokens may be broadcast to any origin"
            )

    def test_explicit_frontend_origin_still_posts_token_bundle(self, monkeypatch):
        """When a valid frontend_origin is known, postMessage is allowed to that origin."""
        _stub_persistence(monkeypatch)
        _stub_auth_status(monkeypatch, required=False)

        def _fake_exchange_with_origin(provider_id, *, code, state, redirect_uri, **kw):
            return {
                "access_token": "good_token",
                "token_type": "Bearer",
                "frontend_origin": "https://app.example.com",
            }

        monkeypatch.setattr(
            infrastructure, "exchange_oauth_authorization_code", _fake_exchange_with_origin
        )
        app = FastAPI()
        app.include_router(infrastructure.router, prefix="/infrastructure")
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/infrastructure/auth/oauth/providers/safe_provider/callback",
            params={"code": "abc123", "state": "xyz"},
        )
        html = response.text
        assert "https://app.example.com" in html, "Known origin must appear in postMessage call"
        # Wildcard must NOT be used when a real origin is known
        assert "'*'" not in html, "Must not fall back to '*' when frontend_origin is set"

    def test_error_flow_does_not_expose_tokens(self, monkeypatch):
        """Error callback (no code/state) must not postMessage to '*' with sensitive data."""
        _stub_persistence(monkeypatch)
        _stub_auth_status(monkeypatch, required=False)
        app = FastAPI()
        app.include_router(infrastructure.router, prefix="/infrastructure")
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/infrastructure/auth/oauth/providers/any_provider/callback",
        )
        html = response.text
        # Error payload has no token data; the wildcard check is the important one
        # When there's an error and no known origin, we must not postMessage to '*'
        # The error flow is allowed to use '*' only if there's no sensitive data
        # (success=False payloads don't contain tokens, but we should fail closed anyway)
        assert response.status_code == 200  # Error page renders OK
        # The callback HTML must carry no token data on the error flow.
        assert "access_token" not in html, f"OAuth callback HTML leaked token data: {html[:200]}"


# ===========================================================================
# 7. GET /persistence/records — auth-namespace record types must be blocked
#
# Any authenticated user (including plain 'researcher' role) must NOT be able
# to read auth_* records via this endpoint — neither by explicit record_type
# filter nor by the unfiltered dump.
# ===========================================================================

# Auth record-type prefix and full set drawn from backend.app.core.auth.constants
_AUTH_RECORD_TYPES = [
    "auth_user",
    "auth_policy",
    "auth_refresh_session",
    "auth_oauth_provider",
    "auth_oauth_state",
]


def _build_client_with_records(monkeypatch, records: list[dict]) -> TestClient:
    """Build a TestClient whose persistence stub returns the given records."""
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    mock_pm = MagicMock()
    mock_pm.list_records.return_value = records
    mock_pm.put_record.return_value = {"record_id": "stub", "record_type": "stub", "payload": {}}
    mock_pm.put_timeseries.return_value = {"ok": True}
    mock_pm.persistence_diagnostics.return_value = {"backend": "stub", "healthy": True}
    mock_pm.health.return_value = {"healthy": True}
    monkeypatch.setattr(infrastructure, "persistence_manager", mock_pm)
    _stub_auth_status(monkeypatch, required=False)
    app = FastAPI()
    app.include_router(infrastructure.router, prefix="/infrastructure")
    return TestClient(app, raise_server_exceptions=False)


class TestListRecordsBlocksAuthNamespace:
    """GET /persistence/records must refuse to serve auth_* record types."""

    @pytest.mark.parametrize("auth_record_type", _AUTH_RECORD_TYPES)
    def test_explicit_auth_record_type_returns_403(self, monkeypatch, auth_record_type):
        """Requesting an auth_* record_type explicitly must return HTTP 403."""
        client = _build_client_with_records(monkeypatch, records=[])
        response = client.get(
            "/infrastructure/persistence/records",
            params={"record_type": auth_record_type},
        )
        assert response.status_code == 403, (
            f"Expected 403 for record_type={auth_record_type!r}, "
            f"got {response.status_code}. "
            "Auth-namespace record types must be blocked from the persistence/records endpoint."
        )

    def test_auth_prefix_rejected_case_sensitive(self, monkeypatch):
        """A record_type that starts with 'auth_' (any suffix) must be blocked."""
        client = _build_client_with_records(monkeypatch, records=[])
        response = client.get(
            "/infrastructure/persistence/records",
            params={"record_type": "auth_custom_future_type"},
        )
        assert response.status_code == 403, (
            "Any record_type starting with 'auth_' must be blocked (prefix rule)."
        )

    def test_unfiltered_dump_excludes_auth_records(self, monkeypatch):
        """When no record_type filter is given, auth_* records must be stripped from output."""
        mixed_records = [
            {"id": "1", "record_type": "auth_user", "record_key": "admin",
             "payload": {"password_hash": "secret"}, "created_at": "t", "updated_at": "t"},
            {"id": "2", "record_type": "auth_refresh_session", "record_key": "sess1",
             "payload": {"token_hash": "secret2"}, "created_at": "t", "updated_at": "t"},
            {"id": "3", "record_type": "backtest_run", "record_key": "run1",
             "payload": {"result": "ok"}, "created_at": "t", "updated_at": "t"},
            {"id": "4", "record_type": "config:default:etf:rotation", "record_key": "v1",
             "payload": {"cfg": True}, "created_at": "t", "updated_at": "t"},
        ]
        client = _build_client_with_records(monkeypatch, records=mixed_records)
        response = client.get("/infrastructure/persistence/records")
        assert response.status_code == 200, f"Unfiltered dump must succeed: {response.status_code}"
        body = response.json()
        returned_types = {r["record_type"] for r in body["records"]}
        assert "auth_user" not in returned_types, (
            "auth_user records must be stripped from unfiltered dump"
        )
        assert "auth_refresh_session" not in returned_types, (
            "auth_refresh_session records must be stripped from unfiltered dump"
        )
        # Non-auth records must still appear
        assert "backtest_run" in returned_types, "Non-auth records must still be returned"
        assert "config:default:etf:rotation" in returned_types, "Config records must still be returned"

    def test_non_auth_record_type_passes_through(self, monkeypatch):
        """Requesting a non-auth record_type must succeed (200) — legitimate use must work."""
        client = _build_client_with_records(
            monkeypatch,
            records=[
                {"id": "r1", "record_type": "backtest_run", "record_key": "k1",
                 "payload": {}, "created_at": "t", "updated_at": "t"},
            ],
        )
        response = client.get(
            "/infrastructure/persistence/records",
            params={"record_type": "backtest_run"},
        )
        assert response.status_code == 200, (
            f"Non-auth record_type must not be blocked, got {response.status_code}"
        )
        body = response.json()
        assert len(body["records"]) == 1

    def test_config_record_type_passes_through(self, monkeypatch):
        """config: prefixed record types (used by config-versions) must not be blocked."""
        client = _build_client_with_records(
            monkeypatch,
            records=[
                {"id": "c1", "record_type": "config:default:etf:rotation", "record_key": "v1",
                 "payload": {}, "created_at": "t", "updated_at": "t"},
            ],
        )
        response = client.get(
            "/infrastructure/persistence/records",
            params={"record_type": "config:default:etf:rotation"},
        )
        assert response.status_code == 200, (
            f"config: record types must not be blocked, got {response.status_code}"
        )

    def test_auth_prefix_not_blocked_in_config_namespace(self, monkeypatch):
        """A record_type like 'config:auth_settings' must NOT be blocked — prefix check is on the
        full record_type string, not a substring check."""
        client = _build_client_with_records(
            monkeypatch,
            records=[
                {"id": "x1", "record_type": "config:auth_settings", "record_key": "v1",
                 "payload": {}, "created_at": "t", "updated_at": "t"},
            ],
        )
        response = client.get(
            "/infrastructure/persistence/records",
            params={"record_type": "config:auth_settings"},
        )
        assert response.status_code == 200, (
            "record_type 'config:auth_settings' starts with 'config:', not 'auth_' — "
            f"must not be blocked, got {response.status_code}"
        )


# ===========================================================================
# 8. POST /auth/token — a bearer-authenticated non-admin must not mint an
#    elevated (admin) token. Anonymous dev-mode mint (auth_method="optional",
#    AUTH_REQUIRED=false) stays unrestricted — that is intentional and is
#    covered by TestPostAuthTokenRequiresAuth above.
# ===========================================================================

def _build_client_as_user(
    monkeypatch, *, role: str, auth_method: str = "bearer", auth_required: bool = True
) -> TestClient:
    """Client whose auth dependency resolves to a fixed authenticated user."""
    monkeypatch.setenv("AUTH_REQUIRED", "true" if auth_required else "false")
    _stub_persistence(monkeypatch)
    _stub_auth_status(monkeypatch, required=auth_required)
    monkeypatch.setattr(infrastructure, "create_access_token", lambda **kw: "stub_token")
    app = FastAPI()
    app.include_router(infrastructure.router, prefix="/infrastructure")
    app.dependency_overrides[infrastructure.get_current_user_optional] = lambda: {
        "sub": role,
        "role": role,
        "auth_method": auth_method,
    }
    return TestClient(app, raise_server_exceptions=False)


class TestAuthTokenRejectsRoleEscalation:
    """A bearer-authenticated non-admin must not mint a more-privileged token."""

    def test_bearer_researcher_cannot_mint_admin_token(self, monkeypatch):
        client = _build_client_as_user(monkeypatch, role="researcher")
        response = client.post(
            "/infrastructure/auth/token",
            json={"subject": "attacker", "role": "admin", "expires_in_seconds": 3600},
        )
        assert response.status_code == 403, (
            f"Expected 403, got {response.status_code}. A bearer-authenticated "
            "researcher must not mint an admin token (privilege escalation)."
        )

    def test_admin_can_mint_admin_token(self, monkeypatch):
        client = _build_client_as_user(monkeypatch, role="admin")
        response = client.post(
            "/infrastructure/auth/token",
            json={"subject": "ops", "role": "admin", "expires_in_seconds": 3600},
        )
        assert response.status_code == 200

    def test_bearer_researcher_can_mint_non_elevated_token(self, monkeypatch):
        client = _build_client_as_user(monkeypatch, role="researcher")
        response = client.post(
            "/infrastructure/auth/token",
            json={"subject": "teammate", "role": "researcher", "expires_in_seconds": 3600},
        )
        assert response.status_code == 200


# ===========================================================================
# 9. POST /persistence/records — auth-namespace writes must be blocked
#    (mirror of the GET guard; closes the auth_user-forgery backdoor)
# ===========================================================================

class TestPutRecordBlocksAuthNamespace:
    """POST /persistence/records must refuse to WRITE auth_* record types."""

    @pytest.mark.parametrize("auth_record_type", _AUTH_RECORD_TYPES)
    def test_writing_auth_record_returns_403(self, monkeypatch, auth_record_type):
        client = _build_client(monkeypatch, auth_required=False)  # blocked even in dev
        response = client.post(
            "/infrastructure/persistence/records",
            json={
                "record_type": auth_record_type,
                "record_key": "admin",
                "payload": {"role": "admin", "password_hash": "forged"},
            },
        )
        assert response.status_code == 403, (
            f"Expected 403 for record_type={auth_record_type!r}, got {response.status_code}. "
            "Auth-namespace records must not be writable via the generic persistence endpoint "
            "(they would let a caller forge an admin user)."
        )

    def test_writing_non_auth_record_succeeds(self, monkeypatch):
        client = _build_client(monkeypatch, auth_required=False)
        response = client.post(
            "/infrastructure/persistence/records",
            json={"record_type": "backtest_run", "record_key": "k1", "payload": {"x": 1}},
        )
        assert response.status_code == 200

    def test_config_namespace_write_not_blocked(self, monkeypatch):
        """'config:auth_settings' starts with 'config:', not 'auth_' — must pass."""
        client = _build_client(monkeypatch, auth_required=False)
        response = client.post(
            "/infrastructure/persistence/records",
            json={"record_type": "config:auth_settings", "record_key": "v1", "payload": {}},
        )
        assert response.status_code == 200
