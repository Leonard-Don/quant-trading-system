"""Unit tests for :mod:`src.backtest.etf_rotation_walkforward`.

Coverage targets:

1. Dataclass + ``to_dict`` round-trip on the aggregate report.
2. Degenerate inputs — empty period, period < window, missing bounds —
   must not raise.
3. Single-window equivalence — when the walkforward generates exactly one
   window, the per-window metrics must match a direct
   :class:`EtfRotationBacktester` call against the same bounds.
4. Multi-window aggregation — hand-rolled mean / median / pct positive
   / consistency_score on synthetic returns match the aggregate stats.
5. A/B policy contract — both ``policy_signal_factor_enabled`` paths run
   and produce well-formed reports.
6. Window count invariant — for an N-month period, ``(N - window_months)
   / step_months + 1`` windows generated when both fit.
7. Buy-hold benchmark — per-window buy-hold matches naive computation.
8. Consistency score bounds — always in ``[0, 1]``.

All synthetic-only; no disk I/O, no network. Suite completes in <2s.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from src.backtest.etf_rotation_backtest import (
    DEFAULT_INITIAL_CAPITAL,
    EtfRotationBacktester,
)
from src.backtest.etf_rotation_walkforward import (
    DEFAULT_STEP_MONTHS,
    DEFAULT_WINDOW_MONTHS,
    EtfRotationWalkforwardAnalyzer,
    WalkforwardReport,
    _compute_consistency_score,
    _iter_window_bounds,
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


def _trend_market(
    symbols: tuple[str, ...] = ("STRONG", "WEAK"),
    days: int = 540,
    seed: int = 42,
) -> pd.DataFrame:
    """STRONG uptrend, WEAK downtrend, deterministic across runs.

    540 business days ≈ 2 years — gives the walkforward room for many
    rolling windows even after warmup.
    """

    dates = pd.date_range("2023-06-01", periods=days, freq="B")
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


def test_missing_period_bounds_yields_empty_report() -> None:
    """No ``period_start`` / ``period_end`` → empty windows, no exception."""

    config = _make_config()
    prices = _trend_market()
    report = EtfRotationWalkforwardAnalyzer(
        config=config,
        price_history=prices,
    ).run()
    assert isinstance(report, WalkforwardReport)
    assert report.n_windows == 0
    assert report.windows == []
    assert any("empty_report" in c for c in report.caveats)
    # Both top-level numbers should default to neutral values when there
    # are no windows to aggregate.
    assert report.pct_positive_windows == 0.0
    assert report.consistency_score == 0.0


def test_period_shorter_than_window_yields_empty_report() -> None:
    """Period < window_months → no windows generated."""

    config = _make_config()
    prices = _trend_market()
    # 1-month period with 3-month window → can't fit even one window.
    report = EtfRotationWalkforwardAnalyzer(
        config=config,
        price_history=prices,
        window_months=3,
        step_months=1,
        period_start="2024-01-01",
        period_end="2024-01-31",
    ).run()
    assert report.n_windows == 0
    assert any("empty_report" in c for c in report.caveats)


def test_window_count_matches_expected_formula() -> None:
    """For an N-month period with W-month windows and S-month steps,
    the analyzer should yield ``floor((N - W) / S) + 1`` windows.
    """

    # 12-month period, 3-month windows, 1-month step → 10 windows.
    # (Jan/Feb/Mar→Mar; Feb/Mar/Apr→Apr; ...; Oct/Nov/Dec→Dec) = 10
    bounds = list(
        _iter_window_bounds(
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-12-31"),
            window_months=3,
            step_months=1,
        )
    )
    assert len(bounds) == 10
    # First window: 2024-01-01 → 2024-03-31 (calendar 3-month inclusive).
    assert bounds[0][0] == pd.Timestamp("2024-01-01")
    assert bounds[0][1] == pd.Timestamp("2024-03-31")
    # Last window must end no later than the outer bound.
    assert bounds[-1][1] <= pd.Timestamp("2024-12-31")


def test_single_window_matches_direct_backtester_call() -> None:
    """A walkforward with exactly one window must reproduce the
    standalone :class:`EtfRotationBacktester` metrics for that window.

    This is the core equivalence guarantee — the walkforward is *just*
    a roll of the v0.1 harness, not a different model.
    """

    config = _make_config()
    prices = _trend_market(days=540)

    # Force a single window by setting window_months == period span.
    window_start = "2024-04-01"
    window_end = "2024-06-30"

    direct = EtfRotationBacktester(
        config=config,
        price_history=prices,
        period_start=window_start,
        period_end=window_end,
    ).run()

    walkforward = EtfRotationWalkforwardAnalyzer(
        config=config,
        price_history=prices,
        window_months=3,
        step_months=1,
        period_start=window_start,
        period_end=window_end,
    ).run()

    assert walkforward.n_windows == 1
    win = walkforward.windows[0]
    # Numeric equivalence — same bars, same weights, same equity.
    assert win.total_return_pct == pytest.approx(direct.total_return_pct, abs=1e-9)
    assert win.sharpe_ratio == pytest.approx(direct.sharpe_ratio, abs=1e-9)
    assert win.max_drawdown_pct == pytest.approx(direct.max_drawdown_pct, abs=1e-9)
    assert win.final_equity == pytest.approx(direct.final_equity, abs=1e-9)
    assert win.comparable_buy_hold_return_pct == pytest.approx(
        direct.comparable_buy_hold_return_pct, abs=1e-9
    )


def test_multi_window_aggregate_matches_hand_computation() -> None:
    """Per-window metrics roll up to mean/median/pct-positive exactly."""

    config = _make_config()
    prices = _trend_market(days=540)
    report = EtfRotationWalkforwardAnalyzer(
        config=config,
        price_history=prices,
        window_months=3,
        step_months=1,
        period_start="2024-01-01",
        period_end="2024-12-31",
    ).run()
    # We expect ≥ 5 windows to make the aggregation meaningful.
    assert report.n_windows >= 5

    returns = [w.total_return_pct for w in report.windows]
    expected_mean = sum(returns) / len(returns)
    expected_median = float(np.median(returns))
    expected_positive = sum(1 for r in returns if r > 0) / len(returns)

    assert report.mean_window_return_pct == pytest.approx(expected_mean, abs=1e-9)
    assert report.median_window_return_pct == pytest.approx(expected_median, abs=1e-9)
    assert report.pct_positive_windows == pytest.approx(expected_positive, abs=1e-9)
    # Worst drawdown is the max of per-window max_drawdown_pct (positive
    # percent, so "worst" = largest).
    assert report.worst_window_dd_pct == pytest.approx(
        max(w.max_drawdown_pct for w in report.windows), abs=1e-9
    )
    # Consistency score must be in [0, 1] regardless of inputs.
    assert 0.0 <= report.consistency_score <= 1.0


def test_policy_signal_factor_toggle_runs_both_paths() -> None:
    """A/B contract — both factor states return well-formed reports."""

    config = _make_config()
    prices = _trend_market(days=540)
    industry_signals = {
        "AlphaSector": {"avg_impact": 0.30, "signal": "bullish", "mentions": 5},
    }
    etf_industry_map = {"STRONG": "AlphaSector"}

    off = EtfRotationWalkforwardAnalyzer(
        config=config,
        price_history=prices,
        window_months=3,
        step_months=1,
        period_start="2024-01-01",
        period_end="2024-09-30",
        policy_signal_factor_enabled=False,
        industry_signals=industry_signals,
        etf_industry_map=etf_industry_map,
    ).run()
    on = EtfRotationWalkforwardAnalyzer(
        config=config,
        price_history=prices,
        window_months=3,
        step_months=1,
        period_start="2024-01-01",
        period_end="2024-09-30",
        policy_signal_factor_enabled=True,
        industry_signals=industry_signals,
        etf_industry_map=etf_industry_map,
    ).run()

    assert off.policy_signal_factor_enabled is False
    assert on.policy_signal_factor_enabled is True
    assert off.n_windows == on.n_windows >= 1
    for rep in (off, on):
        assert math.isfinite(rep.aggregate_return_pct)
        assert math.isfinite(rep.consistency_score)
        # Every window must carry its policy flag through faithfully.
        for win in rep.windows:
            assert win.policy_signal_factor_enabled is rep.policy_signal_factor_enabled


def test_buy_hold_benchmark_per_window_matches_direct_call() -> None:
    """Per-window buy-hold = direct backtester's buy-hold for that window."""

    config = _make_config()
    prices = _trend_market(days=540)
    walkforward = EtfRotationWalkforwardAnalyzer(
        config=config,
        price_history=prices,
        window_months=3,
        step_months=1,
        period_start="2024-01-01",
        period_end="2024-06-30",
    ).run()
    assert walkforward.n_windows >= 2

    # Pull each window's bounds back out, re-run the direct backtester,
    # and compare the buy-hold return.
    for win in walkforward.windows:
        direct = EtfRotationBacktester(
            config=config,
            price_history=prices,
            period_start=win.period_start,
            period_end=win.period_end,
        ).run()
        assert win.comparable_buy_hold_return_pct == pytest.approx(
            direct.comparable_buy_hold_return_pct, abs=1e-9
        )

    # Aggregate mean buy-hold must equal the arithmetic mean of windows.
    expected_mean_bh = sum(
        w.comparable_buy_hold_return_pct for w in walkforward.windows
    ) / walkforward.n_windows
    assert walkforward.mean_buy_hold_return_pct == pytest.approx(
        expected_mean_bh, abs=1e-9
    )


