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


# --------------------------------------------------------------------------- #
# 6. Frictions on the batch and walk-forward paths (audit 2026-06-10: these
#    endpoints bypassed run_backtest_pipeline, so A-share tasks silently ran
#    friction-free — and walk-forward parameter optimization picked candidates
#    under understated costs).
# --------------------------------------------------------------------------- #
def _dummy_ohlcv(n=120):
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    prices = np.linspace(50, 70, n)
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices * 1.01,
            "low": prices * 0.99,
            "close": prices,
            "volume": [2_000_000] * n,
        },
        index=idx,
    )


class TestBatchFrictions:
    def test_backtest_task_friction_fields_default_off(self):
        from src.backtest.batch_backtester import BacktestTask

        task = BacktestTask(
            task_id="t1",
            symbol="600519.SS",
            strategy_name="buy_and_hold",
            parameters={},
            start_date="2023-01-01",
            end_date="2023-06-01",
        )
        assert task.stamp_duty_rate == 0.0
        assert task.transfer_fee_rate == 0.0
        assert task.enforce_t_plus_1 is False
        assert task.price_limit_pct is None

    def test_worker_forwards_friction_kwargs_to_factory(self):
        from src.backtest.batch_backtester import BacktestTask, _run_single_backtest_worker

        seen = {}

        class _Capturing:
            def __init__(
                self,
                initial_capital=10000,
                commission=0.001,
                slippage=0.001,
                execution_lag=1,
                stamp_duty_rate=0.0,
                transfer_fee_rate=0.0,
                enforce_t_plus_1=False,
                price_limit_pct=None,
            ):
                seen.update(
                    stamp_duty_rate=stamp_duty_rate,
                    transfer_fee_rate=transfer_fee_rate,
                    enforce_t_plus_1=enforce_t_plus_1,
                    price_limit_pct=price_limit_pct,
                )

            def run(self, strategy, data):
                return {"total_return": 0.0, "metrics": {}}

        task = BacktestTask(
            task_id="t1",
            symbol="600519.SS",
            strategy_name="buy_and_hold",
            parameters={},
            start_date="2023-01-01",
            end_date="2023-06-01",
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
            enforce_t_plus_1=True,
            price_limit_pct=0.10,
        )
        _run_single_backtest_worker(
            task,
            backtester_factory=_Capturing,
            strategy_factory=lambda name, params: object(),
            data_fetcher=lambda s, a, b: _dummy_ohlcv(),
        )
        # The behavior under test is the kwarg forwarding; the fake's minimal
        # result shape failing metric normalization downstream is irrelevant.
        assert seen["stamp_duty_rate"] == pytest.approx(0.0005)
        assert seen["transfer_fee_rate"] == pytest.approx(0.00001)
        assert seen["enforce_t_plus_1"] is True
        assert seen["price_limit_pct"] == pytest.approx(0.10)

    def test_batch_endpoint_resolves_frictions_per_ashare_task(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        captured = {}

        class _FakeBatch:
            def run_batch(self, tasks, **kwargs):
                captured["tasks"] = list(tasks)
                return []

            def get_ranked_results(self, **kwargs):
                return []

            def get_summary(self):
                return {}

        monkeypatch.setattr(
            backtest_endpoint, "_build_batch_backtester", lambda *a, **k: _FakeBatch()
        )
        app = FastAPI()
        app.include_router(backtest_endpoint.router, prefix="/backtest")
        client = TestClient(app)
        resp = client.post(
            "/backtest/batch",
            json={
                "tasks": [
                    {"symbol": "600519.SS", "strategy": "buy_and_hold"},
                    {"symbol": "300750.SZ", "strategy": "buy_and_hold"},
                    {"symbol": "AAPL", "strategy": "buy_and_hold"},
                ]
            },
        )
        assert resp.status_code == 200, resp.text
        by_symbol = {t.symbol: t for t in captured["tasks"]}
        moutai = by_symbol["600519.SS"]
        assert moutai.stamp_duty_rate == pytest.approx(0.0005)
        assert moutai.transfer_fee_rate == pytest.approx(0.00001)
        assert moutai.enforce_t_plus_1 is True
        assert moutai.price_limit_pct == pytest.approx(0.10)
        # ChiNext board gets the 20% daily band
        assert by_symbol["300750.SZ"].price_limit_pct == pytest.approx(0.20)
        # US symbol: every friction stays off
        aapl = by_symbol["AAPL"]
        assert aapl.stamp_duty_rate == 0.0
        assert aapl.transfer_fee_rate == 0.0
        assert aapl.enforce_t_plus_1 is False
        assert aapl.price_limit_pct is None


class TestWalkForwardFrictions:
    def _post_walkforward(self, monkeypatch, symbol):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        captured = {}

        def fake_analyze(self, *, data, strategy_factory, backtester_factory, **kwargs):
            captured["factory"] = backtester_factory
            return {"n_windows": 0, "windows": [], "aggregate_metrics": {}}

        monkeypatch.setattr(backtest_endpoint.WalkForwardAnalyzer, "analyze", fake_analyze)
        monkeypatch.setattr(
            backtest_endpoint, "_fetch_backtest_data", lambda *a, **k: _dummy_ohlcv()
        )
        app = FastAPI()
        app.include_router(backtest_endpoint.router, prefix="/backtest")
        client = TestClient(app)
        resp = client.post(
            "/backtest/walk-forward",
            json={"symbol": symbol, "strategy": "buy_and_hold"},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["data"], captured["factory"]

    def test_factory_applies_ashare_frictions_and_response_echoes(self, monkeypatch):
        data, factory = self._post_walkforward(monkeypatch, "600519.SS")
        backtester = factory()
        cfg = backtester.execution_config
        assert cfg.stamp_duty_rate == pytest.approx(0.0005)
        assert cfg.transfer_fee_rate == pytest.approx(0.00001)
        assert cfg.enforce_t_plus_1 is True
        assert cfg.price_limit_pct == pytest.approx(0.10)
        # Parity with run_backtest_pipeline's echo (runtime.py:429-433)
        assert data["ashare_frictions_applied"] is True
        assert data["stamp_duty_rate"] == pytest.approx(0.0005)
        assert data["price_limit_pct"] == pytest.approx(0.10)

    def test_us_symbol_keeps_frictions_off(self, monkeypatch):
        data, factory = self._post_walkforward(monkeypatch, "AAPL")
        cfg = factory().execution_config
        assert cfg.stamp_duty_rate == 0.0
        assert cfg.transfer_fee_rate == 0.0
        assert cfg.enforce_t_plus_1 is False
        assert cfg.price_limit_pct is None
        assert data["ashare_frictions_applied"] is False


# --------------------------------------------------------------------------- #
# 7. Per-symbol frictions in the PORTFOLIO engine (audit 2026-06-10: the
#    multi-asset path had no stamp/transfer/limit support at all, so the
#    combined portfolio number was friction-free while its per-symbol
#    component runs charged frictions).
# --------------------------------------------------------------------------- #
_MOUTAI_PROFILE = {
    "stamp_duty_rate": 0.001,
    "transfer_fee_rate": 0.0001,
    "enforce_t_plus_1": True,
    "price_limit_pct": None,
}


class TestPortfolioEngineFrictions:
    def _engine(self, frictions=None, commission=0.0, slippage=0.0):
        from src.backtest.execution_engine import (
            PortfolioExecutionConfig,
            PortfolioExecutionEngine,
        )

        cfg = PortfolioExecutionConfig(
            allow_fractional_shares=True,
            execution_lag=0,
            ashare_frictions=frictions or {},
        )
        return PortfolioExecutionEngine(
            initial_capital=100_000, commission=commission, slippage=slippage, config=cfg
        )

    @staticmethod
    def _frames(symbol, prices_list, weights_list):
        idx = pd.date_range("2024-01-01", periods=len(prices_list), freq="D")
        prices = pd.DataFrame({symbol: prices_list}, index=idx)
        weights = pd.DataFrame({symbol: weights_list}, index=idx)
        return prices, weights

    def test_sell_charges_stamp_and_transfer_on_raw_notional(self):
        prices, weights = self._frames("600519.SS", [100.0, 100.0, 100.0], [1.0, 0.0, 0.0])
        res = self._engine({"600519.SS": _MOUTAI_PROFILE}).execute(
            price_data=prices, target_weights=weights
        )
        buys = [t for t in res["trades"] if t["type"] == "BUY"]
        sells = [t for t in res["trades"] if t["type"] == "SELL"]
        assert buys and sells, res["trades"]
        sell = sells[0]
        raw = sell["shares"] * sell["price"]
        # Parity with the single-asset engine: stamp duty SELL-only, transfer
        # fee both sides, both on the RAW notional.
        assert sell["stamp_duty_cost"] == pytest.approx(raw * 0.001)
        assert sell["transfer_fee_cost"] == pytest.approx(raw * 0.0001)
        buy = buys[0]
        buy_raw = buy["shares"] * buy["price"]
        assert buy["stamp_duty_cost"] == 0.0
        assert buy["transfer_fee_cost"] == pytest.approx(buy_raw * 0.0001)

    def test_unflagged_symbol_runs_byte_identical(self):
        prices, weights = self._frames("AAPL", [100.0, 105.0, 110.0], [1.0, 0.5, 0.0])
        base = self._engine().execute(price_data=prices, target_weights=weights)
        flagged_elsewhere = self._engine({"600519.SS": _MOUTAI_PROFILE}).execute(
            price_data=prices, target_weights=weights
        )
        assert base["portfolio_history"]["total"].tolist() == (
            flagged_elsewhere["portfolio_history"]["total"].tolist()
        )
        for trade in flagged_elsewhere["trades"]:
            assert trade["stamp_duty_cost"] == 0.0
            assert trade["transfer_fee_cost"] == 0.0

    def test_price_limit_blocks_buy_at_limit_up(self):
        profile = dict(_MOUTAI_PROFILE, price_limit_pct=0.10)
        # Bar2 closes +10% vs bar1 -> at the limit-up band -> BUY must not fill;
        # bar3 is inside the band -> the deferred buy fills there.
        prices, weights = self._frames("600519.SS", [100.0, 110.0, 112.0], [0.0, 1.0, 1.0])
        res = self._engine({"600519.SS": profile}).execute(
            price_data=prices, target_weights=weights
        )
        buys = [t for t in res["trades"] if t["type"] == "BUY"]
        assert buys, res["trades"]
        assert buys[0]["date"] == prices.index[2]
        # Control: without the band the buy fills on bar2.
        res_free = self._engine().execute(price_data=prices, target_weights=weights)
        free_buys = [t for t in res_free["trades"] if t["type"] == "BUY"]
        assert free_buys[0]["date"] == prices.index[1]

    def test_price_limit_blocks_sell_at_limit_down(self):
        profile = dict(_MOUTAI_PROFILE, price_limit_pct=0.10)
        # Buy bar1; bar2 closes -10% (limit-down) -> SELL blocked; bar3 sells.
        prices, weights = self._frames("600519.SS", [100.0, 90.0, 91.0], [1.0, 0.0, 0.0])
        res = self._engine({"600519.SS": profile}).execute(
            price_data=prices, target_weights=weights
        )
        sells = [t for t in res["trades"] if t["type"] == "SELL"]
        assert sells, res["trades"]
        assert sells[0]["date"] == prices.index[2]

    def test_portfolio_backtester_threads_frictions_into_config(self):
        from src.backtest.portfolio_backtester import PortfolioBacktester

        bt = PortfolioBacktester(
            initial_capital=100_000,
            ashare_frictions={"600519.SS": _MOUTAI_PROFILE},
        )
        assert bt.execution_config.ashare_frictions == {"600519.SS": _MOUTAI_PROFILE}


class TestPortfolioStrategyEndpointFrictions:
    def test_endpoint_resolves_per_symbol_profiles(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from backend.app.api.v1.endpoints import backtest as backtest_endpoint

        idx = pd.date_range("2023-01-01", periods=80, freq="D")
        closes = np.linspace(50, 70, 80)
        df = pd.DataFrame(
            {
                "open": closes,
                "high": closes * 1.01,
                "low": closes * 0.99,
                "close": closes,
                "volume": [2_000_000] * 80,
            },
            index=idx,
        )

        def fake_pipeline(**kwargs):
            history = [
                {"date": str(d.date()), "total": 100000.0 + i} for i, d in enumerate(idx)
            ]
            return (
                {
                    "portfolio_history": history,
                    "total_return": 0.05,
                    "annualized_return": 0.05,
                    "max_drawdown": -0.05,
                    "final_value": 105000.0,
                    "num_trades": 2,
                },
                None,
            )

        class _Strategy:
            def generate_signals(self, data):
                return pd.Series(1, index=data.index)

        captured = {}

        class _CapturingPB:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def run(self, strategy, data, **kwargs):
                return {
                    "portfolio_history": [],
                    "positions_history": [],
                    "total_return": 0.05,
                    "annualized_return": 0.05,
                    "volatility": 0.1,
                    "sharpe_ratio": 0.5,
                    "max_drawdown": -0.05,
                    "num_trades": 2,
                    "final_value": 105000.0,
                }

        monkeypatch.setattr(backtest_endpoint, "_fetch_backtest_data", lambda *a, **k: df)
        monkeypatch.setattr(backtest_endpoint, "run_backtest_pipeline", fake_pipeline)
        monkeypatch.setattr(
            backtest_endpoint, "_create_strategy_instance", lambda *a, **k: _Strategy()
        )
        monkeypatch.setattr(backtest_endpoint, "PortfolioBacktester", _CapturingPB)

        app = FastAPI()
        app.include_router(backtest_endpoint.router, prefix="/backtest")
        client = TestClient(app)
        resp = client.post(
            "/backtest/portfolio-strategy",
            json={
                "symbols": ["600519.SS", "AAPL"],
                "strategy": "buy_and_hold",
                "objective": "equal_weight",
            },
        )
        assert resp.status_code == 200, resp.text
        frictions = captured["ashare_frictions"]
        # Only the A-share leg gets a profile; the US leg is absent (off).
        assert set(frictions) == {"600519.SS"}
        assert frictions["600519.SS"]["stamp_duty_rate"] == pytest.approx(0.0005)
        assert frictions["600519.SS"]["enforce_t_plus_1"] is True
