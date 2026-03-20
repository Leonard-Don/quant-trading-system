from datetime import datetime

import pandas as pd
import pytest

from src.backtest.cross_market_backtester import CrossMarketBacktester
from src.trading.cross_market import AssetSide, AssetUniverse, SpreadZScoreStrategy


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


def test_asset_universe_normalizes_weights_by_side():
    universe = AssetUniverse(
        [
            {"symbol": "xlu", "asset_class": "ETF", "side": "long"},
            {"symbol": "duk", "asset_class": "US_STOCK", "side": "long"},
            {"symbol": "qqq", "asset_class": "ETF", "side": "short", "weight": 3},
            {"symbol": "arkk", "asset_class": "ETF", "side": "short", "weight": 1},
        ]
    )

    long_assets = universe.get_assets(AssetSide.LONG)
    short_assets = universe.get_assets(AssetSide.SHORT)

    assert [asset.symbol for asset in long_assets] == ["XLU", "DUK"]
    assert round(sum(asset.weight for asset in long_assets), 6) == 1.0
    assert round(sum(asset.weight for asset in short_assets), 6) == 1.0
    assert short_assets[0].weight == 0.75
    assert short_assets[1].weight == 0.25
    summary = universe.summary()
    assert summary["asset_count"] == 4
    assert summary["by_side"]["long"] == 2
    assert summary["by_asset_class"]["ETF"] == 3
    assert summary["execution_channels"]["cash_equity"] == 4
    assert long_assets[0].market == "USA"
    assert long_assets[0].preferred_provider == "us_stock"


