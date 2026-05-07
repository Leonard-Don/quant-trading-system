import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import cross_market, market_data, optimization
from backend.app.core.error_handler import register_exception_handlers


def _client_for(router, prefix: str) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix=prefix)
    return TestClient(app)


def test_market_data_provider_failure_uses_structured_error(monkeypatch):
    class RaisingDataManager:
        def get_historical_data(self, **kwargs):
            raise RuntimeError("provider offline")

    monkeypatch.setattr(market_data, "data_manager", RaisingDataManager())
    client = _client_for(market_data.router, "/market-data")

    response = client.post("/market-data/", json={"symbol": "AAPL"})

    assert response.status_code == 500
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "MARKET_DATA_FETCH_FAILED"
    assert payload["error"]["message"] == "provider offline"


def test_market_data_empty_result_keeps_not_found_semantics(monkeypatch):
    class EmptyDataManager:
        def get_historical_data(self, **kwargs):
            return pd.DataFrame()

    monkeypatch.setattr(market_data, "data_manager", EmptyDataManager())
    client = _client_for(market_data.router, "/market-data")

    response = client.post("/market-data/", json={"symbol": "MISSING"})

    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "MARKET_DATA_NOT_FOUND"
    assert payload["error"]["message"] == "No data found for symbol MISSING"


def test_market_data_invalid_date_uses_structured_validation_error(monkeypatch):
    client = _client_for(market_data.router, "/market-data")

    response = client.post(
        "/market-data/",
        json={"symbol": "AAPL", "start_date": "not-a-date"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "MARKET_DATA_INVALID_REQUEST"
    assert "Invalid isoformat string" in payload["error"]["message"]


def test_optimization_data_failure_uses_structured_error(monkeypatch):
    class RaisingDataManager:
        def get_historical_data(self, *args, **kwargs):
            raise RuntimeError("warehouse unavailable")

    monkeypatch.setattr(optimization, "data_manager", RaisingDataManager())
    client = _client_for(optimization.router, "/optimization")

    response = client.post(
        "/optimization/optimize",
        json={"symbols": ["AAPL", "MSFT"]},
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "PORTFOLIO_OPTIMIZATION_FAILED"
    assert payload["error"]["message"] == "warehouse unavailable"


def test_optimization_solver_failure_uses_structured_error(monkeypatch):
    prices = pd.DataFrame(
        {"close": [100.0, 101.0, 102.0]},
        index=pd.date_range("2024-01-01", periods=3),
    )

    class StaticDataManager:
        def get_historical_data(self, *args, **kwargs):
            return prices.copy()

    class FailingOptimizer:
        def optimize_portfolio(self, historical_prices, objective):
            return {"success": False, "error": "solver failed"}

    monkeypatch.setattr(optimization, "data_manager", StaticDataManager())
    monkeypatch.setattr(optimization, "optimizer", FailingOptimizer())
    client = _client_for(optimization.router, "/optimization")

    response = client.post(
        "/optimization/optimize",
        json={"symbols": ["AAPL", "MSFT"]},
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "PORTFOLIO_OPTIMIZATION_FAILED"
    assert payload["error"]["message"] == "solver failed"


def test_cross_market_runtime_failure_uses_structured_error(monkeypatch):
    class RaisingBacktester:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            raise RuntimeError("engine unavailable")

    monkeypatch.setattr(cross_market, "CrossMarketBacktester", RaisingBacktester)
    client = _client_for(cross_market.router, "/cross-market")

    response = client.post(
        "/cross-market/backtest",
        json={
            "assets": [
                {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
                {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
            ],
            "strategy": "spread_zscore",
        },
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "CROSS_MARKET_BACKTEST_FAILED"
    assert payload["error"]["message"] == "engine unavailable"
