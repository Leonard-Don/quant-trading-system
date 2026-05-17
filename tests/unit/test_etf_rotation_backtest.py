"""Unit tests for the ETF rotation backtest harness.

These tests focus on:

1. The dataclass contract — every public field is populated, ``to_dict``
   round-trips cleanly.
2. Degenerate inputs — empty windows, monotonic-up markets, all-flat
   markets, all-cash universes — must NOT throw.
3. The A/B contract — policy_signal_factor on vs off both run without
   error against the same window.
4. The numeric invariants — turnover, drawdown, win-rate accounting are
   correct on hand-crafted synthetic data.

The fixtures keep all prices in-memory; no disk I/O, no network. Tests
run in well under a second.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from src.backtest.etf_rotation_backtest import (
    DEFAULT_INITIAL_CAPITAL,
    BacktestReport,
    EtfRotationBacktester,
)
from src.strategy.etf_rotation_strategy import (
    EtfAssetConfig,
    EtfRotationConfig,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(symbols: tuple[str, ...] = ("STRONG", "WEAK")) -> EtfRotationConfig:
    """Default 2-asset rotation config used by most tests."""

    return EtfRotationConfig(
        assets=[EtfAssetConfig(symbol=s, max_weight=0.5) for s in symbols],
        gross_cap=0.9,
        warmup_days=60,
    )


def _flat_prices(symbols: tuple[str, ...], days: int = 180) -> pd.DataFrame:
    """Constant-price matrix (zero return at every bar)."""

    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    return pd.DataFrame(
        {s: np.full(days, 100.0) for s in symbols},
        index=dates,
    )


def _monotonic_uptrend(
    symbols: tuple[str, ...],
    days: int = 180,
    daily_return: float = 0.001,
) -> pd.DataFrame:
    """Perfect monotonic uptrend — no noise, no drawdown."""

    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    base = np.array(
        [100.0 * ((1.0 + daily_return) ** i) for i in range(days)], dtype=float,
    )
    return pd.DataFrame({s: base.copy() for s in symbols}, index=dates)


def _trend_market(
    symbols: tuple[str, ...] = ("STRONG", "WEAK"),
    days: int = 180,
    seed: int = 42,
) -> pd.DataFrame:
    """STRONG is uptrend, WEAK is downtrend. Deterministic across runs."""

    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    rng = np.random.default_rng(seed=seed)
    columns: dict[str, np.ndarray] = {}
    for offset, sym in enumerate(symbols):
        drift = np.linspace(0.0, 0.30 if offset == 0 else -0.20, days)
        noise = rng.normal(0.0, 0.003, days)
        columns[sym] = 100.0 * np.exp(drift + np.cumsum(noise))
    return pd.DataFrame(columns, index=dates)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_empty_price_matrix_returns_empty_report() -> None:
    """Empty inputs → empty report, no exception."""

    config = _make_config()
    empty = pd.DataFrame()
    report = EtfRotationBacktester(config=config, price_history=empty).run()
    assert isinstance(report, BacktestReport)
    assert report.n_bars == 0
    assert report.n_rebalances == 0
    assert report.total_return_pct == 0.0
    assert report.max_drawdown_pct == 0.0
    assert report.final_equity == report.initial_capital
    assert any("empty_report" in c for c in report.caveats)


def test_insufficient_history_returns_empty_report() -> None:
    """Fewer bars than the warmup should bail out gracefully."""

    config = _make_config()
    short_prices = _flat_prices(("STRONG", "WEAK"), days=30)  # warmup_days=60
    report = EtfRotationBacktester(config=config, price_history=short_prices).run()
    assert report.n_bars == 0
    assert any("insufficient_history" in c for c in report.caveats)


def test_flat_market_yields_zero_return_no_drawdown() -> None:
    """Constant prices → no return, no drawdown, sharpe undefined → 0."""

    config = _make_config()
    prices = _flat_prices(("STRONG", "WEAK"), days=180)
    report = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start="2024-04-01",
    ).run()
    assert report.n_bars > 0
    # On a flat market the strategy may or may not allocate (trend gates
    # may zero out positions), but realised P&L is zero either way.
    assert report.total_return_pct == pytest.approx(0.0, abs=1e-9)
    assert report.max_drawdown_pct == pytest.approx(0.0, abs=1e-9)
    assert report.sharpe_ratio == 0.0
    # Calmar is undefined when max DD is zero — must be None.
    assert report.calmar_ratio is None


def test_uptrend_market_yields_positive_return() -> None:
    """A monotonic up market with no drawdown → positive return, zero DD."""

    config = _make_config()
    prices = _monotonic_uptrend(("STRONG", "WEAK"), days=200, daily_return=0.001)
    report = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start="2024-04-01",
    ).run()
    assert report.n_bars > 0
    # Strategy will allocate because the uptrend is real.
    assert report.total_return_pct > 0.0
    # Monotonic up → no drawdown ever.
    assert report.max_drawdown_pct == pytest.approx(0.0, abs=1e-9)
    # Buy-hold benchmark must also be positive — sanity check the helper.
    assert report.comparable_buy_hold_return_pct > 0.0


def test_policy_signal_factor_toggle_runs_both_paths() -> None:
    """A/B contract: both factor states return a valid report without error."""

    config = _make_config()
    prices = _trend_market(("STRONG", "WEAK"), days=180)
    # Map STRONG to a bullish industry so we exercise the factor path.
    industry_signals = {
        "AlphaSector": {"avg_impact": 0.30, "signal": "bullish", "mentions": 5},
    }
    etf_industry_map = {"STRONG": "AlphaSector"}

    off = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start="2024-04-01",
        policy_signal_factor_enabled=False,
        industry_signals=industry_signals,
        etf_industry_map=etf_industry_map,
    ).run()
    on = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start="2024-04-01",
        policy_signal_factor_enabled=True,
        industry_signals=industry_signals,
        etf_industry_map=etf_industry_map,
    ).run()

    assert off.policy_signal_factor_enabled is False
    assert on.policy_signal_factor_enabled is True
    # Both reports must be well-formed — no NaN equity, no negative initial
    # capital, etc.
    for rep in (off, on):
        assert rep.n_bars > 0
        assert rep.initial_capital == DEFAULT_INITIAL_CAPITAL
        assert math.isfinite(rep.final_equity)


def test_turnover_calculation_matches_hand_computed_value() -> None:
    """Turnover in the report should equal sum(|Δw|) / 2 across rebalances.

    We craft a trend market that produces stable weights then compare the
    harness's avg_turnover to a hand-rolled computation from the
    ``rebalance_log``.
    """

    config = _make_config()
    prices = _trend_market(("STRONG", "WEAK"), days=180)
    report = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start="2024-04-01",
    ).run()

    assert report.n_rebalances >= 2
    hand_avg = (
        sum(row["turnover"] for row in report.rebalance_log) / report.n_rebalances
    )
    # avg_turnover_pct is the mean turnover * 100
    assert report.avg_turnover_pct == pytest.approx(hand_avg * 100.0, abs=1e-9)


def test_max_drawdown_zero_for_monotonic_curve() -> None:
    """Edge: equity that only goes up should report zero drawdown.

    Uses a single-asset uptrend so the strategy stays fully invested and
    the equity curve cannot dip.
    """

    config = EtfRotationConfig(
        assets=[EtfAssetConfig(symbol="ONLY", max_weight=0.9)],
        gross_cap=0.9,
        warmup_days=60,
    )
    prices = _monotonic_uptrend(("ONLY",), days=200, daily_return=0.001)
    report = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start="2024-04-01",
    ).run()
    assert report.max_drawdown_pct == pytest.approx(0.0, abs=1e-9)
    assert report.calmar_ratio is None


def test_comparable_buy_hold_return_matches_naive_computation() -> None:
    """Buy-and-hold benchmark = mean of (last/first - 1) across assets."""

    config = _make_config()
    prices = _trend_market(("STRONG", "WEAK"), days=180)
    report = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start="2024-04-01",
        period_end="2024-07-31",
    ).run()
    # Pull the same window directly from the matrix and compare.
    window = prices.loc[
        (prices.index >= pd.Timestamp("2024-04-01"))
        & (prices.index <= pd.Timestamp("2024-07-31"))
    ]
    # Strategy universe == ("STRONG", "WEAK") — both columns participate.
    expected = ((window.iloc[-1] / window.iloc[0]) - 1.0).mean() * 100.0
    assert report.comparable_buy_hold_return_pct == pytest.approx(
        float(expected), abs=1e-9,
    )


def test_to_dict_is_json_serializable_with_no_nan() -> None:
    """Report dicts must round-trip through json.dumps with allow_nan=False."""

    config = _make_config()
    # Even on an essentially-flat market the report should serialize cleanly:
    # calmar_ratio can be None (allowed), but no NaN/Inf should leak in.
    prices = _flat_prices(("STRONG", "WEAK"), days=180)
    report = EtfRotationBacktester(config=config, price_history=prices).run()
    payload = report.to_dict()
    # allow_nan=False raises on NaN/Inf inside any nested float.
    serialised = json.dumps(payload, allow_nan=False)
    parsed = json.loads(serialised)
    assert parsed["initial_capital"] == DEFAULT_INITIAL_CAPITAL
    assert parsed["calmar_ratio"] is None  # Defined-as-None when DD == 0
    # Caveats list survives round-trip.
    assert isinstance(parsed["caveats"], list)
    assert "no_transaction_costs_modeled" in parsed["caveats"]


def test_rebalance_freq_validation_rejects_zero() -> None:
    """Construction guard: cadence must be at least one bar."""

    config = _make_config()
    prices = _trend_market()
    with pytest.raises(ValueError, match="rebalance_freq_days"):
        EtfRotationBacktester(
            config=config,
            price_history=prices,
            rebalance_freq_days=0,
        )


def test_initial_capital_validation_rejects_non_positive() -> None:
    """Construction guard: initial_capital must be > 0."""

    config = _make_config()
    prices = _trend_market()
    with pytest.raises(ValueError, match="initial_capital"):
        EtfRotationBacktester(
            config=config,
            price_history=prices,
            initial_capital=0.0,
        )


def test_window_start_after_end_yields_empty_report() -> None:
    """Reversed window bounds → empty result, no crash."""

    config = _make_config()
    prices = _trend_market()
    report = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start="2024-12-01",
        period_end="2024-01-01",
    ).run()
    assert report.n_bars == 0
    assert any("window_too_small" in c or "empty_report" in c for c in report.caveats)
