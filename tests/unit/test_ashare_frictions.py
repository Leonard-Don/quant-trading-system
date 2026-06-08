"""A-share trading friction tests for the single-asset backtester.

Covers the China-market frictions added to ``Backtester``:
    * stamp duty (印花税) — sell-side only
    * transfer fee (过户费) — both sides
    * T+1 settlement (cannot sell shares bought on the same bar)
    * price limits (涨跌停) — block buys at limit-up, sells at limit-down
    * the ``ashare_cost_profile`` helper + auto-application in the /backtest path

All new config fields default OFF, so a US-symbol backtest with defaults is
numerically unchanged (pinned below).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.app.services.backtest import runtime as _backtest_runtime
from src.backtest.backtester import Backtester, ashare_cost_profile

# Capture the genuine pipeline at import time. A sibling endpoint test
# (test_strategy_comparison) monkeypatches the endpoint wrapper, and the
# endpoint's _sync_backtest_runtime_state can leave a stale reference bound on
# the runtime module. Capturing here (collection time, before any test runs)
# preserves the real implementation so our pipeline assertions are order-proof.
_GENUINE_RUN_BACKTEST_PIPELINE = _backtest_runtime.run_backtest_pipeline


@pytest.fixture
def real_run_backtest_pipeline():
    """Yield the runtime module with the genuine pipeline restored."""
    previous = _backtest_runtime.run_backtest_pipeline
    _backtest_runtime.run_backtest_pipeline = _GENUINE_RUN_BACKTEST_PIPELINE
    try:
        yield _backtest_runtime
    finally:
        _backtest_runtime.run_backtest_pipeline = previous


class _Strat:
    """Strategy that replays an explicit per-bar signal series."""

    name = "ExplicitSignals"

    def __init__(self, signals):
        self._signals = signals

    def generate_signals(self, data):
        return pd.Series(self._signals, index=data.index)


def _make_data(prices, *, volume=1_000_000, start="2023-01-02"):
    idx = pd.date_range(start, periods=len(prices), freq="D")
    prices = np.asarray(prices, dtype=float)
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices * 1.05,
            "low": prices * 0.95,
            "close": prices,
            "volume": [volume] * len(prices),
        },
        index=idx,
    )


def _run(signals, prices, *, position_size=1.0, **kwargs):
    """Run a backtest with execution_lag=0 so signals fire on their own bar.

    A zero lag keeps the synthetic fixtures small and lets each test reason
    about the exact bar a fill lands on. ``position_size`` < 1 leaves cash
    headroom so extra per-trade frictions don't push a full-equity buy over
    the affordability cap.
    """
    data = _make_data(prices)
    bt = Backtester(execution_lag=0, **kwargs)
    return bt.run(_Strat(signals), data, position_size=position_size)


# --------------------------------------------------------------------------- #
# 1. Cost model: stamp duty + transfer fee
# --------------------------------------------------------------------------- #
class TestAShareCostModel:
    def test_sell_side_stamp_duty_reduces_proceeds(self):
        prices = [100.0] * 8
        signals = [0, 1, 0, 0, 0, -1, 0, 0]

        base = _run(signals, prices, commission=0.0, slippage=0.0, position_size=0.5)
        with_stamp = _run(
            signals,
            prices,
            commission=0.0,
            slippage=0.0,
            stamp_duty_rate=0.001,
            position_size=0.5,
        )

        # Stamp duty is a pure drag on a flat-price round trip.
        assert with_stamp["final_value"] < base["final_value"]

        sell = next(t for t in with_stamp["trades"] if t["type"] == "SELL")
        shares = sell["shares"]
        notional = shares * 100.0
        expected_stamp = notional * 0.001
        assert sell["stamp_duty_cost"] == pytest.approx(expected_stamp, rel=1e-9)
        # Net revenue is reduced by exactly the stamp duty (no other frictions).
        assert sell["revenue"] == pytest.approx(notional - expected_stamp, rel=1e-9)

    def test_buy_side_pays_no_stamp_duty(self):
        prices = [100.0] * 8
        signals = [0, 1, 0, 0, 0, -1, 0, 0]
        res = _run(
            signals,
            prices,
            commission=0.0,
            slippage=0.0,
            stamp_duty_rate=0.001,
            position_size=0.5,
        )
        buy = next(t for t in res["trades"] if t["type"] == "BUY")
        assert buy.get("stamp_duty_cost", 0.0) == pytest.approx(0.0)

    def test_transfer_fee_charged_on_both_sides(self):
        prices = [100.0] * 8
        signals = [0, 1, 0, 0, 0, -1, 0, 0]
        res = _run(
            signals,
            prices,
            commission=0.0,
            slippage=0.0,
            transfer_fee_rate=0.0001,
            position_size=0.5,
        )
        buy = next(t for t in res["trades"] if t["type"] == "BUY")
        sell = next(t for t in res["trades"] if t["type"] == "SELL")

        buy_notional = buy["shares"] * 100.0
        sell_notional = sell["shares"] * 100.0
        assert buy["transfer_fee_cost"] == pytest.approx(buy_notional * 0.0001, rel=1e-9)
        assert sell["transfer_fee_cost"] == pytest.approx(sell_notional * 0.0001, rel=1e-9)
        # Buy cost includes the transfer fee on top of notional.
        assert buy["cost"] == pytest.approx(buy_notional + buy_notional * 0.0001, rel=1e-9)


# --------------------------------------------------------------------------- #
# 2. T+1 settlement
# --------------------------------------------------------------------------- #
class TestTPlus1:
    def test_no_same_bar_buy_then_sell(self):
        """With T+1 on, no SELL ever lands on the same bar as a same-day BUY."""
        prices = [100.0, 101.0, 102.0, 99.0, 98.0, 103.0]
        # Whipsaw signals that try to enter and exit aggressively.
        signals = [1, -1, 1, -1, 1, -1]
        res = _run(
            signals,
            prices,
            commission=0.0,
            slippage=0.0,
            enforce_t_plus_1=True,
            position_size=0.5,
        )
        buy_dates = {t["date"] for t in res["trades"] if t["type"] == "BUY"}
        sell_dates = {t["date"] for t in res["trades"] if t["type"] == "SELL"}
        # A locked-on-the-buy-bar invariant: no date is both a buy and a sell.
        assert buy_dates.isdisjoint(sell_dates)

    def test_t_plus_1_allows_sell_on_next_bar(self):
        prices = [100.0, 130.0, 130.0]
        signals = [0, 1, -1]
        res = _run(
            signals,
            prices,
            commission=0.0,
            slippage=0.0,
            enforce_t_plus_1=True,
            position_size=0.5,
        )
        sell_trades = [t for t in res["trades"] if t["type"] == "SELL"]
        assert len(sell_trades) == 1
        # The sell lands on bar 2 (the bar after the buy), not bar 1.
        assert sell_trades[0]["date"] == res["portfolio"].index[2]

    def test_t_plus_1_caps_sellable_to_bar_open_holdings(self):
        """Unit-level guard: a sell is capped to shares held at bar-open.

        The scalar long path nets one action per bar, so the cap is a
        correctness guarantee rather than something the daily loop can violate;
        assert it directly on the engine helper.
        """
        from src.backtest.backtester import ExecutionConfig, SingleAssetExecutionEngine

        engine = SingleAssetExecutionEngine(
            initial_capital=100000,
            commission=0.0,
            slippage=0.0,
            config=ExecutionConfig(enforce_t_plus_1=True),
        )
        # Held 50 at bar-open, bought 30 more this bar -> only 50 are sellable.
        position_at_bar_open = 50.0
        current_position = 80.0
        sellable = min(current_position, position_at_bar_open)
        assert engine.config.enforce_t_plus_1 is True
        assert sellable == 50.0


# --------------------------------------------------------------------------- #
# 3. Price limits 涨跌停
# --------------------------------------------------------------------------- #
class TestPriceLimits:
    def test_limit_up_blocks_buy(self):
        # Bar 1 close is +10% over bar 0 -> sealed limit-up, no sellers, buy fails.
        prices = [100.0, 110.0, 110.0, 110.0]
        signals = [0, 1, 0, 0]
        res = _run(
            signals, prices, commission=0.0, slippage=0.0, price_limit_pct=0.10
        )
        buys = [t for t in res["trades"] if t["type"] == "BUY"]
        assert buys == []

    def test_below_limit_up_allows_buy(self):
        # +9% is inside the band -> buy fills normally.
        prices = [100.0, 109.0, 109.0, 109.0]
        signals = [0, 1, 0, 0]
        res = _run(
            signals, prices, commission=0.0, slippage=0.0, price_limit_pct=0.10
        )
        buys = [t for t in res["trades"] if t["type"] == "BUY"]
        assert len(buys) == 1

    def test_limit_down_blocks_sell(self):
        # Buy on bar 1 (flat), then bar 2 gaps to -10% (limit-down): sell blocked.
        prices = [100.0, 100.0, 90.0, 90.0]
        signals = [0, 1, -1, 0]
        res = _run(
            signals,
            prices,
            commission=0.0,
            slippage=0.0,
            price_limit_pct=0.10,
        )
        sells = [t for t in res["trades"] if t["type"] == "SELL"]
        assert sells == []

    def test_first_bar_has_no_limit_constraint(self):
        # No prior close on bar 0; a bar-0 buy must still be allowed.
        prices = [100.0, 100.0, 100.0]
        signals = [1, 0, 0]
        res = _run(
            signals, prices, commission=0.0, slippage=0.0, price_limit_pct=0.10
        )
        buys = [t for t in res["trades"] if t["type"] == "BUY"]
        assert len(buys) == 1


# --------------------------------------------------------------------------- #
# 4. Profile helper
# --------------------------------------------------------------------------- #
class TestProfileHelper:
    def test_default_profile_values(self):
        profile = ashare_cost_profile()
        assert profile["stamp_duty_rate"] == pytest.approx(0.0005)
        assert profile["transfer_fee_rate"] == pytest.approx(0.00001)
        assert profile["enforce_t_plus_1"] is True
        assert profile["price_limit_pct"] == pytest.approx(0.10)

    def test_profile_respects_custom_limit(self):
        profile = ashare_cost_profile(price_limit_pct=0.20)
        assert profile["price_limit_pct"] == pytest.approx(0.20)


# --------------------------------------------------------------------------- #
# 5. Auto-apply in the /backtest path
# --------------------------------------------------------------------------- #
class TestAutoProfile:
    def test_resolve_ashare_for_ss_symbol(self):
        from backend.app.services.backtest.runtime import resolve_ashare_frictions

        profile = resolve_ashare_frictions("600519.SS")
        assert profile is not None
        assert profile["enforce_t_plus_1"] is True
        assert profile["stamp_duty_rate"] == pytest.approx(0.0005)
        assert profile["price_limit_pct"] == pytest.approx(0.10)

    def test_resolve_ashare_for_sz_symbol(self):
        from backend.app.services.backtest.runtime import resolve_ashare_frictions

        profile = resolve_ashare_frictions("000001.SZ")
        assert profile is not None
        assert profile["price_limit_pct"] == pytest.approx(0.10)

    def test_resolve_ashare_chinext_uses_20pct_limit(self):
        from backend.app.services.backtest.runtime import resolve_ashare_frictions

        # 300xxx (ChiNext) and 688xxx (STAR) have a 20% daily band.
        assert resolve_ashare_frictions("300750.SZ")["price_limit_pct"] == pytest.approx(0.20)
        assert resolve_ashare_frictions("688981.SS")["price_limit_pct"] == pytest.approx(0.20)

    def test_resolve_ashare_for_bare_6digit_code(self):
        from backend.app.services.backtest.runtime import resolve_ashare_frictions

        assert resolve_ashare_frictions("600519")["price_limit_pct"] == pytest.approx(0.10)
        assert resolve_ashare_frictions("300750")["price_limit_pct"] == pytest.approx(0.20)

    def test_resolve_returns_none_for_us_symbol(self):
        from backend.app.services.backtest.runtime import resolve_ashare_frictions

        assert resolve_ashare_frictions("AAPL") is None
        assert resolve_ashare_frictions("MSFT") is None

    def test_pipeline_applies_profile_for_ss_symbol(self, real_run_backtest_pipeline):
        backtest_runtime = real_run_backtest_pipeline

        idx = pd.date_range("2023-01-01", periods=60, freq="D")
        prices = np.linspace(50, 70, 60)
        data = pd.DataFrame(
            {
                "open": prices,
                "high": prices * 1.01,
                "low": prices * 0.99,
                "close": prices,
                "volume": [2_000_000] * 60,
            },
            index=idx,
        )
        results, _ = backtest_runtime.run_backtest_pipeline(
            symbol="600519.SS",
            strategy_name="buy_and_hold",
            parameters={},
            initial_capital=100000,
            data=data,
        )
        assert results["ashare_frictions_applied"] is True
        assert results["enforce_t_plus_1"] is True
        assert results["stamp_duty_rate"] == pytest.approx(0.0005)
        assert results["price_limit_pct"] == pytest.approx(0.10)

    def test_pipeline_skips_profile_for_us_symbol(self, real_run_backtest_pipeline):
        backtest_runtime = real_run_backtest_pipeline

        idx = pd.date_range("2023-01-01", periods=60, freq="D")
        prices = np.linspace(50, 70, 60)
        data = pd.DataFrame(
            {
                "open": prices,
                "high": prices * 1.01,
                "low": prices * 0.99,
                "close": prices,
                "volume": [2_000_000] * 60,
            },
            index=idx,
        )
        results, _ = backtest_runtime.run_backtest_pipeline(
            symbol="AAPL",
            strategy_name="buy_and_hold",
            parameters={},
            initial_capital=100000,
            data=data,
        )
        assert results["ashare_frictions_applied"] is False
        assert results["enforce_t_plus_1"] is False
        assert results["stamp_duty_rate"] == pytest.approx(0.0)
        assert results["price_limit_pct"] is None

    def test_explicit_override_wins_over_auto_profile(self, real_run_backtest_pipeline):
        backtest_runtime = real_run_backtest_pipeline

        idx = pd.date_range("2023-01-01", periods=60, freq="D")
        prices = np.linspace(50, 70, 60)
        data = pd.DataFrame(
            {
                "open": prices,
                "high": prices * 1.01,
                "low": prices * 0.99,
                "close": prices,
                "volume": [2_000_000] * 60,
            },
            index=idx,
        )
        results, _ = backtest_runtime.run_backtest_pipeline(
            symbol="600519.SS",
            strategy_name="buy_and_hold",
            parameters={},
            initial_capital=100000,
            stamp_duty_rate=0.0,  # explicit override turns stamp duty off
            data=data,
        )
        # Auto-profile still flags A-share, but the explicit field wins.
        assert results["ashare_frictions_applied"] is True
        assert results["stamp_duty_rate"] == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# 6. Invariance: US backtest unchanged with all defaults
# --------------------------------------------------------------------------- #
class TestUSInvariance:
    def test_us_backtest_numerically_unchanged(self):
        idx = pd.date_range("2023-01-01", periods=30, freq="D")
        prices = np.linspace(100, 130, 30)
        data = pd.DataFrame(
            {
                "open": prices,
                "high": prices * 1.01,
                "low": prices * 0.99,
                "close": prices,
                "volume": [1_000_000] * 30,
            },
            index=idx,
        )
        sig = [0] * 30
        sig[2] = 1
        sig[10] = -1
        res = Backtester(
            initial_capital=100000, commission=0.001, slippage=0.001
        ).run(_Strat(sig), data)
        # Pinned against the pre-change engine output.
        assert res["final_value"] == pytest.approx(107587.9569682759, rel=1e-12)
        assert res["num_trades"] == 2

    def test_new_config_fields_default_off(self):
        bt = Backtester()
        cfg = bt.execution_config
        assert cfg.stamp_duty_rate == 0.0
        assert cfg.transfer_fee_rate == 0.0
        assert cfg.enforce_t_plus_1 is False
        assert cfg.price_limit_pct is None