def test_consistency_score_extremes() -> None:
    """Hand-construct edge inputs and check the helper's behaviour."""

    # All positive, zero dispersion → score ≈ 1.0.
    score_flat_positive = _compute_consistency_score([5.0, 5.0, 5.0, 5.0], 1.0)
    assert score_flat_positive == pytest.approx(1.0, abs=1e-9)

    # All zero → score = 0.0 (no positive windows + no dispersion).
    score_all_zero = _compute_consistency_score([0.0, 0.0, 0.0], 0.0)
    assert score_all_zero == 0.0

    # Mixed sign, half positive, modest dispersion → score in (0, 0.5).
    score_mixed = _compute_consistency_score([5.0, -3.0, 4.0, -2.0], 0.5)
    assert 0.0 < score_mixed < 0.5

    # Single window: score equals pct_positive verbatim.
    assert _compute_consistency_score([5.0], 1.0) == 1.0
    assert _compute_consistency_score([-3.0], 0.0) == 0.0

    # Empty list: 0.0.
    assert _compute_consistency_score([], 0.0) == 0.0


def test_to_dict_is_json_serializable_with_no_nan() -> None:
    """Aggregate report must round-trip ``json.dumps(allow_nan=False)``."""

    config = _make_config()
    prices = _trend_market(days=540)
    report = EtfRotationWalkforwardAnalyzer(
        config=config,
        price_history=prices,
        window_months=3,
        step_months=1,
        period_start="2024-01-01",
        period_end="2024-06-30",
    ).run()
    payload = report.to_dict()
    # allow_nan=False raises on NaN/Inf anywhere inside the nested dict.
    serialised = json.dumps(payload, allow_nan=False)
    parsed = json.loads(serialised)
    assert parsed["window_months"] == DEFAULT_WINDOW_MONTHS
    assert parsed["step_months"] == DEFAULT_STEP_MONTHS
    assert parsed["initial_capital"] == DEFAULT_INITIAL_CAPITAL
    assert isinstance(parsed["windows"], list)
    assert len(parsed["windows"]) == report.n_windows
    # Per-window reports also serialise — verify the inner dict has the
    # expected canonical fields.
    if parsed["windows"]:
        first_window = parsed["windows"][0]
        assert "total_return_pct" in first_window
        assert "sharpe_ratio" in first_window
        assert "max_drawdown_pct" in first_window


