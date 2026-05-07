from collections.abc import Callable
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import analysis
from backend.app.core.error_handler import register_exception_handlers
from src.utils.cache import cache_manager


def _client_for_analysis() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(analysis.router, prefix="/analysis")
    return TestClient(app)


def _history_frame() -> pd.DataFrame:
    close = [100.0, 101.5, 102.0, 103.5, 104.0]
    return pd.DataFrame(
        {
            "open": [99.5, 100.5, 101.0, 102.5, 103.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 100.5, 102.0, 102.5],
            "close": close,
            "volume": [1000, 1100, 1050, 1200, 1250],
        },
        index=pd.date_range("2024-01-01", periods=len(close)),
    )


class EmptyDataManager:
    def get_historical_data(self, **kwargs):
        return pd.DataFrame()


class RaisingDataManager:
    def get_historical_data(self, **kwargs):
        raise RuntimeError("provider unavailable")


class StaticDataManager:
    def get_historical_data(self, **kwargs):
        return _history_frame()


TARGET_ENDPOINTS = [
    ("/analysis/analyze", "TREND_ANALYSIS_DATA_NOT_FOUND", "TREND_ANALYSIS_DATA_FETCH_FAILED"),
    (
        "/analysis/comprehensive",
        "COMPREHENSIVE_ANALYSIS_DATA_NOT_FOUND",
        "COMPREHENSIVE_ANALYSIS_DATA_FETCH_FAILED",
    ),
    ("/analysis/klines", "KLINES_DATA_NOT_FOUND", "KLINES_DATA_FETCH_FAILED"),
    (
        "/analysis/volume-price",
        "VOLUME_PRICE_DATA_NOT_FOUND",
        "VOLUME_PRICE_DATA_FETCH_FAILED",
    ),
    (
        "/analysis/sentiment",
        "SENTIMENT_ANALYSIS_DATA_NOT_FOUND",
        "SENTIMENT_ANALYSIS_DATA_FETCH_FAILED",
    ),
    (
        "/analysis/prediction",
        "PRICE_PREDICTION_DATA_NOT_FOUND",
        "PRICE_PREDICTION_DATA_FETCH_FAILED",
    ),
]


ANALYZER_FAILURES: list[
    tuple[str, str, str, Callable[[RuntimeError], SimpleNamespace]]
] = [
    (
        "/analysis/analyze",
        "trend_analyzer",
        "TREND_ANALYSIS_FAILED",
        lambda exc: SimpleNamespace(analyze_trend=lambda data: (_ for _ in ()).throw(exc)),
    ),
    (
        "/analysis/comprehensive",
        "comprehensive_scorer",
        "COMPREHENSIVE_ANALYSIS_FAILED",
        lambda exc: SimpleNamespace(
            comprehensive_analysis=lambda data, symbol, include_pattern=True: (
                _ for _ in ()
            ).throw(exc)
        ),
    ),
    (
        "/analysis/volume-price",
        "volume_analyzer",
        "VOLUME_PRICE_ANALYSIS_FAILED",
        lambda exc: SimpleNamespace(analyze=lambda data: (_ for _ in ()).throw(exc)),
    ),
    (
        "/analysis/sentiment",
        "sentiment_analyzer",
        "SENTIMENT_ANALYSIS_FAILED",
        lambda exc: SimpleNamespace(
            analyze=lambda data, symbol: (_ for _ in ()).throw(exc)
        ),
    ),
    (
        "/analysis/prediction",
        "price_predictor",
        "PRICE_PREDICTION_FAILED",
        lambda exc: SimpleNamespace(
            predict_next_days=lambda data, days, symbol: (_ for _ in ()).throw(exc)
        ),
    ),
]


@pytest.fixture(autouse=True)
def clear_analysis_cache():
    cache_manager.clear()
    yield
    cache_manager.clear()


@pytest.mark.parametrize(("path", "error_code", "_fetch_code"), TARGET_ENDPOINTS)
def test_analysis_data_endpoints_empty_history_returns_structured_not_found(
    monkeypatch, path, error_code, _fetch_code
):
    monkeypatch.setattr(analysis, "data_manager", EmptyDataManager())
    client = _client_for_analysis()

    response = client.post(path, json={"symbol": "MISSING", "interval": "1d"})

    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == error_code
    assert payload["error"]["message"] == "No data found for symbol MISSING"


@pytest.mark.parametrize(("path", "_not_found_code", "error_code"), TARGET_ENDPOINTS)
def test_analysis_data_endpoints_history_failure_returns_structured_fetch_error(
    monkeypatch, path, _not_found_code, error_code
):
    monkeypatch.setattr(analysis, "data_manager", RaisingDataManager())
    client = _client_for_analysis()

    response = client.post(path, json={"symbol": "FAIL", "interval": "1d"})

    assert response.status_code == 502
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == error_code
    assert payload["error"]["message"] == "provider unavailable"
    assert payload["error"]["details"] == {"symbol": "FAIL"}


@pytest.mark.parametrize(
    ("path", "analyzer_attr", "error_code", "factory"), ANALYZER_FAILURES
)
def test_analysis_endpoints_runtime_failures_return_structured_analysis_error(
    monkeypatch, path, analyzer_attr, error_code, factory
):
    monkeypatch.setattr(analysis, "data_manager", StaticDataManager())
    monkeypatch.setattr(analysis, analyzer_attr, factory(RuntimeError("analysis exploded")))
    client = _client_for_analysis()

    response = client.post(path, json={"symbol": "FAIL", "interval": "1d"})

    assert response.status_code == 500
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == error_code
    assert payload["error"]["message"] == "analysis exploded"
    assert payload["error"]["details"] == {"symbol": "FAIL"}
