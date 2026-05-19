#!/usr/bin/env python3
"""Walk-forward extension of the formal pairwise statistical tests.

Commit ``fddfbf8`` added terminal-period DM + block-bootstrap + Sharpe
tests comparing rotation / mean_reversion / blend against buy-and-hold
on the full 4-year window. The empirical finding was that **no test
reached α=0.05 (or even α=0.10)** — a 16-19pp raw spread was
statistically indistinguishable from noise on a single window.

A single terminal-period test answers "is the spread significant when
you ate the full window in one bite?" — but it can't tell you whether
the spread is *concentrated in a regime* or *evenly distributed in
time*. This CLI extends the same tests to walk-forward windows so you
get a per-window p-value series instead of one number.

Honest framing:

* Per-window tests have *fewer* observations than the terminal one,
  so each window has *less* power. We do this not to dredge for a
  significant window (multiple-testing correction makes that hard)
  but to surface whether the spread is at least *consistently in the
  same direction* across windows.
* If every window's raw p-value is > 0.05 and Holm correction rejects
  zero windows, that's the headline. We don't bury it.

Typical use::

    python scripts/walkforward_stat_tests.py \
        --csv data/etf_backtest/etf_prices_5y.csv \
        --window-years 2 \
        --step-months 6 \
        --strategies rotation,mean_reversion,blend \
        --output-csv walkforward_stat_tests.csv \
        --output-md docs/walkforward_stat_tests_summary.md

Outputs:

* Per-window DataFrame to ``--output-csv`` (one row per
  (strategy, window) pair).
* One-page Markdown summary to ``--output-md``.
* Terminal-friendly summary table to stdout.
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Optional, cast

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.compare_strategies import (  # noqa: E402
    load_price_matrix,
    run_comparison,
)
from src.backtest.etf_rotation_backtest import (  # noqa: E402
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_REBALANCE_FREQ_DAYS,
    BacktestReport,
)
from src.backtest.strategy_comparison import (  # noqa: E402
    DEFAULT_STRATEGY_LABELS,
    ComparisonReport,
)
from src.backtest.strategy_statistical_tests import (  # noqa: E402
    holm_correct,
    walk_forward_statistical_tests,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers: extract aligned per-period returns from a ComparisonReport
# ---------------------------------------------------------------------------


def _strategy_return_series(report: BacktestReport) -> pd.Series:
    """Pull a date-indexed per-rebalance return Series from a BacktestReport.

    Mirrors :func:`_returns_from_rebalance_log` (in strategy_comparison)
    but preserves the dates so the walk-forward slicing can carve the
    series into calendar windows. The first rebalance log entry is the
    initial allocation (period_return = 0) — we drop it so the series
    starts with the first realised return.
    """

    log = report.rebalance_log or []
    dates: list[pd.Timestamp] = []
    values: list[float] = []
    for i, entry in enumerate(log):
        if i == 0:
            continue
        raw_date = entry.get("date")
        raw_return = entry.get("period_return_pct")
        if raw_date is None or raw_return is None:
            continue
        try:
            ts = pd.Timestamp(raw_date)
        except (TypeError, ValueError):
            continue
        try:
            val = float(raw_return) / 100.0
        except (TypeError, ValueError):
            continue
        if not math.isfinite(val):
            continue
        dates.append(ts)
        values.append(val)
    return pd.Series(values, index=pd.DatetimeIndex(dates), dtype=float, name=None)


def _buy_hold_return_series(
    prices: pd.DataFrame,
    *,
    period_start: pd.Timestamp,
    period_end: pd.Timestamp,
    rebalance_freq_days: int,
) -> pd.Series:
    """Synthesise an equal-weight buy-and-hold per-period return Series.

    Mirrors :meth:`StrategyComparator._build_buy_hold_period_returns`
    but preserves the sample dates so the result is alignable with the
    strategy series for walk-forward slicing.
    """

    mask = (prices.index >= period_start) & (prices.index <= period_end)
    window = prices.loc[mask].dropna(how="all")
    if window.empty or len(window) < 2:
        return pd.Series(dtype=float)
    equity = (window / window.iloc[0]).mean(axis=1)
    sample_idx = list(range(0, len(equity), rebalance_freq_days))
    if len(sample_idx) < 2:
        return pd.Series(dtype=float)
    sampled = equity.iloc[sample_idx]
    returns = sampled.pct_change().dropna()
    returns = returns[np.isfinite(returns)]
    return returns


def _align_strategy_vs_buy_hold(
    strategy_returns: pd.Series,
    buy_hold_returns: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Inner-join two date-indexed Series so the walk-forward gets aligned input.

    Without alignment one strategy's missing date drags the walkforward
    DM into a length-mismatch error. We intersect on the index and
    reindex both so they have the same dates with no NaN holes.
    """

    common_idx = strategy_returns.index.intersection(buy_hold_returns.index)
    if len(common_idx) == 0:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    return (
        strategy_returns.reindex(common_idx).astype(float),
        buy_hold_returns.reindex(common_idx).astype(float),
    )


