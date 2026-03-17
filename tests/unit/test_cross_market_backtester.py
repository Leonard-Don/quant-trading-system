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
    assert results["price_matrix_summary"]["asset_count"] == 2
    assert len(results["portfolio_curve"]) == 12


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
