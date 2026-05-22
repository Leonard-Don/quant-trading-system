"""
Tests that 500 response bodies do NOT contain raw Python exception strings.

Covers the "error-detail leakage" issue: endpoints that called
`raise HTTPException(status_code=500, detail=str(e))` directly forwarded
internal exception messages (file paths, library internals) to HTTP clients.

After the fix each such endpoint must:
  1. Return HTTP 500 with a generic client-safe message.
  2. NOT include the raw exception text in the response body.
"""
from __future__ import annotations

import asyncio

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import analysis, backtest
from backend.app.core.error_handler import register_exception_handlers
from src.utils.cache import cache_manager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INTERNAL_MESSAGE = "Internal server error"
# A string that would appear in raw exception detail but must NOT appear in
# the sanitised response body.
_RAW_EXCEPTION_FRAGMENT = "secret internal path"


def _client_for_analysis() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(analysis.router, prefix="/analysis")
    return TestClient(app, raise_server_exceptions=False)


def _history_frame() -> pd.DataFrame:
    close = [100.0 + i for i in range(120)]
    return pd.DataFrame(
        {
            "open": [c - 0.5 for c in close],
            "high": [c + 1.0 for c in close],
            "low": [c - 1.0 for c in close],
            "close": close,
            "volume": [1000 + i * 10 for i in range(120)],
        },
        index=pd.date_range("2024-01-01", periods=120),
    )


class _StaticDataManager:
    def get_historical_data(self, **_kwargs):
        return _history_frame()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    cache_manager.clear()
    yield
    cache_manager.clear()


# ---------------------------------------------------------------------------
# analysis.py — 10 endpoints with detail=str(e)
# ---------------------------------------------------------------------------


def test_fundamental_analysis_does_not_leak_exception_detail(monkeypatch):
    """analyze_fundamental must not include raw exception text in 500 body."""
    monkeypatch.setattr(analysis, "data_manager", _StaticDataManager())
    monkeypatch.setattr(
        analysis.fundamental_analyzer,
        "analyze",
        lambda symbol: (_ for _ in ()).throw(
            RuntimeError(f"internal: {_RAW_EXCEPTION_FRAGMENT}")
        ),
    )
    client = _client_for_analysis()

    resp = client.post("/analysis/fundamental", json={"symbol": "X", "interval": "1d"})

    assert resp.status_code == 500
    body = resp.text
    assert _RAW_EXCEPTION_FRAGMENT not in body
    assert _INTERNAL_MESSAGE in body


def test_pattern_recognition_does_not_leak_exception_detail(monkeypatch):
    """recognize_patterns must not include raw exception text in 500 body."""
    monkeypatch.setattr(analysis, "data_manager", _StaticDataManager())
    monkeypatch.setattr(
        analysis.pattern_recognizer,
        "recognize_patterns",
        lambda data: (_ for _ in ()).throw(
            RuntimeError(f"internal: {_RAW_EXCEPTION_FRAGMENT}")
        ),
    )
    client = _client_for_analysis()

    resp = client.post("/analysis/patterns", json={"symbol": "X", "interval": "1d"})

    assert resp.status_code == 500
    body = resp.text
    assert _RAW_EXCEPTION_FRAGMENT not in body
    assert _INTERNAL_MESSAGE in body


def test_correlation_analysis_does_not_leak_exception_detail(monkeypatch):
    """analyze_correlation must not include raw exception text in 500 body.

    The endpoint catches per-symbol fetch errors silently; to trigger the
    broad except at the bottom we need to fail a computation step AFTER the
    data has been collected (e.g. the pd.DataFrame.corr() step).
    """
    import pandas as _pd

    def _good_data(**_kwargs):
        close = [100.0 + i for i in range(40)]
        return _pd.DataFrame(
            {"close": close},
            index=_pd.date_range("2024-01-01", periods=40),
        )

    monkeypatch.setattr(analysis.data_manager, "get_historical_data", _good_data)

    # Patch pct_change on DataFrame to blow up during correlation computation
    orig_pct_change = _pd.DataFrame.pct_change

    def _boom_pct_change(self, *args, **kwargs):
        result = orig_pct_change(self, *args, **kwargs)
        raise RuntimeError(f"internal: {_RAW_EXCEPTION_FRAGMENT}")

    monkeypatch.setattr(_pd.DataFrame, "pct_change", _boom_pct_change)

    client = _client_for_analysis()

    resp = client.post(
        "/analysis/correlation",
        json={"symbols": ["A", "B"], "period_days": 30},
    )

    assert resp.status_code == 500
    body = resp.text
    assert _RAW_EXCEPTION_FRAGMENT not in body
    assert _INTERNAL_MESSAGE in body


def test_prediction_compare_does_not_leak_exception_detail(monkeypatch):
    """compare_model_predictions must not include raw exception text in 500 body."""
    monkeypatch.setattr(analysis, "data_manager", _StaticDataManager())
    monkeypatch.setattr(
        analysis.model_comparator,
        "compare_predictions",
        lambda data, symbol, n: (_ for _ in ()).throw(
            RuntimeError(f"internal: {_RAW_EXCEPTION_FRAGMENT}")
        ),
    )
    client = _client_for_analysis()

    resp = client.post("/analysis/prediction/compare", json={"symbol": "X", "interval": "1d"})

    assert resp.status_code == 500
    body = resp.text
    assert _RAW_EXCEPTION_FRAGMENT not in body
    assert _INTERNAL_MESSAGE in body


