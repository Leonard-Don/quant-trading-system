#!/usr/bin/env python3
"""Invert the statistical-falsification layer into a falsifiable alpha target.

Background
----------
``scripts/walkforward_stat_tests.py`` and ``docs/walkforward_stat_tests_summary.md``
established the honest *negative* result: the ETF rotation strategy is
statistically **indistinguishable** from equal-weight buy-and-hold on
the 5y sample — every walk-forward Diebold-Mariano test sits above
α=0.05 and zero windows survive Holm correction.

A reader naturally asks the dual question: *"a null result is not the
same as a zero edge — how big would a real edge have to be before this
sample could even see it?"* This script answers exactly that. It does
**not** search for alpha or invent factors (that is open research). It
inverts the DM test:

    Given the HAC variance structure the walk-forward DM tests already
    measured, solve for the **Minimum Detectable Effect (MDE)** — the
    smallest true Information Ratio / annualised excess return at which
    the DM test reaches the requested power (default 80%) on the
    available sample.

The MDE is a *falsifiable target*: if the rotation strategy's true edge
is below the MDE IR, the 5y sample is underpowered and "no significant
edge" tells you nothing; only an edge at or above the MDE could have
been detected. Quote it honestly — "the strategy would need ≥ X IR to
be statistically detectable on this sample; below that we cannot tell
it apart from noise."

Method
------
The DM statistic for ``loss_fn="negative_return"`` is
``DM = d_mean / sqrt(hac_var / n)`` and the annualised Information Ratio
is ``IR = DM * sqrt(periods_per_year / n)``. Holding the *observed*
per-period Newey-West HAC variance fixed, the two-sided test at level α
reaches power ``1-β`` when the non-centrality hits
``z_{1-α/2} + z_{β}``; inverting gives
``mde_ir = (z_{1-α/2} + z_{β}) * sqrt(periods_per_year / n)``. See
:func:`src.backtest.strategy_statistical_tests.minimum_detectable_effect`
for the full derivation. The inversion is exact (closed-form, no
simulation); ``--self-check`` re-feeds the MDE IR through the forward
power calculation to prove it lands back on the requested power.

Typical use
-----------
::

    python scripts/power_target.py \
        --csv data/etf_backtest/etf_prices_5y.csv \
        --strategy rotation \
        --power 0.80 \
        --output-md docs/falsifiable_alpha_target.md

Outputs a terminal summary plus (optionally) a Markdown doc. With
``--per-window`` it also inverts every walk-forward window so you can
see how the MDE shrinks/grows with window length.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.compare_strategies import (  # noqa: E402
    load_price_matrix,
    run_comparison,
)
from scripts.walkforward_stat_tests import (  # noqa: E402
    _align_strategy_vs_buy_hold,
    _buy_hold_return_series,
    _strategy_return_series,
)
from src.backtest.etf_rotation_backtest import (  # noqa: E402
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_REBALANCE_FREQ_DAYS,
)
from src.backtest.strategy_comparison import DEFAULT_STRATEGY_LABELS  # noqa: E402
from src.backtest.strategy_statistical_tests import (  # noqa: E402
    MinimumDetectableEffect,
    _iter_walk_forward_bounds,
    diebold_mariano_test,
    dm_power_for_information_ratio,
    minimum_detectable_effect_from_dm,
)

logger = logging.getLogger(__name__)

# Trading weeks per year — the ETF rotation walk-forward rebalances
# weekly (DEFAULT_REBALANCE_FREQ_DAYS = 5 business days), so an IR / a
# tracking error annualises with sqrt(52). Daily strategies would pass
# ~252 instead.
WEEKS_PER_YEAR: float = 52.0


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def compute_alpha_target(
    csv_path: Path,
    *,
    strategy_label: str = "rotation",
    alpha: float = 0.05,
    power: float = 0.80,
    window_years: float = 2.0,
    step_months: int = 6,
    rebalance_freq_days: int = DEFAULT_REBALANCE_FREQ_DAYS,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    periods_per_year: float = WEEKS_PER_YEAR,
    blend_regime: str = "unknown",
    include_per_window: bool = True,
) -> dict[str, object]:
    """Run the full inversion pipeline and return a summary dict.

    Steps:

    1. Load the price CSV and run :class:`StrategyComparator` so the
       chosen strategy and equal-weight buy-and-hold get per-rebalance
       return series sampled at the same cadence.
    2. Align the two series and run the *terminal-period* DM test —
       its ``hac_variance`` / ``n_obs`` anchor the headline MDE.
    3. Invert the DM result into a :class:`MinimumDetectableEffect`.
    4. (Optional) repeat the inversion per walk-forward window so the
       reader sees how the MDE moves with sample size.

    The returned dict is JSON-friendly and feeds both the terminal
    renderer and the Markdown writer.
    """

    prices = load_price_matrix(csv_path)
    if prices.empty:
        raise ValueError(f"Empty price matrix from {csv_path!r}")

    period_start = str(prices.index[0].date())
    period_end = str(prices.index[-1].date())

    comparison = run_comparison(
        csv_path,
        period_start=period_start,
        period_end=period_end,
        strategy_labels=[strategy_label],
        rebalance_freq_days=rebalance_freq_days,
        initial_capital=initial_capital,
        blend_regime=blend_regime,
        compute_statistical_tests=False,
    )
    report = comparison.per_strategy_metrics.get(strategy_label)
    if report is None:
        raise ValueError(
            f"strategy {strategy_label!r} not present in comparison report"
        )

    strat_returns = _strategy_return_series(report)
    bh_returns = _buy_hold_return_series(
        prices,
        period_start=pd.Timestamp(period_start),
        period_end=pd.Timestamp(period_end),
        rebalance_freq_days=rebalance_freq_days,
    )
    aligned_a, aligned_b = _align_strategy_vs_buy_hold(strat_returns, bh_returns)
    if aligned_a.empty or len(aligned_a) < 2:
        raise ValueError(
            f"strategy {strategy_label!r} shares too few dates with "
            "buy-and-hold to invert the test"
        )

    # --- Terminal-period DM + inversion ---
    terminal_dm = diebold_mariano_test(
        aligned_a.tolist(),
        aligned_b.tolist(),
        loss_fn="negative_return",
        h=1,
    )
    terminal_mde = minimum_detectable_effect_from_dm(
        terminal_dm,
        alpha=alpha,
        power=power,
        periods_per_year=periods_per_year,
    )

    result: dict[str, object] = {
        "strategy": strategy_label,
        "period_start": period_start,
        "period_end": period_end,
        "alpha": alpha,
        "power": power,
        "periods_per_year": periods_per_year,
        "rebalance_freq_days": rebalance_freq_days,
        "terminal": {
            "dm_statistic": terminal_dm.dm_statistic,
            "dm_pvalue": terminal_dm.p_value,
            "mean_loss_differential": terminal_dm.mean_loss_differential,
            "mde": terminal_mde.to_dict(),
        },
    }

    if include_per_window:
        per_window = _per_window_mde(
            aligned_a,
            aligned_b,
            window_years=window_years,
            step_months=step_months,
            alpha=alpha,
            power=power,
            periods_per_year=periods_per_year,
        )
        result["window_years"] = window_years
        result["step_months"] = step_months
        result["per_window"] = per_window

    return result


def _per_window_mde(
    aligned_a: pd.Series,
    aligned_b: pd.Series,
    *,
    window_years: float,
    step_months: int,
    alpha: float,
    power: float,
    periods_per_year: float,
) -> list[dict[str, object]]:
    """Invert the DM test on every walk-forward window.

    Reuses :func:`_iter_walk_forward_bounds` (the same window iterator
    the walk-forward stat-tests CLI uses) so the window boundaries line
    up exactly with ``docs/walkforward_stat_tests.csv``.
    """

    a_arr = aligned_a.to_numpy(dtype=float)
    b_arr = aligned_b.to_numpy(dtype=float)
    ts_index = pd.DatetimeIndex(pd.to_datetime(aligned_a.index))

    rows: list[dict[str, object]] = []
    for window_id, start_ts, end_ts, sl in _iter_walk_forward_bounds(
        ts_index,
        window_years=window_years,
        step_months=step_months,
    ):
        dm = diebold_mariano_test(
            a_arr[sl].tolist(),
            b_arr[sl].tolist(),
            loss_fn="negative_return",
            h=1,
        )
        if dm.n_obs < 2:
            continue
        mde = minimum_detectable_effect_from_dm(
            dm,
            alpha=alpha,
            power=power,
            periods_per_year=periods_per_year,
        )
        rows.append(
            {
                "window_id": int(window_id),
                "start_date": str(start_ts.date()),
                "end_date": str(end_ts.date()),
                "n_obs": dm.n_obs,
                "dm_statistic": dm.dm_statistic,
                "mde_ir": mde.mde_ir,
                "mde_excess_return_annual": mde.mde_excess_return_annual,
                "observed_ir": mde.observed_ir,
                "annualized_tracking_error": mde.annualized_tracking_error,
            }
        )
    return rows


def self_check(mde: MinimumDetectableEffect) -> dict[str, float]:
    """Round-trip the MDE: feed ``mde_ir`` back through the power formula.

    A correct inversion means a strategy whose *true* IR is exactly
    ``mde_ir`` is detected with probability ≈ the requested ``power``.
    Returns the recovered power and its absolute deviation from target.
    """

    recovered = dm_power_for_information_ratio(
        mde.mde_ir,
        mde.n_obs,
        alpha=mde.alpha,
        periods_per_year=mde.periods_per_year,
    )
    return {
        "target_power": mde.power,
        "recovered_power": recovered,
        "abs_error": abs(recovered - mde.power),
    }


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def _fmt_pct(value: float) -> str:
    return f"{value * 100:+.2f}%"


def render_terminal(result: dict[str, object]) -> str:
    """Compact one-screen terminal summary."""

    terminal = cast_dict(result["terminal"])
    mde = cast_dict(terminal["mde"])
    lines: list[str] = []
    lines.append(
        f"Falsifiable alpha target — strategy={result['strategy']} "
        f"vs equal-weight buy-and-hold"
    )
    lines.append(
        f"Period: {result['period_start']} -> {result['period_end']} | "
        f"n={mde['n_obs']} rebalance periods | "
        f"alpha={result['alpha']} power={result['power']:.0%}"
    )
    lines.append("")
    lines.append(
        f"Observed:  IR={float(mde['observed_ir']):+.4f}  "
        f"excess return={_fmt_pct(float(mde['observed_excess_return_annual']))}/yr  "
        f"(DM stat={float(terminal['dm_statistic']):+.3f}, "
        f"p={float(terminal['dm_pvalue']):.4f})"
    )
    lines.append(
        f"Annualized tracking error: "
        f"{float(mde['annualized_tracking_error']) * 100:.2f}%  "
        f"(per-period HAC variance={float(mde['hac_variance']):.3e})"
    )
    lines.append("")
    lines.append(">>> MINIMUM DETECTABLE EFFECT (the falsifiable target) <<<")
    lines.append(
        f"    MDE Information Ratio       = {float(mde['mde_ir']):.4f}"
    )
    lines.append(
        f"    MDE annualized excess return= "
        f"{_fmt_pct(float(mde['mde_excess_return_annual']))}/yr"
    )
    lines.append(
        f"    MDE per-rebalance excess    = "
        f"{_fmt_pct(float(mde['mde_excess_return_per_period']))}/period"
    )
    lines.append(
        f"    required non-centrality     = {float(mde['required_ncp']):.4f}"
    )
    lines.append("")
    observed_ir = abs(float(mde["observed_ir"]))
    mde_ir = float(mde["mde_ir"])
    if observed_ir < mde_ir:
        lines.append(
            f"Verdict: |observed IR| {observed_ir:.3f} < MDE IR {mde_ir:.3f} "
            "-> the strategy sits INSIDE the noise floor. The 5y sample is "
            "underpowered: 'no significant edge' does not imply 'no edge'."
        )
    else:
        lines.append(
            f"Verdict: |observed IR| {observed_ir:.3f} >= MDE IR {mde_ir:.3f} "
            "-> the observed effect is large enough that the test should "
            "have power to see it; inspect the DM p-value directly."
        )

    per_window = result.get("per_window")
    if per_window:
        windows = list(per_window)  # type: ignore[arg-type]
        lines.append("")
        lines.append("Per walk-forward window:")
        lines.append(
            f"{'win':>4}{'start':>13}{'end':>13}{'n':>5}"
            f"{'MDE IR':>10}{'MDE ret/yr':>13}{'obs IR':>10}"
        )
        for row in windows:
            w = cast_dict(row)
            lines.append(
                f"{int(w['window_id']):>4}"
                f"{w['start_date']!s:>13}"
                f"{w['end_date']!s:>13}"
                f"{int(w['n_obs']):>5}"
                f"{float(w['mde_ir']):>10.4f}"
                f"{_fmt_pct(float(w['mde_excess_return_annual'])):>13}"
                f"{float(w['observed_ir']):>+10.4f}"
            )
    return "\n".join(lines)


def render_markdown(result: dict[str, object]) -> str:
    """Render the falsifiable-alpha-target doc for ``docs/``."""

    terminal = cast_dict(result["terminal"])
    mde = cast_dict(terminal["mde"])
    n_obs = int(mde["n_obs"])
    mde_ir = float(mde["mde_ir"])
    observed_ir = float(mde["observed_ir"])
    power_pct = f"{float(result['power']):.0%}"

    lines: list[str] = []
    lines.append("# Falsifiable alpha target (power-analysis inversion)")
    lines.append("")
    lines.append(
        "This doc is the **inversion** of the statistical-falsification "
        "layer. `docs/walkforward_stat_tests_summary.md` established the "
        "honest negative result — the ETF rotation strategy is "
        "statistically indistinguishable from buy-and-hold on the 5y "
        "sample. A null result is *not* a zero edge, so the natural "
        "follow-up is: **how large would a true edge have to be before "
        "this sample could detect it?** That threshold — the Minimum "
        "Detectable Effect (MDE) — is computed below. It is a falsifiable "
        "target, not a claim that the strategy *has* an edge."
    )
    lines.append("")
    lines.append("## Inputs")
    lines.append("")
    lines.append(f"- Strategy: `{result['strategy']}` vs equal-weight buy-and-hold")
    lines.append(
        f"- Period: `{result['period_start']}` -> `{result['period_end']}`"
    )
    lines.append(
        f"- Sample size: **{n_obs}** rebalance periods "
        f"(weekly cadence, {result['rebalance_freq_days']} business days)"
    )
    lines.append(
        f"- Test: two-sided Diebold-Mariano (loss = negative-return, "
        f"Newey-West HAC h=1) at alpha = **{result['alpha']}**"
    )
    lines.append(f"- Target power: **{power_pct}**")
    lines.append(
        f"- Annualisation: **{result['periods_per_year']:.0f}** "
        "rebalance periods per year"
    )
    lines.append("")
    lines.append("## What the sample actually shows")
    lines.append("")
    lines.append("| Quantity | Value |")
    lines.append("| --- | ---: |")
    lines.append(
        f"| Observed Information Ratio | {observed_ir:+.4f} |"
    )
    lines.append(
        f"| Observed annualised excess return | "
        f"{_fmt_pct(float(mde['observed_excess_return_annual']))}/yr |"
    )
    lines.append(
        f"| Terminal-period DM statistic | "
        f"{float(terminal['dm_statistic']):+.3f} |"
    )
    lines.append(
        f"| Terminal-period DM p-value (2-sided) | "
        f"{float(terminal['dm_pvalue']):.4f} |"
    )
    lines.append(
        f"| Annualised tracking error | "
        f"{float(mde['annualized_tracking_error']) * 100:.2f}% |"
    )
    lines.append("")
    lines.append("## The falsifiable target — Minimum Detectable Effect")
    lines.append("")
    lines.append(
        f"On this {n_obs}-period sample, holding the observed HAC variance "
        f"structure fixed, the DM test reaches **{power_pct} power** at "
        f"alpha = {result['alpha']} only if the strategy's *true* edge is "
        "at least:"
    )
    lines.append("")
    lines.append("| MDE (the target) | Value |")
    lines.append("| --- | ---: |")
    lines.append(f"| **Information Ratio** | **{mde_ir:.4f}** |")
    lines.append(
        f"| Annualised excess return | "
        f"**{_fmt_pct(float(mde['mde_excess_return_annual']))}/yr** |"
    )
    lines.append(
        f"| Per-rebalance excess return | "
        f"{_fmt_pct(float(mde['mde_excess_return_per_period']))}/period |"
    )
    lines.append(
        f"| Required non-centrality (z_(1-a/2) + z_power) | "
        f"{float(mde['required_ncp']):.4f} |"
    )
    lines.append("")
    lines.append("## Honest interpretation")
    lines.append("")
    if abs(observed_ir) < mde_ir:
        lines.append(
            f"The strategy's observed IR ({observed_ir:+.4f}) is **inside "
            f"the noise floor** — its magnitude is below the MDE IR of "
            f"{mde_ir:.4f}. This is the load-bearing conclusion: on this "
            "sample the strategy **cannot be told apart from buy-and-hold**, "
            "and 'no statistically significant edge' carries *no* "
            "information about whether a smaller real edge exists. The "
            f"sample would need a true IR of **>= {mde_ir:.2f}** before the "
            "DM test could reliably (>= "
            f"{power_pct}) reject the null."
        )
    else:
        lines.append(
            f"The strategy's observed IR ({observed_ir:+.4f}) exceeds the "
            f"MDE IR ({mde_ir:.4f}) in magnitude, so the test has adequate "
            "power for an effect this size — read the DM p-value directly "
            "rather than treating the result as underpowered."
        )
    lines.append("")
    lines.append(
        f"A useful frame: an IR of {mde_ir:.2f} is an *institutional-grade* "
        "bar — sustained Information Ratios above 1.0 are rare even for "
        "professional managers. The reason the bar is this high is the "
        "strategy's large tracking error "
        f"({float(mde['annualized_tracking_error']) * 100:.1f}% annualised) "
        "relative to any plausible alpha: the rotation strategy deviates "
        "substantially from the benchmark, so it needs a *correspondingly "
        "large* mean excess return to clear the noise. Shrinking the "
        "tracking error (tighter active weights, lower turnover) lowers "
        "the MDE just as effectively as raising raw alpha."
    )
    lines.append("")
    lines.append(
        "Equivalently: to detect the rotation strategy's currently "
        f"*observed* point-estimate edge "
        f"({_fmt_pct(float(mde['observed_excess_return_annual']))}/yr) at "
        f"{power_pct} power you would need roughly "
        f"`(required_ncp / observed_IR)^2 * periods_per_year` rebalance "
        "periods — far more than the "
        f"{n_obs} this 5y sample provides. The honest move is to either "
        "(a) collect a longer / higher-frequency sample, (b) re-engineer "
        "the strategy for a thinner tracking error, or (c) accept that "
        "the edge — if any — is below this sample's resolution and stop "
        "treating the backtest spread as signal."
    )
    lines.append("")

    per_window = result.get("per_window")
    if per_window:
        windows = list(per_window)  # type: ignore[arg-type]
        lines.append("## Per walk-forward window")
        lines.append("")
        lines.append(
            f"Each {result.get('window_years')}-year walk-forward window "
            "inverted independently. Shorter windows have fewer "
            "observations and therefore a *higher* MDE — they can detect "
            "even less."
        )
        lines.append("")
        lines.append(
            "| window | start | end | n | MDE IR | MDE excess return/yr "
            "| observed IR |"
        )
        lines.append("| ---: | --- | --- | ---: | ---: | ---: | ---: |")
        for row in windows:
            w = cast_dict(row)
            lines.append(
                f"| {int(w['window_id'])} | {w['start_date']} | "
                f"{w['end_date']} | {int(w['n_obs'])} | "
                f"{float(w['mde_ir']):.4f} | "
                f"{_fmt_pct(float(w['mde_excess_return_annual']))} | "
                f"{float(w['observed_ir']):+.4f} |"
            )
        lines.append("")

    lines.append("## Code integration")
    lines.append("")
    lines.append(
        "The reusable power-analysis primitive lives in "
        "`src.backtest.strategy_statistical_tests.minimum_detectable_effect`. "
        "`scripts/power_target.py` applies it to the ETF rotation vs "
        "buy-and-hold comparison and renders this falsifiable-alpha report. "
        "The generic `src.backtest.batch_backtester.WalkForwardAnalyzer` uses "
        "the same inversion for its `statistical_power_diagnostics` payload, "
        "so batch walk-forward output can flag `observed_effect_inside_noise_floor` "
        "instead of over-reading noisy sample-out windows."
    )
    lines.append("")

    lines.append("## Method")
    lines.append("")
    lines.append(
        "The Diebold-Mariano statistic for the negative-return loss is "
        "`DM = d_mean / sqrt(hac_var / n)`, where `d_mean` is the mean "
        "loss differential, `-d_mean` is the per-period excess return, "
        "and `hac_var` is the per-period Newey-West HAC variance of the "
        "differential. The annualised Information Ratio relates to it by "
        "`IR = DM * sqrt(periods_per_year / n)`. Under the alternative "
        "the two-sided test at level alpha reaches power `1-b` when the "
        "non-centrality of `|DM|` solves the same two-tail power equation "
        "used by the forward check:"
    )
    lines.append("")
    lines.append("```")
    lines.append("power = Phi(required_ncp - z_(1-a/2)) + Phi(-required_ncp - z_(1-a/2))")
    lines.append("mde_ir = required_ncp * sqrt(periods_per_year / n)")
    lines.append("mde_excess_return_per_period = required_ncp * sqrt(hac_var / n)")
    lines.append("```")
    lines.append("")
    lines.append(
        "The inversion is solved numerically (no simulation). It is "
        "implemented in "
        "`src.backtest.strategy_statistical_tests.minimum_detectable_effect` "
        "and round-trip-verified: feeding `mde_ir` back through "
        "`dm_power_for_information_ratio` recovers the requested power "
        f"({power_pct}) to within floating-point tolerance. Regenerate "
        "this doc with `python scripts/power_target.py "
        "--csv data/etf_backtest/etf_prices_5y.csv "
        "--output-md docs/falsifiable_alpha_target.md`."
    )
    lines.append("")
    return "\n".join(lines)


def cast_dict(value: object) -> dict[str, object]:
    """Narrow an ``object`` known to be a dict (keeps mypy + readers happy)."""

    assert isinstance(value, dict)
    return value


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Invert the Diebold-Mariano statistical layer into a "
            "falsifiable alpha target: the Minimum Detectable Effect "
            "(IR / annualised excess return) at the requested power."
        ),
    )
    parser.add_argument(
        "--csv",
        required=True,
        type=Path,
        help="Wide-form ETF price CSV (date index, ETF code columns).",
    )
    parser.add_argument(
        "--strategy",
        default="rotation",
        choices=tuple(DEFAULT_STRATEGY_LABELS),
        help="Strategy to invert against equal-weight buy-and-hold.",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Two-sided significance level for the DM test.",
    )
    parser.add_argument(
        "--power",
        type=float,
        default=0.80,
        help="Target statistical power (1 - beta) to solve the MDE for.",
    )
    parser.add_argument(
        "--window-years",
        type=float,
        default=2.0,
        help="Walk-forward window length in years (for --per-window).",
    )
    parser.add_argument(
        "--step-months",
        type=int,
        default=6,
        help="Step between walk-forward window starts (for --per-window).",
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
        "--periods-per-year",
        type=float,
        default=WEEKS_PER_YEAR,
        help="Annualisation factor (52 for weekly, ~252 for daily).",
    )
    parser.add_argument(
        "--blend-regime",
        default="unknown",
        choices=("bull", "correction", "sideways", "bear", "crisis", "unknown"),
        help=(
            "Regime label for EtfStrategyBlend; only relevant when "
            "--strategy blend. The default 'unknown' resolves to alpha=1.0 "
            "(blend collapses to pure rotation)."
        ),
    )
    parser.add_argument(
        "--no-per-window",
        action="store_true",
        help="Skip the per-walk-forward-window MDE breakdown.",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help=(
            "Round-trip the MDE: feed mde_ir back through the forward "
            "power calc and assert it recovers the requested power."
        ),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help=(
            "Optional destination for the Markdown doc "
            "(e.g. docs/falsifiable_alpha_target.md)."
        ),
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _build_arg_parser().parse_args(argv)

    result = compute_alpha_target(
        args.csv,
        strategy_label=args.strategy,
        alpha=args.alpha,
        power=args.power,
        window_years=args.window_years,
        step_months=args.step_months,
        rebalance_freq_days=args.rebalance_freq_days,
        initial_capital=args.initial_capital,
        periods_per_year=args.periods_per_year,
        blend_regime=args.blend_regime,
        include_per_window=not args.no_per_window,
    )

    print(render_terminal(result))

    if args.self_check:
        terminal = cast_dict(result["terminal"])
        mde_dict = cast_dict(terminal["mde"])
        mde = MinimumDetectableEffect(**mde_dict)  # type: ignore[arg-type]
        check = self_check(mde)
        print("")
        print(
            f"Self-check: target power={check['target_power']:.4f}  "
            f"recovered={check['recovered_power']:.4f}  "
            f"abs error={check['abs_error']:.2e}"
        )
        if check["abs_error"] > 1e-6:
            print("error: round-trip power deviates beyond tolerance", file=sys.stderr)
            return 1

    if args.output_md is not None:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(render_markdown(result), encoding="utf-8")
        print("")
        print(f"Markdown written to {args.output_md}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
