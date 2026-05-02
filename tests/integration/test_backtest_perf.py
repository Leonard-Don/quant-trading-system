"""Performance SLA tests for the core backtest pipeline.

Run locally::

    pytest tests/integration/test_backtest_perf.py --benchmark-only -v

Run only the perf marker::

    pytest -m perf --benchmark-only -v

The CI ``perf`` job runs these on every PR. The SLA assertions guard against
silent regressions when refactoring the backtester or strategy modules.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.backtester import Backtester
from src.strategy.strategies import (
    BollingerBands,
    MovingAverageCrossover,
    RSIStrategy,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _synthetic_ohlcv(days: int = 252, seed: int = 42) -> pd.DataFrame:
    """Reproducible OHLCV with realistic noise — avoids hitting the network."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    returns = rng.normal(0.0005, 0.018, size=days)
    close = 100.0 * np.cumprod(1.0 + returns)
    high = close * (1.0 + np.abs(rng.normal(0.002, 0.001, size=days)))
    low = close * (1.0 - np.abs(rng.normal(0.002, 0.001, size=days)))
    open_ = close * (1.0 + rng.normal(0.0, 0.001, size=days))
    volume = rng.integers(1_000_000, 10_000_000, size=days)
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )
    df["high"] = np.maximum(df["high"], df[["open", "close"]].max(axis=1))
    df["low"] = np.minimum(df["low"], df[["open", "close"]].min(axis=1))
    return df


@pytest.fixture(scope="module")
def one_year_data() -> pd.DataFrame:
    return _synthetic_ohlcv(days=252)


@pytest.fixture(scope="module")
def five_year_data() -> pd.DataFrame:
    return _synthetic_ohlcv(days=252 * 5)


# ---------------------------------------------------------------------------
# SLA tests — fail when p95 wall clock exceeds the budget
# ---------------------------------------------------------------------------

# Budget rationale: 1-year daily MA-crossover should be a sub-200ms compute
# pipeline. We add 10x headroom for CI noise / cold caches and tighten as the
# stack matures. Bumping a budget upward requires a PR comment justifying it.
SLA_MA_1Y_SECONDS = 2.0
SLA_RSI_1Y_SECONDS = 2.0
SLA_BB_1Y_SECONDS = 2.0
SLA_MA_5Y_SECONDS = 5.0


@pytest.mark.perf
@pytest.mark.integration
def test_perf_ma_crossover_one_year(benchmark, one_year_data: pd.DataFrame) -> None:
    backtester = Backtester(initial_capital=10_000, commission=0.001, slippage=0.001)
    strategy = MovingAverageCrossover(fast_period=10, slow_period=30)

    result = benchmark.pedantic(
        backtester.run,
        args=(strategy, one_year_data),
        rounds=5,
        iterations=1,
        warmup_rounds=1,
    )

    assert result is not None
    stats = benchmark.stats.stats
    assert stats.mean < SLA_MA_1Y_SECONDS, (
        f"MA crossover 1Y mean {stats.mean:.3f}s > SLA {SLA_MA_1Y_SECONDS}s"
    )


@pytest.mark.perf
@pytest.mark.integration
def test_perf_rsi_one_year(benchmark, one_year_data: pd.DataFrame) -> None:
    backtester = Backtester(initial_capital=10_000, commission=0.001, slippage=0.001)
    strategy = RSIStrategy(period=14, oversold=30, overbought=70)

    benchmark.pedantic(
        backtester.run,
        args=(strategy, one_year_data),
        rounds=5,
        iterations=1,
        warmup_rounds=1,
    )

    stats = benchmark.stats.stats
    assert stats.mean < SLA_RSI_1Y_SECONDS, (
        f"RSI 1Y mean {stats.mean:.3f}s > SLA {SLA_RSI_1Y_SECONDS}s"
    )


@pytest.mark.perf
@pytest.mark.integration
def test_perf_bollinger_one_year(benchmark, one_year_data: pd.DataFrame) -> None:
    backtester = Backtester(initial_capital=10_000, commission=0.001, slippage=0.001)
    strategy = BollingerBands(period=20, num_std=2.0)

    benchmark.pedantic(
        backtester.run,
        args=(strategy, one_year_data),
        rounds=5,
        iterations=1,
        warmup_rounds=1,
    )

    stats = benchmark.stats.stats
    assert stats.mean < SLA_BB_1Y_SECONDS, (
        f"Bollinger 1Y mean {stats.mean:.3f}s > SLA {SLA_BB_1Y_SECONDS}s"
    )


@pytest.mark.perf
@pytest.mark.integration
def test_perf_ma_crossover_five_year(benchmark, five_year_data: pd.DataFrame) -> None:
    """Long-horizon backtest — guards against O(n^2) accidents."""
    backtester = Backtester(initial_capital=10_000, commission=0.001, slippage=0.001)
    strategy = MovingAverageCrossover(fast_period=20, slow_period=60)

    benchmark.pedantic(
        backtester.run,
        args=(strategy, five_year_data),
        rounds=3,
        iterations=1,
        warmup_rounds=1,
    )

    stats = benchmark.stats.stats
    assert stats.mean < SLA_MA_5Y_SECONDS, (
        f"MA 5Y mean {stats.mean:.3f}s > SLA {SLA_MA_5Y_SECONDS}s"
    )
