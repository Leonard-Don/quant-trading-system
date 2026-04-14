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

    def get_cross_market_historical_data(
        self,
        symbol,
        asset_class,
        start_date=None,
        end_date=None,
        interval="1d",
    ):
        return {
            "data": self.frames.get(symbol, pd.DataFrame()).copy(),
            "provider": f"mock_{str(asset_class).lower()}",
            "asset_class": asset_class,
            "symbol": symbol,
        }


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
            "template_context": {
                "template_id": "utilities_vs_growth",
                "template_name": "US utilities vs NASDAQ growth",
                "allocation_mode": "macro_bias",
                "bias_summary": "多头增配 XLU，空头增配 QQQ",
                "bias_strength_raw": 11.8,
                "bias_strength": 6.5,
                "bias_scale": 0.55,
                "bias_quality_label": "compressed",
                "bias_quality_reason": "正文抓取脆弱源 ndrc，宏观偏置已收缩",
                "base_recommendation_score": 3.1,
                "recommendation_score": 2.65,
                "base_recommendation_tier": "优先部署",
                "recommendation_tier": "重点跟踪",
                "ranking_penalty": 0.45,
                "ranking_penalty_reason": "核心腿 XLU 已进入压缩焦点，模板排序自动降级",
                "base_assets": [
                    {"symbol": "XLU", "asset_class": "ETF", "side": "long", "weight": 0.45},
                    {"symbol": "QQQ", "asset_class": "ETF", "side": "short", "weight": 0.55},
                ],
                "raw_bias_assets": [
                    {"symbol": "XLU", "asset_class": "ETF", "side": "long", "weight": 0.518},
                    {"symbol": "QQQ", "asset_class": "ETF", "side": "short", "weight": 0.482},
                ],
            },
            "allocation_constraints": {
                "max_single_weight": 1.0,
            },
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
    assert "execution_plan" in payload["data"]
    assert payload["data"]["data_alignment"]["per_symbol"][0]["provider"].startswith("mock_")
    assert payload["data"]["execution_diagnostics"]["route_count"] == 2
    assert payload["data"]["execution_plan"]["routes"][0]["target_notional"] > 0
    assert payload["data"]["execution_plan"]["routes"][0]["adv_usage"] > 0
    assert payload["data"]["execution_plan"]["routes"][0]["margin_requirement"] > 0
    assert payload["data"]["execution_diagnostics"]["concentration_level"] in {"balanced", "moderate", "high"}
    assert payload["data"]["execution_diagnostics"]["liquidity_level"] in {"comfortable", "watch", "stretched", "unknown"}
    assert payload["data"]["execution_diagnostics"]["margin_level"] in {"manageable", "elevated", "aggressive"}
    assert payload["data"]["execution_diagnostics"]["beta_level"] in {"balanced", "watch", "stretched", "unknown"}
    assert payload["data"]["execution_diagnostics"]["calendar_level"] in {"aligned", "watch", "stretched"}
    assert "provider_allocation" in payload["data"]["execution_plan"]
    assert "liquidity_summary" in payload["data"]["execution_plan"]
    assert "margin_summary" in payload["data"]["execution_plan"]
    assert "calendar_diagnostics" in payload["data"]["data_alignment"]
    assert "beta_neutrality" in payload["data"]["hedge_portfolio"]
    assert payload["data"]["execution_plan"]["routes"][0]["rounded_quantity"] >= 1
    assert payload["data"]["execution_diagnostics"]["suggested_rebalance"] in {"weekly", "biweekly", "monthly"}
    assert len(payload["data"]["execution_plan"]["execution_stress"]["scenarios"]) == 4
    assert payload["data"]["allocation_overlay"]["allocation_mode"] == "macro_bias"
    assert payload["data"]["allocation_overlay"]["bias_strength_raw"] == 11.8
    assert payload["data"]["allocation_overlay"]["bias_strength"] == 6.5
    assert payload["data"]["allocation_overlay"]["bias_quality_label"] == "compressed"
    assert payload["data"]["allocation_overlay"]["bias_compression_effect"] > 0
    assert payload["data"]["allocation_overlay"]["compression_summary"]["label"] == "compressed"
    assert payload["data"]["allocation_overlay"]["selection_quality"]["label"] == "auto_downgraded"
    assert payload["data"]["allocation_overlay"]["selection_quality"]["effective_recommendation_score"] == 2.65
    assert payload["data"]["allocation_overlay"]["selection_quality"]["ranking_penalty"] == 0.45
    assert payload["data"]["allocation_overlay"]["compressed_asset_count"] >= 1
    assert "compression_delta" in payload["data"]["allocation_overlay"]["rows"][0]
    assert "constraint_overlay" in payload["data"]


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


def test_cross_market_endpoint_rejects_infeasible_constraints(monkeypatch):
    client = _build_client(
        monkeypatch,
        {
            "XLU": _price_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109]),
            "QQQ": _price_frame([100, 99, 98, 97, 96, 95, 94, 93, 92, 91]),
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
            "allocation_constraints": {
                "max_single_weight": 0.4,
            },
            "min_history_days": 10,
        },
    )

    assert response.status_code == 400
    assert "infeasible" in response.json()["detail"].lower()


def test_cross_market_templates_include_macro_linkage_metadata(monkeypatch):
    client = _build_client(monkeypatch, {})

    response = client.get("/cross-market/templates")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["templates"]) >= 8
    first = payload["templates"][0]
    assert "theme" in first
    assert "theme_core" in first
    assert "theme_support" in first
    assert "execution_posture" in first
    assert "narrative" in first
    assert "linked_factors" in first
    assert "linked_dimensions" in first
    assert isinstance(first["linked_factors"], list)
    template_ids = {item["id"] for item in payload["templates"]}
    assert "people_decay_short_vs_cashflow_defensive" in template_ids
    assert "rates_pressure_vs_duration_tech" in template_ids
    assert "dollar_squeeze_vs_china_beta" in template_ids