def test_asset_universe_requires_both_sides():
    with pytest.raises(ValueError, match="both long and short"):
        AssetUniverse(
            [
                {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
                {"symbol": "DUK", "asset_class": "US_STOCK", "side": "long"},
            ]
        )


def test_spread_zscore_strategy_opens_and_closes_positions():
    dates = pd.date_range("2024-01-01", periods=12, freq="D")
    price_matrix = pd.DataFrame(
        {
            "XLU": [100, 100, 100, 100, 100, 130, 135, 100, 100, 100, 100, 100],
            "QQQ": [100] * 12,
        },
        index=dates,
    )
    universe = AssetUniverse(
        [
            {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
            {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
        ]
    )

    strategy = SpreadZScoreStrategy()
    signals = strategy.generate_cross_signals(
        price_matrix=price_matrix,
        asset_specs=universe.get_assets(),
        parameters={"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
    )

    assert "z_score" in signals.columns
    assert (signals["signal"] == -1).any()
    assert (signals["position"] == -1).any()
    assert signals["position"].iloc[-1] == 0


def test_cross_market_backtester_returns_expected_sections():
    frames = {
        "XLU": _price_frame([100, 101, 102, 104, 108, 115, 118, 112, 109, 105, 103, 101]),
        "QQQ": _price_frame([100, 100, 99, 98, 97, 96, 95, 97, 99, 101, 102, 103]),
    }
    backtester = CrossMarketBacktester(
        data_manager=DummyDataManager(frames),
        initial_capital=100000,
        commission=0.0005,
        slippage=0.0005,
    )

    results = backtester.run(
        assets=[
            {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
            {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
        ],
        template_context={
            "template_id": "utilities_vs_growth",
            "template_name": "US utilities vs NASDAQ growth",
            "allocation_mode": "macro_bias",
            "bias_summary": "多头增配 XLU，空头增配 QQQ",
            "bias_strength": 6.5,
            "base_assets": [
                {"symbol": "XLU", "asset_class": "ETF", "side": "long", "weight": 0.45},
                {"symbol": "QQQ", "asset_class": "ETF", "side": "short", "weight": 0.55},
            ],
        },
        strategy_name="spread_zscore",
        parameters={"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
        min_history_days=10,
    )

    assert "price_matrix_summary" in results
    assert "spread_series" in results
    assert "leg_performance" in results
    assert "correlation_matrix" in results
    assert "data_alignment" in results
    assert "execution_diagnostics" in results
    assert "asset_universe" in results
    assert "hedge_portfolio" in results
    assert "asset_contributions" in results
    assert "execution_plan" in results
    assert results["price_matrix_summary"]["asset_count"] == 2
    assert len(results["portfolio_curve"]) == 12
    assert results["asset_universe"]["by_side"]["long"] == 1
    assert "XLU" in results["asset_contributions"]
    assert results["hedge_portfolio"]["gross_exposure"] > 0
    assert results["data_alignment"]["per_symbol"][0]["provider"].startswith("mock_")
    assert results["execution_plan"]["route_count"] == 2
    assert results["execution_diagnostics"]["route_count"] == 2
    assert results["execution_plan"]["initial_capital"] == 100000
    assert all(route["target_notional"] > 0 for route in results["execution_plan"]["routes"])
    assert round(sum(route["capital_fraction"] for route in results["execution_plan"]["routes"]), 6) == 1.0
    assert results["execution_diagnostics"]["batch_count"] == len(results["execution_plan"]["batches"])
    assert results["execution_diagnostics"]["provider_count"] == len(results["execution_plan"]["by_provider"])
    assert results["execution_diagnostics"]["concentration_level"] in {"balanced", "moderate", "high"}
    assert results["execution_plan"]["provider_allocation"][0]["target_notional"] > 0
    assert results["execution_plan"]["largest_batch"]["target_notional"] > 0
    assert results["execution_plan"]["routes"][0]["rounded_quantity"] >= 1
    assert results["execution_plan"]["routes"][0]["reference_price"] > 0
    assert results["execution_plan"]["sizing_summary"]["lot_efficiency"] > 0
    assert results["execution_diagnostics"]["suggested_rebalance"] in {"weekly", "biweekly", "monthly"}
    assert len(results["execution_plan"]["execution_stress"]["scenarios"]) == 4
    assert results["execution_plan"]["execution_stress"]["worst_case"]["largest_batch_notional"] > 0
    assert results["execution_diagnostics"]["stress_test_flag"] in {"balanced", "moderate", "high"}
    assert results["allocation_overlay"]["allocation_mode"] == "macro_bias"
    assert results["allocation_overlay"]["rows"][0]["effective_weight"] >= 0
    assert results["allocation_overlay"]["max_delta_weight"] >= 0


def test_cross_market_backtester_uses_tradable_mask():
    frames = {
        "XLU": _price_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111]),
        "QQQ": _price_frame([100, 99, 98, 97, 96, 95, 94, 93, 92, 91], start="2024-01-03"),
    }
    backtester = CrossMarketBacktester(data_manager=DummyDataManager(frames))

    results = backtester.run(
        assets=[
            {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
            {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
        ],
        strategy_name="spread_zscore",
        parameters={"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
        min_history_days=10,
        min_overlap_ratio=0.7,
    )

    assert results["data_alignment"]["dropped_dates_count"] == 2
    assert results["data_alignment"]["aligned_row_count"] == 10


def test_cross_market_backtester_rejects_short_history():
    frames = {
        "XLU": _price_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109]),
        "QQQ": _price_frame([100, 99, 98, 97, 96, 95, 94, 93, 92, 91]),
    }
    backtester = CrossMarketBacktester(data_manager=DummyDataManager(frames))

    with pytest.raises(ValueError, match="need at least 20"):
        backtester.run(
            assets=[
                {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
                {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
            ],
            strategy_name="spread_zscore",
            parameters={"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
            min_history_days=20,
        )


def test_cross_market_backtester_returns_hedge_ratio_series_for_ols_mode():
    frames = {
        "XLU": _price_frame([100, 101, 102, 103, 104, 106, 108, 110, 111, 112, 113, 114, 115, 116]),
        "QQQ": _price_frame([100, 100, 101, 101, 102, 103, 104, 104, 105, 106, 107, 108, 109, 110]),
    }
    backtester = CrossMarketBacktester(data_manager=DummyDataManager(frames))

    results = backtester.run(
        assets=[
            {"symbol": "XLU", "asset_class": "ETF", "side": "long"},
            {"symbol": "QQQ", "asset_class": "ETF", "side": "short"},
        ],
        strategy_name="spread_zscore",
        parameters={"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
        construction_mode="ols_hedge",
        min_history_days=10,
    )

    assert "hedge_ratio_series" in results
    assert len(results["hedge_ratio_series"]) == results["price_matrix_summary"]["row_count"]
    assert results["execution_diagnostics"]["construction_mode"] == "ols_hedge"
    assert results["hedge_portfolio"]["hedge_ratio"]["average"] > 0


def test_cross_market_backtester_uses_asset_class_aware_fetch_metadata():
    frames = {
        "HG=F": _price_frame([100, 102, 103, 101, 105, 110, 108, 107, 109, 111, 114, 116]),
        "SOXX": _price_frame([100, 99, 101, 103, 102, 101, 100, 98, 97, 96, 95, 94]),
    }
    backtester = CrossMarketBacktester(data_manager=DummyDataManager(frames))

    results = backtester.run(
        assets=[
            {"symbol": "HG=F", "asset_class": "COMMODITY_FUTURES", "side": "long"},
            {"symbol": "SOXX", "asset_class": "ETF", "side": "short"},
        ],
        strategy_name="spread_zscore",
        parameters={"lookback": 5, "entry_threshold": 1.0, "exit_threshold": 0.2},
        min_history_days=10,
    )

    symbol_rows = {item["symbol"]: item for item in results["data_alignment"]["per_symbol"]}
    assert symbol_rows["HG=F"]["asset_class"] == "COMMODITY_FUTURES"
    assert symbol_rows["HG=F"]["provider"] == "mock_commodity_futures"
    assert symbol_rows["SOXX"]["provider"] == "mock_etf"
    assert results["execution_plan"]["batches"][0]["preferred_provider"] in {"commodity", "us_stock"}
    assert any(batch["target_notional"] > 0 for batch in results["execution_plan"]["batches"])
    assert results["execution_plan"]["venue_allocation"][0]["target_notional"] > 0
    assert all(route["capacity_band"] in {"light", "moderate", "heavy"} for route in results["execution_plan"]["routes"])
