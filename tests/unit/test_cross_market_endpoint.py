from fastapi import FastAPI
from fastapi.testclient import TestClient
import pandas as pd

from backend.app.api.v1.endpoints import cross_market


def _price_frame(values, start="2024-01-01"):
    dates = pd.date_range(start=start, periods=len(values), freq="D")
    prices = pd.Series(values, index=dates)
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": 1_000_000,
        }
    )


class DummyDataManager:
    def __init__(self, frames):
        self.frames = frames

    def get_historical_data(self, symbol, start_date=None, end_date=None, interval="1d", period=None):
        return self.frames.get(symbol, pd.DataFrame()).copy()


def _build_client(monkeypatch, frames):
    app = FastAPI()
    app.include_router(cross_market.router, prefix="/cross-market")
    monkeypatch.setattr(cross_market, "_get_data_manager", lambda: DummyDataManager(frames))
    return TestClient(app)


def test_cross_market_endpoint_success(monkeypatch):
    client = _build_client(
        monkeypatch,
        {
            "XLU": _price_frame([100, 101, 102, 104, 108, 115, 118, 112, 109, 105, 103, 101]),
            "QQQ": _price_frame([100, 100, 99, 98, 97, 96, 95, 97, 99, 101, 102, 103]),
        },
    )

    response = client.post(
        "/cross-market/backtest",
        json={
            "assets": [
                {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
                {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
            ],
            "strategy": "spread_zscore",
            "parameters": {"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
            "min_history_days": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "spread_series" in payload["data"]
    assert "asset_universe" in payload["data"]
    assert "hedge_portfolio" in payload["data"]
    assert "asset_contributions" in payload["data"]


def test_cross_market_endpoint_requires_both_sides(monkeypatch):
    client = _build_client(
        monkeypatch,
        {"XLU": _price_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109])},
    )

    response = client.post(
        "/cross-market/backtest",
        json={
            "assets": [
                {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
                {"symbol": "DUK", "asset_class": "US_STOCK", "side": "long"},
            ],
            "strategy": "spread_zscore",
        },
    )

    assert response.status_code == 400


def test_cross_market_endpoint_rejects_unknown_values_with_400(monkeypatch):
    client = _build_client(
        monkeypatch,
        {
            "XLU": _price_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109]),
            "QQQ": _price_frame([100, 99, 98, 97, 96, 95, 94, 93, 92, 91]),
        },
    )

    bad_asset_class = client.post(
        "/cross-market/backtest",
        json={
            "assets": [
                {"symbol": "XLU", "asset_class": "UNKNOWN", "side": "long"},
                {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
            ],
            "strategy": "spread_zscore",
        },
    )
    assert bad_asset_class.status_code == 400

    bad_strategy = client.post(
        "/cross-market/backtest",
        json={
            "assets": [
                {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
                {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
            ],
            "strategy": "unknown_strategy",
        },
    )
    assert bad_strategy.status_code == 400


def test_cross_market_endpoint_returns_alignment_error(monkeypatch):
    client = _build_client(
        monkeypatch,
        {
            "XLU": _price_frame([100, 101, 102, 103, 104, 105], start="2024-01-01"),
            "QQQ": _price_frame([100, 99, 98, 97, 96, 95], start="2024-03-01"),
        },
    )

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

    assert response.status_code == 400
    assert "aligned" in response.json()["detail"].lower()


def test_cross_market_endpoint_supports_ols_hedge(monkeypatch):
    client = _build_client(
        monkeypatch,
        {
            "XLU": _price_frame([100, 101, 102, 103, 104, 106, 108, 110, 111, 112, 113, 114, 115, 116]),
            "QQQ": _price_frame([100, 100, 101, 101, 102, 103, 104, 104, 105, 106, 107, 108, 109, 110]),
        },
    )

    response = client.post(
        "/cross-market/backtest",
        json={
            "assets": [
                {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
                {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
            ],
            "strategy": "spread_zscore",
            "construction_mode": "ols_hedge",
            "parameters": {"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
            "min_history_days": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "hedge_ratio_series" in payload["data"]
    assert payload["data"]["execution_diagnostics"]["construction_mode"] == "ols_hedge"


def test_cross_market_endpoint_rejects_low_overlap_ratio(monkeypatch):
    client = _build_client(
        monkeypatch,
        {
            "XLU": _price_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113], start="2024-01-01"),
            "QQQ": _price_frame([100, 99, 98, 97, 96, 95, 94, 93, 92, 91], start="2024-01-05"),
        },
    )

    response = client.post(
        "/cross-market/backtest",
        json={
            "assets": [
                {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
                {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
            ],
            "strategy": "spread_zscore",
            "min_history_days": 10,
            "min_overlap_ratio": 0.95,
        },
    )

    assert response.status_code == 400
    assert "overlap ratio" in response.json()["detail"].lower()