def test_lstm_prediction_does_not_leak_exception_detail(monkeypatch):
    """predict_with_lstm must not include raw exception text in 500 body."""
    monkeypatch.setattr(analysis, "data_manager", _StaticDataManager())

    import sys
    import types

    # Stub out the lazy import inside predict_with_lstm
    fake_lstm = types.SimpleNamespace(
        predict=lambda data, symbol, days: (_ for _ in ()).throw(
            RuntimeError(f"internal: {_RAW_EXCEPTION_FRAGMENT}")
        )
    )
    fake_module = types.ModuleType("src.analytics.lstm_predictor")
    fake_module.lstm_predictor = fake_lstm
    monkeypatch.setitem(sys.modules, "src.analytics.lstm_predictor", fake_module)

    client = _client_for_analysis()

    resp = client.post("/analysis/prediction/lstm", json={"symbol": "X", "interval": "1d"})

    assert resp.status_code == 500
    body = resp.text
    assert _RAW_EXCEPTION_FRAGMENT not in body
    assert _INTERNAL_MESSAGE in body


def test_train_all_models_does_not_leak_exception_detail(monkeypatch):
    """train_all_models must not include raw exception text in 500 body."""
    monkeypatch.setattr(analysis, "data_manager", _StaticDataManager())
    monkeypatch.setattr(
        analysis.model_comparator,
        "train_all_models",
        lambda data, symbol: (_ for _ in ()).throw(
            RuntimeError(f"internal: {_RAW_EXCEPTION_FRAGMENT}")
        ),
    )
    client = _client_for_analysis()

    resp = client.post("/analysis/train/all", json={"symbol": "X", "interval": "1d"})

    assert resp.status_code == 500
    body = resp.text
    assert _RAW_EXCEPTION_FRAGMENT not in body
    assert _INTERNAL_MESSAGE in body


def test_technical_indicators_does_not_leak_exception_detail(monkeypatch):
    """get_technical_indicators must not include raw exception text in 500 body."""
    monkeypatch.setattr(analysis, "data_manager", _StaticDataManager())
    monkeypatch.setattr(
        analysis,
        "calculate_rsi",
        lambda data: (_ for _ in ()).throw(
            RuntimeError(f"internal: {_RAW_EXCEPTION_FRAGMENT}")
        ),
    )
    client = _client_for_analysis()

    resp = client.post("/analysis/technical-indicators", json={"symbol": "X", "interval": "1d"})

    assert resp.status_code == 500
    body = resp.text
    assert _RAW_EXCEPTION_FRAGMENT not in body
    assert _INTERNAL_MESSAGE in body


def test_sentiment_history_does_not_leak_exception_detail(monkeypatch):
    """get_sentiment_history must not include raw exception text in 500 body."""

    def _raise(**_kwargs):
        raise RuntimeError(f"internal: {_RAW_EXCEPTION_FRAGMENT}")

    monkeypatch.setattr(analysis.data_manager, "get_historical_data", _raise)
    client = _client_for_analysis()

    resp = client.post("/analysis/sentiment-history", json={"symbol": "X", "interval": "1d"})

    assert resp.status_code == 500
    body = resp.text
    assert _RAW_EXCEPTION_FRAGMENT not in body
    assert _INTERNAL_MESSAGE in body


def test_industry_comparison_does_not_leak_exception_detail(monkeypatch):
    """get_industry_comparison must not include raw exception text in 500 body."""
    monkeypatch.setattr(
        analysis.fundamental_analyzer,
        "analyze",
        lambda symbol: (_ for _ in ()).throw(
            RuntimeError(f"internal: {_RAW_EXCEPTION_FRAGMENT}")
        ),
    )
    client = _client_for_analysis()

    resp = client.post("/analysis/industry-comparison", json={"symbol": "X", "interval": "1d"})

    assert resp.status_code == 500
    body = resp.text
    assert _RAW_EXCEPTION_FRAGMENT not in body
    assert _INTERNAL_MESSAGE in body


def test_risk_metrics_does_not_leak_exception_detail(monkeypatch):
    """get_risk_metrics must not include raw exception text in 500 body."""

    def _raise(**_kwargs):
        raise RuntimeError(f"internal: {_RAW_EXCEPTION_FRAGMENT}")

    monkeypatch.setattr(analysis.data_manager, "get_historical_data", _raise)
    client = _client_for_analysis()

    resp = client.post("/analysis/risk-metrics", json={"symbol": "X", "interval": "1d"})

    assert resp.status_code == 500
    body = resp.text
    assert _RAW_EXCEPTION_FRAGMENT not in body
    assert _INTERNAL_MESSAGE in body


# ---------------------------------------------------------------------------
# backtest.py:1036 — generate_report
# ---------------------------------------------------------------------------


def test_generate_report_does_not_leak_exception_detail(monkeypatch):
    """generate_report must raise HTTPException with generic detail, not str(e)."""

    def _raise_report_error(*args, **kwargs):
        raise RuntimeError(f"internal: {_RAW_EXCEPTION_FRAGMENT}")

    monkeypatch.setattr(backtest, "_build_report_pdf", _raise_report_error)

    from fastapi import HTTPException as _HTTPException

    with pytest.raises(_HTTPException) as exc_info:
        asyncio.run(backtest.generate_report(backtest.ReportRequest(symbol="AAPL", strategy="buy_and_hold")))

    assert exc_info.value.status_code == 500
    assert _RAW_EXCEPTION_FRAGMENT not in str(exc_info.value.detail)
    assert exc_info.value.detail == _INTERNAL_MESSAGE
