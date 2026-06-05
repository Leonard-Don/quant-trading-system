"""Tests for the data-source health surfaced by ``/system/providers/status``.

The provider-status endpoint embeds Tushare's classified ``health_check`` result
plus a ``degraded`` flag so the frontend can show a green/amber/red dot. The
result is cached server-side (~60s) so the lightweight indicator poll does not
add Tushare rate-limit pressure.

No live network: ``health_check`` is always mocked. ``TUSHARE_TOKEN`` is blanked
and the cache is reset in setup so these stay deterministic.
"""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import system
from backend.app.core.error_handler import register_exception_handlers


@pytest.fixture(autouse=True)
def _isolate_datasource_health(monkeypatch):
    # Blank the token so nothing resolves a real client, and clear the
    # server-side health cache so each test starts cold (else flaky).
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TS_TOKEN", raising=False)
    system._reset_tushare_health_cache()
    yield
    system._reset_tushare_health_cache()


def _client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(system.router, prefix="/system")
    return TestClient(app)


class _FakeTushare:
    name = "tushare"

    def __init__(self, result, *, calls):
        self._result = result
        self._calls = calls

    def health_check(self):
        self._calls.append(1)
        return self._result


class _FakeFactory:
    def __init__(self, tushare):
        self.providers = {"tushare": tushare} if tushare is not None else {}

    def get_provider_runtime_status(self):
        return {}


class _FakeDataManager:
    def __init__(self, tushare):
        self.provider_factory = _FakeFactory(tushare)


def _install(monkeypatch, *, result, calls=None):
    calls = calls if calls is not None else []
    tushare = _FakeTushare(result, calls=calls)
    monkeypatch.setattr(system, "get_data_manager", lambda: _FakeDataManager(tushare))
    # SinaIndustryAdapter.get_circuit_status is imported lazily inside the
    # endpoint; stub it so the existing branch does not need real state.
    monkeypatch.setattr(
        "src.data.providers.sina_ths_adapter.SinaIndustryAdapter.get_circuit_status",
        classmethod(lambda cls: {}),
        raising=False,
    )
    return calls


def test_status_reports_tushare_ok_not_degraded(monkeypatch):
    _install(monkeypatch, result={"ok": True, "reason": "ok", "detail": "tushare reachable"})
    client = _client()

    payload = client.get("/system/providers/status").json()

    assert payload["success"] is True
    assert payload["tushare"] == {"ok": True, "reason": "ok", "detail": "tushare reachable"}
    assert payload["degraded"] is False
    assert payload["primary_source"] == "tushare"


def test_status_reports_token_invalid_as_degraded(monkeypatch):
    _install(
        monkeypatch,
        result={"ok": False, "reason": "token_invalid", "detail": "您的token不对"},
    )
    client = _client()

    payload = client.get("/system/providers/status").json()

    assert payload["tushare"]["ok"] is False
    assert payload["tushare"]["reason"] == "token_invalid"
    assert payload["degraded"] is True


def test_status_reports_rate_limited_as_degraded(monkeypatch):
    _install(
        monkeypatch,
        result={"ok": False, "reason": "rate_limited", "detail": "每分钟最多访问"},
    )
    client = _client()

    payload = client.get("/system/providers/status").json()

    assert payload["tushare"]["reason"] == "rate_limited"
    assert payload["degraded"] is True


def test_health_check_result_is_cached(monkeypatch):
    calls = _install(
        monkeypatch, result={"ok": True, "reason": "ok", "detail": "ok"}
    )
    client = _client()

    client.get("/system/providers/status")
    client.get("/system/providers/status")
    client.get("/system/providers/status")

    # Cached within the TTL window -> health_check runs at most once.
    assert len(calls) == 1


def test_missing_tushare_provider_is_token_missing_and_degraded(monkeypatch):
    monkeypatch.setattr(system, "get_data_manager", lambda: _FakeDataManager(None))
    monkeypatch.setattr(
        "src.data.providers.sina_ths_adapter.SinaIndustryAdapter.get_circuit_status",
        classmethod(lambda cls: {}),
        raising=False,
    )
    client = _client()

    payload = client.get("/system/providers/status").json()

    assert payload["tushare"]["ok"] is False
    assert payload["tushare"]["reason"] == "token_missing"
    assert payload["degraded"] is True


def test_health_check_failure_degrades_gracefully(monkeypatch):
    class _Boom:
        name = "tushare"

        def health_check(self):
            raise RuntimeError("unexpected client explosion")

    monkeypatch.setattr(system, "get_data_manager", lambda: _FakeDataManager(_Boom()))
    monkeypatch.setattr(
        "src.data.providers.sina_ths_adapter.SinaIndustryAdapter.get_circuit_status",
        classmethod(lambda cls: {}),
        raising=False,
    )
    client = _client()

    response = client.get("/system/providers/status")

    # A health-check blowup must not 500 the status endpoint; it degrades.
    assert response.status_code == 200
    payload = response.json()
    assert payload["tushare"]["ok"] is False
    assert payload["degraded"] is True


def test_token_env_is_blanked():
    # Guard the isolation fixture itself.
    assert not os.getenv("TUSHARE_TOKEN")