# ---------------------------------------------------------------------------
# Per-strategy walk-forward driver
# ---------------------------------------------------------------------------


def run_walkforward_stat_tests(
    csv_path: Path,
    *,
    window_years: float,
    step_months: int,
    strategy_labels: Sequence[str] = DEFAULT_STRATEGY_LABELS,
    rebalance_freq_days: int = DEFAULT_REBALANCE_FREQ_DAYS,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    block_size: int = 10,
    n_bootstrap: int = 1000,
    alpha: float = 0.05,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Drive the full pipeline and return ``(per_window_df, summary)``.

    Pipeline steps:

    1. Load the price CSV.
    2. Run :class:`StrategyComparator` over the full window (or the
       caller-supplied bounds) so every strategy + buy-and-hold gets a
       per-rebalance return series sampled at the same cadence.
    3. For each chosen strategy, walk-forward the DM / Sharpe / bootstrap
       tests on (strategy_returns, buy_hold_returns).
    4. Apply Holm step-down across the *full* per-window p-value matrix
       (windows × strategies, not just one strategy at a time).

    Returns the long-form per-window DataFrame and a summary dict
    suitable for the Markdown renderer.
    """

    prices = load_price_matrix(csv_path)
    if prices.empty:
        raise ValueError(f"Empty price matrix from {csv_path!r}")

    resolved_start = period_start or str(prices.index[0].date())
    resolved_end = period_end or str(prices.index[-1].date())

    comparison = run_comparison(
        csv_path,
        period_start=resolved_start,
        period_end=resolved_end,
        strategy_labels=strategy_labels,
        rebalance_freq_days=rebalance_freq_days,
        initial_capital=initial_capital,
        # We compute statistical tests separately in walk-forward mode,
        # so the comparator's own one-shot tests are off here.
        compute_statistical_tests=False,
    )

    bh_returns = _buy_hold_return_series(
        prices,
        period_start=pd.Timestamp(resolved_start),
        period_end=pd.Timestamp(resolved_end),
        rebalance_freq_days=rebalance_freq_days,
    )
    if bh_returns.empty:
        raise ValueError(
            "Could not synthesise buy-and-hold return series — period too short "
            f"or no usable prices in {resolved_start} → {resolved_end}"
        )

    per_strategy_frames: list[pd.DataFrame] = []
    for label in strategy_labels:
        report = comparison.per_strategy_metrics.get(label)
        if report is None:
            logger.warning(
                "strategy %s not present in comparison report — skipping",
                label,
            )
            continue
        strat_returns = _strategy_return_series(report)
        if strat_returns.empty:
            logger.warning(
                "strategy %s produced an empty return series — skipping",
                label,
            )
            continue
        aligned_a, aligned_b = _align_strategy_vs_buy_hold(strat_returns, bh_returns)
        if aligned_a.empty:
            logger.warning(
                "strategy %s shares no dates with buy-and-hold — skipping",
                label,
            )
            continue
        # apply_holm=False here — we Holm-correct across the full
        # (strategies × windows) p-value matrix at the end.
        df = walk_forward_statistical_tests(
            aligned_a,
            aligned_b,
            window_years=window_years,
            step_months=step_months,
            block_size=block_size,
            n_bootstrap=n_bootstrap,
            apply_holm=False,
        )
        if df.empty:
            logger.warning(
                "strategy %s yielded zero walk-forward windows", label,
            )
            continue
        df = df.copy()
        df.insert(0, "strategy", label)
        per_strategy_frames.append(df)

    if not per_strategy_frames:
        empty = pd.DataFrame(
            columns=[
                "strategy",
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
            ]
        )
        return empty, _build_summary(
            empty,
            comparison=comparison,
            window_years=window_years,
            step_months=step_months,
            alpha=alpha,
        )

    combined = pd.concat(per_strategy_frames, ignore_index=True)
    # Family-wise Holm correction across every (strategy, window) p-value.
    correction = holm_correct(
        combined["dm_pvalue"].tolist(),
        alpha=alpha,
        labels=[
            f"{row['strategy']}/window_{int(row['window_id'])}"
            for _, row in combined.iterrows()
        ],
    )
    combined["dm_holm_threshold"] = correction.adjusted_alpha
    combined["dm_holm_rejected"] = correction.rejected
    combined["dm_holm_alpha"] = alpha

    summary = _build_summary(
        combined,
        comparison=comparison,
        window_years=window_years,
        step_months=step_months,
        alpha=alpha,
    )
    return combined, summary


# ---------------------------------------------------------------------------
# Summary + Markdown renderer
# ---------------------------------------------------------------------------


def _build_summary(
    df: pd.DataFrame,
    *,
    comparison: Optional[ComparisonReport],
    window_years: float,
    step_months: int,
    alpha: float,
) -> dict[str, object]:
    """Distill the per-window DataFrame into the Markdown-renderer payload."""

    summary: dict[str, object] = {
        "window_years": float(window_years),
        "step_months": int(step_months),
        "alpha": float(alpha),
        "n_total_window_tests": len(df),
        "strategies": sorted(df["strategy"].unique().tolist()) if not df.empty else [],
        "n_windows_per_strategy": {},
    }
    if comparison is not None:
        summary["period_start"] = comparison.period_start
        summary["period_end"] = comparison.period_end
    if df.empty:
        summary["n_raw_significant"] = 0
        summary["n_holm_significant"] = 0
        summary["min_pvalue"] = None
        summary["min_pvalue_strategy"] = None
        summary["min_pvalue_window"] = None
        summary["direction_consistency_by_strategy"] = {}
        summary["honest_conclusion"] = (
            "No walk-forward windows could be emitted; the period is too "
            "short for the requested window/step combination."
        )
        return summary

    # Direction consistency: for each strategy, fraction of windows where
    # the strategy *beat* buy-hold (mean_loss_differential < 0 in DM-speak
    # = strategy's loss is smaller). We don't have mean_loss_differential
    # on the row directly, but dm_stat shares the same sign convention
    # (since loss_fn=negative_return and the variance is positive), so a
    # negative dm_stat means strategy A had lower loss = beat buy-hold.
    n_per_strategy: dict[str, int] = {}
    direction_consistency: dict[str, float] = {}
    for strat, sub in df.groupby("strategy"):
        n_per_strategy[str(strat)] = len(sub)
        if len(sub) == 0:
            direction_consistency[str(strat)] = 0.0
            continue
        beats = int((sub["dm_stat"] < 0.0).sum())
        direction_consistency[str(strat)] = float(beats / len(sub))
    summary["n_windows_per_strategy"] = n_per_strategy
    summary["direction_consistency_by_strategy"] = direction_consistency

    summary["n_raw_significant"] = int((df["dm_pvalue"] < alpha).sum())
    summary["n_holm_significant"] = (
        int(df["dm_holm_rejected"].sum())
        if "dm_holm_rejected" in df.columns
        else 0
    )

    min_idx = int(df["dm_pvalue"].idxmin())
    min_row = df.iloc[min_idx]
    summary["min_pvalue"] = float(min_row["dm_pvalue"])
    summary["min_pvalue_strategy"] = str(min_row["strategy"])
    summary["min_pvalue_window"] = (
        f"{min_row['start_date']} → {min_row['end_date']} (window_id={int(min_row['window_id'])})"
    )

    summary["honest_conclusion"] = _craft_conclusion(df, alpha=alpha)
    return summary


def _craft_conclusion(df: pd.DataFrame, *, alpha: float) -> str:
    """Build the one-paragraph honest finding.

    Four mutually-exclusive states:

    1. Holm rejects ≥ 1 window → significant in some regime.
    2. Holm rejects 0 but raw p-values below α exist → suggestive but
       fails multi-testing.
    3. Every window's raw p > α → no signal at all.
    4. Empty df handled upstream.
    """

    n_total = len(df)
    n_raw = int((df["dm_pvalue"] < alpha).sum())
    n_holm = (
        int(df["dm_holm_rejected"].sum())
        if "dm_holm_rejected" in df.columns
        else 0
    )
    min_p = float(df["dm_pvalue"].min())

    if n_holm > 0:
        return (
            f"Walk-forward DM tests reject H0 (strategy = buy-hold) in "
            f"{n_holm} of {n_total} window tests at α={alpha} after Holm "
            f"correction (raw p<α in {n_raw}). The smallest p-value was "
            f"{min_p:.4f}. This is a genuine — though regime-localised — "
            "rejection. Not a green light to trade live; investigate which "
            "regime the rejecting windows sit in and whether transaction "
            "costs / slippage erase the spread."
        )
    if n_raw > 0:
        return (
            f"{n_raw} of {n_total} window tests have raw DM p < {alpha} "
            f"(min p = {min_p:.4f}), but zero survive Holm correction across "
            f"the family of {n_total} tests. The terminal-period finding "
            "(commit fddfbf8: no test reached α=0.05) holds up: the apparent "
            "spread is concentrated in lucky windows that don't survive "
            "multiple-testing correction. Treat the strategies as "
            "statistically indistinguishable from buy-and-hold on this "
            "sample."
        )
    return (
        f"Every single one of the {n_total} walk-forward window tests has "
        f"raw DM p-value above α={alpha} (minimum p = {min_p:.4f}). After "
        "Holm correction zero windows reject. There is no walk-forward "
        "regime in which the active strategies are statistically distinct "
        "from buy-and-hold on this 5y sample. The terminal-period finding "
        "(commit fddfbf8) generalises temporally: the 16-19pp raw spread is "
        "indistinguishable from noise no matter how you slice the window. "
        "If a real +3pp/yr edge exists you need ~6 years of weekly data to "
        "detect it at 80% power; this 5y sample is underpowered."
    )


def render_markdown_summary(
    df: pd.DataFrame,
    summary: dict[str, object],
) -> str:
    """Render a one-page Markdown summary for ``docs/``."""

    lines: list[str] = []
    lines.append("# Walk-forward statistical-tests summary")
    lines.append("")
    lines.append(
        f"- Period: `{summary.get('period_start', 'n/a')}` → "
        f"`{summary.get('period_end', 'n/a')}`"
    )
    lines.append(
        f"- Window length: **{summary['window_years']} year(s)** · "
        f"Step: **{summary['step_months']} month(s)** · "
        f"alpha = **{summary['alpha']}** (Holm step-down across all tests)"
    )
    strategies_list = cast(list[str], summary["strategies"])
    lines.append(
        f"- Strategies tested vs buy-and-hold: "
        f"{', '.join(f'`{s}`' for s in strategies_list)}"
    )
    lines.append(
        f"- Total window tests: **{summary['n_total_window_tests']}** "
        f"(per strategy: {summary['n_windows_per_strategy']})"
    )
    lines.append("")

    lines.append("## Headline numbers")
    lines.append("")
    lines.append(
        f"- Windows with raw DM p < {summary['alpha']}: "
        f"**{summary['n_raw_significant']}** of "
        f"**{summary['n_total_window_tests']}**"
    )
    lines.append(
        f"- Windows surviving Holm correction (family-wise across all "
        f"{summary['n_total_window_tests']} tests): "
        f"**{summary['n_holm_significant']}**"
    )
    min_p_raw = summary.get("min_pvalue")
    if min_p_raw is not None:
        lines.append(
            f"- Minimum p-value: **{float(cast(float, min_p_raw)):.4f}** — strategy "
            f"`{summary['min_pvalue_strategy']}`, "
            f"window {summary['min_pvalue_window']}"
        )
    lines.append("")

    direction = cast(
        dict[str, float], summary.get("direction_consistency_by_strategy") or {},
    )
    if direction:
        lines.append("## Direction consistency (does strategy beat buy-hold?)")
        lines.append("")
        lines.append(
            "Fraction of walk-forward windows where the DM statistic is "
            "negative (loss-of-strategy < loss-of-buy-hold, i.e. strategy "
            "*beat* buy-hold on the window). 50% = coin-flip; 70%+ = a "
            "consistent direction even if individual windows aren't "
            "significant."
        )
        lines.append("")
        lines.append("| Strategy | Windows beating buy-hold | Fraction |")
        lines.append("| --- | ---: | ---: |")
        n_per_strategy_map = cast(
            dict[str, int], summary["n_windows_per_strategy"],
        )
        for strat in sorted(direction):
            n_windows = n_per_strategy_map.get(strat, 0)
            frac = float(direction[strat])
            wins = round(frac * n_windows)
            lines.append(f"| `{strat}` | {wins} / {n_windows} | {frac:.0%} |")
        lines.append("")

    lines.append("## Per-window detail")
    lines.append("")
    if df.empty:
        lines.append("> No windows emitted.")
    else:
        lines.append(
            "| strategy | window_id | start | end | n | DM stat | DM p | "
            "Sharpe z | Sharpe p | boot p | Holm reject |"
        )
        lines.append(
            "| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | :-: |"
        )
        for _, row in df.iterrows():
            holm = "yes" if bool(row.get("dm_holm_rejected", False)) else "no"
            lines.append(
                f"| `{row['strategy']}` | {int(row['window_id'])} | "
                f"{row['start_date']} | {row['end_date']} | "
                f"{int(row['n_obs'])} | {float(row['dm_stat']):+.3f} | "
                f"{float(row['dm_pvalue']):.4f} | "
                f"{float(row['sharpe_z']):+.3f} | "
                f"{float(row['sharpe_pvalue']):.4f} | "
                f"{float(row['boot_pvalue']):.4f} | {holm} |"
            )
        lines.append("")

    lines.append("## Honest conclusion")
    lines.append("")
    lines.append(str(summary.get("honest_conclusion", "")))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "Methodology: each window runs Diebold-Mariano (loss=negative-return, "
        "Newey-West HAC h=1), Memmel (2003) closed-form Sharpe-difference "
        "test, and Politis-Romano circular block bootstrap on the per-period "
        "return differential vs equal-weight buy-and-hold sampled at the "
        "same rebalance cadence. Windows overlap by design — Holm correction "
        "treats them as a family, which is the right multi-test correction "
        "for 'are any windows significantly different from buy-hold?'."
    )
    lines.append("")
    return "\n".join(lines)


def _render_terminal_summary(df: pd.DataFrame, summary: dict[str, object]) -> str:
    """Compact one-screen terminal table for stdout."""

    lines: list[str] = []
    strategies_terminal = cast(list[str], summary.get("strategies") or [])
    lines.append(
        f"Walk-forward tests: window={summary['window_years']}y "
        f"step={summary['step_months']}mo "
        f"alpha={summary['alpha']} "
        f"strategies={','.join(strategies_terminal)}"
    )
    period_start = summary.get("period_start", "n/a")
    period_end = summary.get("period_end", "n/a")
    lines.append(
        f"Period: {period_start} -> {period_end} | "
        f"total tests: {summary['n_total_window_tests']}"
    )
    lines.append(
        f"Raw p<alpha: {summary['n_raw_significant']}  |  "
        f"Holm-survivor: {summary['n_holm_significant']}  |  "
        f"min p: {summary.get('min_pvalue')}"
    )
    lines.append("")
    if df.empty:
        lines.append("(no window data)")
        return "\n".join(lines)
    header = (
        f"{'strategy':<16}{'win':>4}{'start':>12}{'end':>12}{'n':>5}"
        f"{'DM stat':>10}{'DM p':>9}{'Sh p':>9}{'boot p':>9}{'Holm':>6}"
    )
    lines.append(header)
    for _, row in df.iterrows():
        lines.append(
            f"{row['strategy']!s:<16}"
            f"{int(row['window_id']):>4}"
            f"{row['start_date']:>12}"
            f"{row['end_date']:>12}"
            f"{int(row['n_obs']):>5}"
            f"{float(row['dm_stat']):>+10.3f}"
            f"{float(row['dm_pvalue']):>9.4f}"
            f"{float(row['sharpe_pvalue']):>9.4f}"
            f"{float(row['boot_pvalue']):>9.4f}"
            f"{('yes' if bool(row.get('dm_holm_rejected', False)) else 'no'):>6}"
        )
    lines.append("")
    lines.append(str(summary.get("honest_conclusion", "")))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_strategy_list(raw: str) -> list[str]:
    if not raw:
        return list(DEFAULT_STRATEGY_LABELS)
    items = [s.strip() for s in raw.split(",") if s.strip()]
    unknown = [s for s in items if s not in DEFAULT_STRATEGY_LABELS]
    if unknown:
        raise ValueError(
            f"Unknown strategies {unknown!r}; valid: {list(DEFAULT_STRATEGY_LABELS)}"
        )
    deduped: list[str] = []
    for s in items:
        if s not in deduped:
            deduped.append(s)
    return deduped


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run walk-forward Diebold-Mariano + block bootstrap + Sharpe "
            "tests on rotation / mean_reversion / blend vs equal-weight "
            "buy-and-hold."
        ),
    )
    parser.add_argument(
        "--csv",
        required=True,
        type=Path,
        help="Wide-form ETF price CSV (date index, ETF code columns).",
    )
    parser.add_argument(
        "--window-years",
        type=float,
        default=2.0,
        help="Walk-forward window length in years (fractional OK).",
    )
    parser.add_argument(
        "--step-months",
        type=int,
        default=6,
        help="Step between consecutive walk-forward window starts.",
    )
    parser.add_argument(
        "--strategies",
        default=",".join(DEFAULT_STRATEGY_LABELS),
        help=f"Comma-separated subset of {','.join(DEFAULT_STRATEGY_LABELS)}.",
    )
    parser.add_argument(
        "--rebalance-freq-days",
        type=int,
        default=DEFAULT_REBALANCE_FREQ_DAYS,
        help="Rebalance cadence in business days (default 5 ~ weekly).",
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=DEFAULT_INITIAL_CAPITAL,
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Family-wise significance level for Holm step-down.",
    )
    parser.add_argument(
        "--block-size",
        type=int,
        default=10,
        help="Block size for the Politis-Romano circular block bootstrap.",
    )
    parser.add_argument(
        "--n-bootstrap",
        type=int,
        default=1000,
        help="Number of bootstrap replicates per window.",
    )
    parser.add_argument(
        "--period-start",
        default=None,
        help="Override the period start (default: first date in CSV).",
    )
    parser.add_argument(
        "--period-end",
        default=None,
        help="Override the period end (default: last date in CSV).",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("walkforward_stat_tests.csv"),
        help="Destination for the long-form per-window DataFrame.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("docs/walkforward_stat_tests_summary.md"),
        help="Destination for the one-page Markdown summary.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _build_arg_parser().parse_args(argv)
    try:
        strategy_labels = _parse_strategy_list(args.strategies)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    df, summary = run_walkforward_stat_tests(
        args.csv,
        window_years=args.window_years,
        step_months=args.step_months,
        strategy_labels=strategy_labels,
        rebalance_freq_days=args.rebalance_freq_days,
        initial_capital=args.initial_capital,
        block_size=args.block_size,
        n_bootstrap=args.n_bootstrap,
        alpha=args.alpha,
        period_start=args.period_start,
        period_end=args.period_end,
    )

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output_csv, index=False)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(
        render_markdown_summary(df, summary), encoding="utf-8",
    )

    print(_render_terminal_summary(df, summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
