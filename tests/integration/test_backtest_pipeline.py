"""End-to-end pipeline test: ``DataManager`` → ``Strategy`` → ``Backtester``.

Validates that the three modules' interfaces fit together — DataManager's
output shape matches what Strategy.generate_signals expects, and that in
turn matches what Backtester.run consumes. No network, no provider SDKs.

This complements ``test_backtest_perf.py`` (which only exercises the
Backtester+Strategy boundary with pre-built DataFrames) and the per-provider
unit tests (which never touch the backtester).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.backtest.backtester import Backtester
from src.data.data_manager import DataManager
from src.strategy.strategies import MovingAverageCrossover


# ---------------------------------------------------------------------------
# Synthetic data
# ---------------------------------------------------------------------------


def _synthetic_ohlcv(periods: int = 252, seed: int = 42) -> pd.DataFrame:
    """Reproducible OHLCV with realistic noise. Mirrors test_backtest_perf style."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=periods, freq="B")
    returns = rng.normal(0.0005, 0.018, size=periods)
    close = 100.0 * np.cumprod(1.0 + returns)
    high = close * (1.0 + np.abs(rng.normal(0.002, 0.001, size=periods)))
    low = close * (1.0 - np.abs(rng.normal(0.002, 0.001, size=periods)))
    open_ = close * (1.0 + rng.normal(0.0, 0.001, size=periods))
    volume = rng.integers(1_000_000, 10_000_000, size=periods)
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )
    df["high"] = np.maximum(df["high"], df[["open", "close"]].max(axis=1))
    df["low"] = np.minimum(df["low"], df[["open", "close"]].min(axis=1))
    return df


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_data_manager(monkeypatch):
    """A ``DataManager`` whose Yahoo fallback path is short-circuited to
    return synthetic OHLCV. We turn off the provider factory so the public
    ``get_historical_data`` contract is exercised through the legacy path
    (which is always enabled regardless of provider configuration).

    NOTE: This monkeypatches a private method (``_fetch_yahoo_historical_data``).
    If that method is renamed, this test will break loudly, which is the
    desired behavior — it documents the integration contract.
    """
    dm = DataManager(use_provider_factory=False)
    df = _synthetic_ohlcv()

    def _fake_fetch(symbol, start_date=None, end_date=None, interval="1d", period=None):
        return df.copy()

    monkeypatch.setattr(dm, "_fetch_yahoo_historical_data", _fake_fetch)
    return dm, df


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_data_manager_emits_normalized_ohlcv(patched_data_manager):
    dm, _ = patched_data_manager

    df = dm.get_historical_data("TEST")

    assert not df.empty
    # Lowercase canonical columns the rest of the stack relies on
    for col in ("open", "high", "low", "close", "volume"):
        assert col in df.columns, f"missing required column: {col}"
    assert df.index.is_monotonic_increasing


def test_pipeline_runs_end_to_end(patched_data_manager):
    dm, raw_df = patched_data_manager

    df = dm.get_historical_data("TEST")
    assert len(df) == len(raw_df)

    backtester = Backtester(initial_capital=10_000, commission=0.001, slippage=0.001)
    strategy = MovingAverageCrossover(fast_period=10, slow_period=30)

    result = backtester.run(strategy, df)

    # Result envelope contract — these are what the API layer and
    # frontend report rendering depend on.
    for key in (
        "total_return",
        "annualized_return",
        "sharpe_ratio",
        "max_drawdown",
        "trades",
        "portfolio",
        "execution_costs",
        "execution_diagnostics",
    ):
        assert key in result, f"missing key in backtest result: {key}"

    assert math.isfinite(result["total_return"])
    assert math.isfinite(result["max_drawdown"])
    # Sharpe can be NaN on a flat-return run, but on this seed it should be finite.
    assert math.isfinite(result["sharpe_ratio"])

    # max_drawdown is reported as a non-negative magnitude (e.g. 0.20 for a 20% drawdown).
    assert result["max_drawdown"] >= 0

    assert isinstance(result["trades"], list)
    assert isinstance(result["portfolio"], pd.DataFrame)
    assert "total" in result["portfolio"].columns


def test_pipeline_handles_empty_data_gracefully(monkeypatch):
    """If the data layer hands back an empty frame, the backtester must
    not crash; it should return an empty dict per its documented contract."""
    dm = DataManager(use_provider_factory=False)
    monkeypatch.setattr(
        dm,
        "_fetch_yahoo_historical_data",
        lambda *args, **kwargs: pd.DataFrame(),
    )

    df = dm.get_historical_data("EMPTY")
    assert df.empty

    backtester = Backtester(initial_capital=10_000)
    strategy = MovingAverageCrossover(fast_period=10, slow_period=30)
    result = backtester.run(strategy, df)

    assert result == {}
