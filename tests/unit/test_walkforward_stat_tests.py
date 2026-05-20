"""Unit tests for the walk-forward extension of the formal pairwise tests.

These tests focus on:

1. *Window structure* — given a fixed period + window/step combination,
   the number of windows emitted matches the calendar arithmetic.
2. *Calibration* — identical-return synthetic series produce p ≈ 1
   in every window (no false rejection from regime imbalance).
3. *Effect-size scaling* — a tiny alpha produces high p-values across
   the board; a massive synthetic alpha (rotation = buy-hold * 2)
   produces at least some rejections per window.
4. *Holm correction at scale* — 100 windows with one borderline window
   (p=0.001) should fail vanilla rejection but pass at α/n threshold
   for the first rank.
5. *CLI smoke* — the end-to-end CLI driver should run on a small
   synthetic price matrix without raising and produce a non-empty
   DataFrame.

All tests use NumPy RNG with explicit seeds — no flaky failures.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import pytest

from src.backtest.strategy_statistical_tests import (
    _iter_walk_forward_bounds,
    _resolve_period_index,
    holm_correct,
    walk_forward_statistical_tests,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _date_index(start: str, periods: int, freq: str = "W") -> pd.DatetimeIndex:
    """Weekly business-day-ish index for synthetic return series."""

    return pd.date_range(start=start, periods=periods, freq=freq)


def _series(values: np.ndarray, index: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(values, index=index, dtype=float)


# ---------------------------------------------------------------------------
# Window structure
# ---------------------------------------------------------------------------


def test_window_iterator_emits_exact_count_for_2y_step_6mo_on_4y() -> None:
    """4-year span / 2-year window / 6-month step → exactly 5 windows.

    Cursor schedule: [t, t+6m, t+12m, t+18m, t+24m]. Each window ends
    cursor + 2y - 1day. With ``cursor = t + 24m`` the window ends at
    ``t + 48m - 1day``, which fits inside the 48-month + 1 day span we
    pass in. The 6th cursor (t + 30m) would end at t + 54m - 1day, too
    far → not emitted.
    """

    # Use daily freq so the index endpoints land exactly on the requested
    # calendar bounds (weekly anchors floor the start to the first
    # business week and would shave a few days off the span).
    index = pd.date_range(start="2020-01-01", end="2024-01-01", freq="D")
    windows = list(
        _iter_walk_forward_bounds(index, window_years=2.0, step_months=6)
    )
    assert len(windows) == 5
    # Check that the first window starts on 2020-01-01 and the last on 2022-01-01.
    assert windows[0][1] == pd.Timestamp("2020-01-01")
    assert windows[-1][1] == pd.Timestamp("2022-01-01")


def test_window_iterator_emits_zero_when_period_shorter_than_window() -> None:
    """A 6-month index with a 2-year window → no windows emitted."""

    index = pd.date_range(start="2024-01-01", periods=26, freq="W")
    windows = list(
        _iter_walk_forward_bounds(index, window_years=2.0, step_months=6)
    )
    assert windows == []


def test_window_iterator_rejects_non_positive_args() -> None:
    """``window_years`` ≤ 0 or ``step_months`` ≤ 0 must raise."""

    index = pd.date_range(start="2024-01-01", periods=10, freq="W")
    with pytest.raises(ValueError, match="window_years"):
        list(_iter_walk_forward_bounds(index, window_years=0.0, step_months=1))
    with pytest.raises(ValueError, match="step_months"):
        list(_iter_walk_forward_bounds(index, window_years=1.0, step_months=0))


def test_resolve_period_index_requires_index_for_arrays() -> None:
    """Plain arrays without an explicit ``index`` argument must raise."""

    with pytest.raises(ValueError, match="requires either"):
        _resolve_period_index([0.1, 0.2], [0.1, 0.1], index=None)


def test_resolve_period_index_intersects_series_indices() -> None:
    """Two Series with partly-overlapping indices should align to the intersection."""

    idx_a = pd.date_range("2024-01-01", periods=5, freq="D")
    idx_b = pd.date_range("2024-01-03", periods=5, freq="D")
    a = pd.Series([0.1] * 5, index=idx_a)
    b = pd.Series([0.2] * 5, index=idx_b)
    a_arr, b_arr, ts = _resolve_period_index(a, b)
    assert len(ts) == 3  # 2024-01-03 .. 2024-01-05
    assert list(a_arr) == [0.1, 0.1, 0.1]
    assert list(b_arr) == [0.2, 0.2, 0.2]


# ---------------------------------------------------------------------------
# Calibration: identical series produce p ≈ 1 every window
# ---------------------------------------------------------------------------


def test_identical_returns_yield_p_one_in_every_window() -> None:
    """rotation = buy-hold literally → DM p = 1 in every emitted window."""

    rng = np.random.default_rng(seed=0)
    n = 250  # ~5 years of weekly data
    idx = _date_index("2020-01-01", n, freq="W")
    returns = rng.normal(0.001, 0.01, size=n)
    a = _series(returns, idx)
    b = _series(returns.copy(), idx)

    df = walk_forward_statistical_tests(
        a, b,
        window_years=2.0,
        step_months=6,
        n_bootstrap=200,  # smaller for speed
        apply_holm=True,
    )
    assert not df.empty
    # Identical series → degenerate variance → DM stat exactly 0, p=1.
    np.testing.assert_allclose(df["dm_pvalue"].to_numpy(), 1.0, atol=1e-9)
    assert (df["dm_stat"] == 0.0).all()
    # And Holm should reject nothing.
    assert df["dm_holm_rejected"].sum() == 0


# ---------------------------------------------------------------------------
# Effect-size scaling
# ---------------------------------------------------------------------------


def test_tiny_alpha_yields_mostly_high_pvalues() -> None:
    """rotation = buy-hold + 1 bp drift → most windows have p > 0.05.

    Tiny effect, high noise → low power. The test asserts that *fewer
    than half* of the windows hit raw p < 0.05 (not zero — chance can
    randomly produce a hit on any sample).
    """

    rng = np.random.default_rng(seed=1)
    n = 250
    idx = _date_index("2020-01-01", n, freq="W")
    bh = rng.normal(0.001, 0.02, size=n)
    rotation = bh + 0.0001  # +1 bp weekly — tiny

    a = _series(rotation, idx)
    b = _series(bh, idx)
    df = walk_forward_statistical_tests(
        a, b,
        window_years=2.0,
        step_months=6,
        n_bootstrap=200,
        apply_holm=True,
    )
    assert not df.empty
    raw_hits = int((df["dm_pvalue"] < 0.05).sum())
    # Tiny alpha → low power; assert most windows don't reject. We don't
    # claim zero rejection because random chance on noise can hit any
    # particular window — but the *majority* should fail to reject.
    assert raw_hits < len(df) / 2.0
    # Holm correction should reject very few (likely zero) windows.
    assert int(df["dm_holm_rejected"].sum()) <= raw_hits


def test_massive_synthetic_alpha_yields_significant_windows() -> None:
    """rotation = independent series with massive alpha → DM rejects in most windows.

    A truly detectable synthetic alpha needs *independent* noise plus a
    mean shift — a deterministic proportional rescaling like
    ``rotation = buy_hold * 2`` leaves the DM statistic invariant
    because variance scales with the square of the mean. Here rotation
    has the same volatility as buy-hold but a +50 bps weekly mean
    (~30%/yr drift), so each ~100-obs window has more than enough
    power to reject at α=0.05 even after Holm correction.
    """

    rng = np.random.default_rng(seed=2)
    n = 250
    idx = _date_index("2020-01-01", n, freq="W")
    bh = rng.normal(0.0, 0.01, size=n)
    # +50 bps weekly mean, same volatility as buy-hold — clear winner.
    rotation = rng.normal(0.005, 0.01, size=n)

    a = _series(rotation, idx)
    b = _series(bh, idx)
    df = walk_forward_statistical_tests(
        a, b,
        window_years=2.0,
        step_months=6,
        n_bootstrap=300,
        apply_holm=True,
    )
    assert not df.empty
    # Loss differential should be strictly negative (rotation beats BH).
    assert (df["dm_stat"] < 0.0).all()
    # At least half of the windows should hit raw p < 0.05.
    raw_hits = int((df["dm_pvalue"] < 0.05).sum())
    assert raw_hits >= len(df) // 2
    # At least one window should survive Holm correction across the family.
    assert int(df["dm_holm_rejected"].sum()) >= 1


# ---------------------------------------------------------------------------
# Holm correction at scale
# ---------------------------------------------------------------------------


def test_holm_correction_with_100_windows_one_tiny_pvalue() -> None:
    """100 windows where one has p=0.001 → Holm at α=0.05 *rejects* it.

    Holm threshold for rank 0 with k=100 is α/k = 0.0005. A p=0.001
    sits above this — fails to reject. But at α=0.10 the threshold is
    0.10/100 = 0.001, so p=0.001 is borderline (strictly < 0.001 fails).
    We bump the p-value to 0.0004 to give an unambiguous rejection at
    α=0.05.
    """

    p_values = [0.0004] + [0.5] * 99
    corr = holm_correct(p_values, alpha=0.05)
    assert corr.rejected[0] is True
    assert sum(corr.rejected) == 1


def test_holm_correction_blocks_higher_p_via_cascade() -> None:
    """Holm cascades: a mid-rank failure blocks every later test."""

    # Sorted ascending: [0.0001, 0.5, 0.5, ...]. With k=100 the rank-0
    # threshold is 0.0005; 0.0001 < 0.0005 → reject. Rank 1 threshold is
    # 0.05/99 ≈ 0.000505; 0.5 > threshold → fail → cascade.
    p_values = [0.0001] + [0.5] * 99
    corr = holm_correct(p_values, alpha=0.05)
    # Exactly one rejection.
    assert sum(corr.rejected) == 1
    # The remaining 99 are all blocked.
    assert all(r is False for r in corr.rejected[1:])


# ---------------------------------------------------------------------------
# DataFrame schema + Holm column wiring
# ---------------------------------------------------------------------------


def test_walkforward_dataframe_columns_when_holm_enabled() -> None:
    """The DataFrame must surface every documented column with Holm columns."""

    rng = np.random.default_rng(seed=3)
    n = 100
    idx = _date_index("2022-01-01", n, freq="W")
    a = _series(rng.normal(0.001, 0.01, n), idx)
    b = _series(rng.normal(0.0, 0.01, n), idx)
    df = walk_forward_statistical_tests(
        a, b,
        window_years=0.5,
        step_months=3,
        n_bootstrap=100,
        apply_holm=True,
    )
    expected_cols = {
        "window_id",
        "start_date",
        "end_date",
        "n_obs",
        "dm_stat",
        "dm_pvalue",
        "sharpe_z",
        "sharpe_pvalue",
        "boot_lower",
        "boot_upper",
        "boot_pvalue",
        "dm_holm_threshold",
        "dm_holm_rejected",
        "dm_holm_alpha",
    }
    assert expected_cols.issubset(df.columns)


def test_walkforward_dataframe_columns_when_holm_disabled() -> None:
    """``apply_holm=False`` should drop the three Holm columns."""

    rng = np.random.default_rng(seed=4)
    n = 100
    idx = _date_index("2022-01-01", n, freq="W")
    a = _series(rng.normal(0.001, 0.01, n), idx)
    b = _series(rng.normal(0.0, 0.01, n), idx)
    df = walk_forward_statistical_tests(
        a, b,
        window_years=0.5,
        step_months=3,
        n_bootstrap=100,
        apply_holm=False,
    )
    assert "dm_holm_rejected" not in df.columns
    assert "dm_holm_threshold" not in df.columns


# ---------------------------------------------------------------------------
# CLI driver end-to-end smoke test
# ---------------------------------------------------------------------------


def _write_synthetic_price_csv(
    tmp_path: Path,
    *,
    n_days: int = 1100,
    seed: int = 5,
) -> Path:
    """Write a small wide CSV mimicking ``data/etf_backtest/etf_prices_5y.csv``.

    Uses the real-universe ETF codes so the rotation strategy's default
    holdings list (loaded by ``daily_etf_signal.load_default_holdings``)
    can match the columns. ~1100 business days ≈ 4.4 years — enough for
    multiple 2-year walk-forward windows.
    """

    rng = np.random.default_rng(seed=seed)
    idx = pd.date_range(start="2022-01-03", periods=n_days, freq="B")
    # Match the codes in data/etf_backtest/etf_prices_5y.csv exactly so
    # the strategy's default-holdings universe finds something to trade.
    columns = {}
    for i, code in enumerate(["159985", "512400", "510300", "518680", "513130"]):
        drift = 0.0003 + i * 0.0001
        noise = rng.normal(0.0, 0.012, n_days)
        log_returns = drift + noise
        prices = 10.0 * np.exp(np.cumsum(log_returns))
        columns[code] = prices
    df = pd.DataFrame(columns, index=idx)
    df.index.name = "date"
    csv_path = tmp_path / "synthetic_prices.csv"
    df.to_csv(csv_path)
    return csv_path


def test_cli_smoke_runs_end_to_end(tmp_path: Path) -> None:
    """The full CLI pipeline should run on a synthetic CSV without raising."""

    # Lazy import inside the test so the heavier strategy machinery only
    # loads when the user runs this CLI-smoke test (every other test in
    # the file stays at the bare-primitive level).
    from scripts.walkforward_stat_tests import run_walkforward_stat_tests

    csv_path = _write_synthetic_price_csv(tmp_path, n_days=1100)
    df, summary = run_walkforward_stat_tests(
        csv_path,
        window_years=2.0,
        step_months=6,
        strategy_labels=["rotation"],  # one strategy keeps the test fast
        n_bootstrap=100,
        alpha=0.05,
    )
    # We expect at least one window to be emitted on a 4+ year sample.
    assert isinstance(df, pd.DataFrame)
    assert cast(int, summary["n_total_window_tests"]) >= 1
    assert "rotation" in cast(list[str], summary["strategies"])
    # Honest conclusion must be a non-empty string.
    assert isinstance(summary["honest_conclusion"], str)
    assert summary["honest_conclusion"]


def test_cli_default_outputs_are_publishable_docs_paths() -> None:
    """A no-flag real-data run should not leave root-level untracked CSVs."""

    from scripts import walkforward_stat_tests as wf

    args = wf._build_arg_parser().parse_args(
        ["--csv", "data/etf_backtest/etf_prices_5y.csv"]
    )
    assert args.output_csv == Path("docs/walkforward_stat_tests.csv")
    assert args.output_md == Path("docs/walkforward_stat_tests_summary.md")


# ---------------------------------------------------------------------------
# Blend ≡ rotation degeneracy detector
# ---------------------------------------------------------------------------


def test_blend_regime_flag_defaults_to_unknown() -> None:
    """--blend-regime is the passthrough that lets a user escape degeneracy;
    its default must remain ``unknown`` so existing scripts/CI don't break.
    """

    from scripts import walkforward_stat_tests as wf

    args = wf._build_arg_parser().parse_args(
        ["--csv", "data/etf_backtest/etf_prices_5y.csv"]
    )
    assert args.blend_regime == "unknown"


def test_detect_blend_rotation_degeneracy_flags_identical_rows() -> None:
    """When blend's per-window DM stats are byte-identical to rotation's
    the detector returns a payload naming the twin strategy.
    """

    from scripts.walkforward_stat_tests import _detect_blend_rotation_degeneracy

    df = pd.DataFrame(
        {
            "strategy": ["rotation", "rotation", "blend", "blend"],
            "window_id": [0, 1, 0, 1],
            "dm_stat": [1.10, -0.25, 1.10, -0.25],
            "dm_pvalue": [0.27, 0.80, 0.27, 0.80],
        }
    )
    payload = _detect_blend_rotation_degeneracy(df, blend_regime="unknown")
    assert payload is not None
    assert payload["twin_strategy"] == "rotation"
    assert payload["blend_regime"] == "unknown"
    assert payload["n_matched_windows"] == 2


def test_detect_blend_rotation_degeneracy_returns_none_when_distinct() -> None:
    """When blend's per-window numbers differ from every other strategy the
    detector must return None — no false-positive warnings.
    """

    from scripts.walkforward_stat_tests import _detect_blend_rotation_degeneracy

    df = pd.DataFrame(
        {
            "strategy": ["rotation", "rotation", "blend", "blend"],
            "window_id": [0, 1, 0, 1],
            "dm_stat": [1.10, -0.25, 0.85, -0.31],
            "dm_pvalue": [0.27, 0.80, 0.39, 0.75],
        }
    )
    assert _detect_blend_rotation_degeneracy(df, blend_regime="sideways") is None


def test_detect_blend_rotation_degeneracy_returns_none_when_blend_absent() -> None:
    """If the strategy list does not include blend the detector is a no-op."""

    from scripts.walkforward_stat_tests import _detect_blend_rotation_degeneracy

    df = pd.DataFrame(
        {
            "strategy": ["rotation", "mean_reversion"],
            "window_id": [0, 0],
            "dm_stat": [0.5, 0.5],
            "dm_pvalue": [0.6, 0.6],
        }
    )
    assert _detect_blend_rotation_degeneracy(df, blend_regime="unknown") is None


def test_summary_renders_degeneracy_warning_in_markdown_and_terminal() -> None:
    """The Markdown + terminal renderers must surface the degeneracy
    payload so a human reading the summary cannot miss it.
    """

    from scripts.walkforward_stat_tests import (
        _build_summary,
        _render_terminal_summary,
        render_markdown_summary,
    )

    df = pd.DataFrame(
        {
            "strategy": ["rotation", "rotation", "blend", "blend"],
            "window_id": [0, 1, 0, 1],
            "start_date": ["2022-01-01"] * 4,
            "end_date": ["2024-01-01"] * 4,
            "n_obs": [100, 100, 100, 100],
            "dm_stat": [1.10, -0.25, 1.10, -0.25],
            "dm_pvalue": [0.27, 0.80, 0.27, 0.80],
            "sharpe_z": [0.5, -0.2, 0.5, -0.2],
            "sharpe_pvalue": [0.6, 0.8, 0.6, 0.8],
            "boot_lower": [-0.05, -0.10, -0.05, -0.10],
            "boot_upper": [0.10, 0.05, 0.10, 0.05],
            "boot_pvalue": [0.4, 0.7, 0.4, 0.7],
            "dm_holm_threshold": [0.05] * 4,
            "dm_holm_rejected": [False] * 4,
            "dm_holm_alpha": [0.05] * 4,
        }
    )
    summary = _build_summary(
        df,
        comparison=None,
        window_years=2.0,
        step_months=6,
        alpha=0.05,
        blend_regime="unknown",
    )
    assert summary["blend_degeneracy"] is not None
    md = render_markdown_summary(df, summary)
    term = _render_terminal_summary(df, summary)
    assert "Degenerate blend comparison" in md
    assert "blend ≡ rotation" in term
    # The honest conclusion must lead with the degeneracy warning so the
    # user can't read past the headline numbers without seeing it.
    assert "blend ≡ rotation" in str(summary["honest_conclusion"])


def test_summary_omits_degeneracy_warning_when_sideways_regime() -> None:
    """A non-degenerate blend run must not trigger the warning."""

    from scripts.walkforward_stat_tests import (
        _build_summary,
        _render_terminal_summary,
        render_markdown_summary,
    )

    df = pd.DataFrame(
        {
            "strategy": ["rotation", "rotation", "blend", "blend"],
            "window_id": [0, 1, 0, 1],
            "start_date": ["2022-01-01"] * 4,
            "end_date": ["2024-01-01"] * 4,
            "n_obs": [100, 100, 100, 100],
            "dm_stat": [1.10, -0.25, 0.85, -0.31],
            "dm_pvalue": [0.27, 0.80, 0.39, 0.75],
            "sharpe_z": [0.5, -0.2, 0.4, -0.3],
            "sharpe_pvalue": [0.6, 0.8, 0.7, 0.7],
            "boot_lower": [-0.05, -0.10, -0.04, -0.09],
            "boot_upper": [0.10, 0.05, 0.09, 0.04],
            "boot_pvalue": [0.4, 0.7, 0.5, 0.6],
            "dm_holm_threshold": [0.05] * 4,
            "dm_holm_rejected": [False] * 4,
            "dm_holm_alpha": [0.05] * 4,
        }
    )
    summary = _build_summary(
        df,
        comparison=None,
        window_years=2.0,
        step_months=6,
        alpha=0.05,
        blend_regime="sideways",
    )
    assert summary["blend_degeneracy"] is None
    assert "Degenerate blend comparison" not in render_markdown_summary(df, summary)
    assert "blend ≡" not in _render_terminal_summary(df, summary)


def test_all_null_conclusion_links_to_power_target_mde() -> None:
    """All-null summaries should point to the MDE inversion, not stale heuristics."""

    from scripts.walkforward_stat_tests import _build_summary

    df = pd.DataFrame(
        {
            "strategy": ["rotation", "rotation"],
            "window_id": [0, 1],
            "start_date": ["2022-01-01", "2022-07-01"],
            "end_date": ["2024-01-01", "2024-07-01"],
            "n_obs": [100, 100],
            "dm_stat": [0.5, -0.2],
            "dm_pvalue": [0.40, 0.80],
            "sharpe_z": [0.2, -0.1],
            "sharpe_pvalue": [0.8, 0.9],
            "boot_lower": [-0.05, -0.08],
            "boot_upper": [0.06, 0.04],
            "boot_pvalue": [0.5, 0.9],
            "dm_holm_threshold": [0.05, 0.025],
            "dm_holm_rejected": [False, False],
            "dm_holm_alpha": [0.05, 0.05],
        }
    )

    summary = _build_summary(
        df,
        comparison=None,
        window_years=2.0,
        step_months=6,
        alpha=0.05,
    )

    conclusion = str(summary["honest_conclusion"])
    assert "Minimum Detectable Effect" in conclusion
    assert "scripts/power_target.py" in conclusion