def test_walkforward_construction_validation() -> None:
    """Construction guards: window_months / step_months / rebalance_freq_days / initial_capital."""

    config = _make_config()
    prices = _trend_market()

    with pytest.raises(ValueError, match="window_months"):
        EtfRotationWalkforwardAnalyzer(
            config=config, price_history=prices, window_months=0,
        )
    with pytest.raises(ValueError, match="step_months"):
        EtfRotationWalkforwardAnalyzer(
            config=config, price_history=prices, step_months=0,
        )
    with pytest.raises(ValueError, match="rebalance_freq_days"):
        EtfRotationWalkforwardAnalyzer(
            config=config, price_history=prices, rebalance_freq_days=0,
        )
    with pytest.raises(ValueError, match="initial_capital"):
        EtfRotationWalkforwardAnalyzer(
            config=config, price_history=prices, initial_capital=0.0,
        )


def test_caveats_include_walkforward_specific_and_inherit_window_caveats() -> None:
    """The aggregate caveats must surface walkforward-specific markers AND
    inherit the v0.1 per-window caveats (deduplicated).
    """

    config = _make_config()
    prices = _trend_market(days=540)
    report = EtfRotationWalkforwardAnalyzer(
        config=config,
        price_history=prices,
        window_months=3,
        step_months=1,
        period_start="2024-01-01",
        period_end="2024-06-30",
    ).run()
    assert report.n_windows >= 1
    # Walkforward-specific markers must always be present.
    assert "walkforward_overlapping_windows_double_count_overlap" in report.caveats
    assert "sequential_execution_no_parallelism" in report.caveats
    # Inherited from the per-window backtester.
    assert "no_transaction_costs_modeled" in report.caveats
    assert "no_bid_ask_spread_or_slippage" in report.caveats
    assert "no_market_impact" in report.caveats
    # Dedup: only one copy of each inherited caveat regardless of window count.
    assert report.caveats.count("no_transaction_costs_modeled") == 1
