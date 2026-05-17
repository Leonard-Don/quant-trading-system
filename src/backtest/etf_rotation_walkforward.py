"""Walkforward stability analyzer for :class:`EtfRotationBacktester`.

The single-window backtest (see ``src/backtest/etf_rotation_backtest.py``,
committed at ``840addf``) answers "did the strategy work in *this* window?"
— one data point. That's noisy by construction: a single window can hide
either a lucky run or an unlucky tape regime that masks real edge.

This module rolls the same harness across multiple overlapping/sliding
windows of the *same* historical price matrix and aggregates the
per-window metrics into a stability picture: median window return, % of
windows that finished positive, dispersion of Sharpe and drawdown, and a
0-to-1 ``consistency_score`` that summarises how much the windows agree
on the strategy's direction.

What walkforward *can* answer
------------------------------
* "Does the strategy beat zero in most regimes, or only in one lucky
  window?" → ``pct_positive_windows``.
* "How much does realised performance jitter across windows?" → standard
  deviation of window returns + ``consistency_score``.
* "Is the worst-case drawdown localised to one window or a recurring
  feature?" → ``worst_window_dd_pct`` vs. ``mean_max_dd_pct``.
* "Does enabling ``policy_signal_factor`` help on average across
  windows?" → run twice (``policy_signal_factor_enabled`` on vs off) and
  compare the two reports.

What walkforward *cannot* answer (v0.1 inherited caveats)
---------------------------------------------------------
All v0.1 backtest caveats carry over unchanged — no transaction costs,
no bid-ask spread/slippage, no market impact, next-bar close fills only,
no survivorship handling. The walkforward is a *stability* layer over
the single-window harness; it does NOT add execution realism. See
:meth:`EtfRotationBacktester._build_caveats` for the per-window list.

Sequential execution
--------------------
v0.1 runs windows **sequentially**. Parallelising via multiprocessing is
tempting (~13 windows ≈ embarrassingly parallel) but adds risk for v0.1:
the backtester wraps the production ``EtfRotationStrategy`` which isn't
known to be pickle-clean for every config, and process-spawn overhead on
small windows can swallow the wall-clock win. Revisit once we have a
benchmark showing the sequential cost is actually painful in practice.
"""

from __future__ import annotations

import logging
import math
import statistics
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional, Union

import pandas as pd

from src.backtest.etf_rotation_backtest import (
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_REBALANCE_FREQ_DAYS,
    BacktestReport,
    EtfRotationBacktester,
    _sanitize_for_json,
)
from src.backtest.transaction_costs import TransactionCostModel
from src.strategy.etf_rotation_strategy import EtfRotationConfig

logger = logging.getLogger(__name__)


DEFAULT_WINDOW_MONTHS = 3
DEFAULT_STEP_MONTHS = 1


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WalkforwardReport:
    """Structured aggregate over a list of per-window :class:`BacktestReport`.

    Field semantics
    ---------------
    * ``period_start`` / ``period_end`` — the *outer* analysis bounds the
      caller passed (not the union of executed windows; an empty window
      list still echoes the caller's bounds for traceability).
    * ``window_months`` / ``step_months`` — generation knobs preserved on
      the report so downstream tooling doesn't have to re-derive them.
    * ``windows`` — every per-window :class:`BacktestReport` in
      chronological order. Empty (``[]``) when no window could be
      generated (period shorter than ``window_months``, no price data,
      etc.). ``windows[i].period_start`` / ``period_end`` reflect the
      *executed* window bounds (snapped to actual trading days), which
      may differ slightly from the abstract month-boundary cursor.
    * ``aggregate_return_pct`` — geometric compound of window returns
      (``∏(1 + r_i) - 1``). Useful as a "what if I traded every window
      back to back?" snapshot; **not** the literal P&L of a continuous
      strategy because overlapping windows double-count their overlap.
      Annotated in the caveats.
    * ``median_window_return_pct`` — median of per-window total returns.
      Robust to one extreme window dominating ``aggregate_return_pct``.
    * ``mean_window_return_pct`` — arithmetic mean of per-window total
      returns. Stored alongside the median so the caller can spot
      skewed-vs-symmetric distributions at a glance.
    * ``pct_positive_windows`` — fraction of windows with
      ``total_return_pct > 0``, in ``[0.0, 1.0]``. The headline "did the
      strategy survive in most windows?" stat.
    * ``mean_sharpe`` / ``median_sharpe`` — central tendency of
      annualised Sharpe across windows. Mean is sensitive to outliers,
      median is the honest central read.
    * ``mean_max_dd_pct`` / ``worst_window_dd_pct`` — average vs. worst
      drawdown per window. The gap between them flags concentrated
      drawdown risk: small gap = drawdowns evenly distributed across
      windows; big gap = one window blew up.
    * ``return_std_pct`` — sample standard deviation (``ddof=1``) of
      window returns, surfaced so the caller has the dispersion stat
      directly rather than re-deriving it from ``windows``.
    * ``mean_buy_hold_return_pct`` — arithmetic mean of per-window
      ``comparable_buy_hold_return_pct``. Pair with
      ``mean_window_return_pct`` to see whether the strategy *on
      average* beats naive buy-hold across the same windows.
    * ``consistency_score`` — single-number health score in ``[0.0,
      1.0]``. Defined as the harmonic-style blend
      ``positive_fraction * (1 / (1 + cv_of_returns))`` where ``cv`` is
      the coefficient of variation (std / |mean|) of per-window returns.
      The ``positive_fraction`` term enforces "most windows must be
      positive"; the ``1 / (1 + cv)`` term penalises dispersion even
      when the mean is positive. Clamped to ``[0, 1]``. Documented in
      :func:`_compute_consistency_score`.
    * ``policy_signal_factor_enabled`` — value passed through. Reports
      from on vs off runs can be compared by inspecting this flag.
    * ``caveats`` — every per-window caveat, deduplicated, plus the
      walkforward-specific ones (overlapping windows, sequential
      execution, aggregate compounding caveat).
    """

    period_start: Optional[str]
    period_end: Optional[str]
    window_months: int
    step_months: int
    n_windows: int
    rebalance_freq_days: int
    initial_capital: float
    policy_signal_factor_enabled: bool
    windows: list[BacktestReport] = field(default_factory=list)
    aggregate_return_pct: float = 0.0
    mean_window_return_pct: float = 0.0
    median_window_return_pct: float = 0.0
    return_std_pct: float = 0.0
    pct_positive_windows: float = 0.0
    mean_sharpe: float = 0.0
    median_sharpe: float = 0.0
    mean_max_dd_pct: float = 0.0
    worst_window_dd_pct: float = 0.0
    mean_buy_hold_return_pct: float = 0.0
    consistency_score: float = 0.0
    # Transaction-cost summary aggregated across the executed windows.
    # When ``tc_enabled=False`` the fields are zero so the schema is
    # uniform regardless of the TC flag.
    tc_enabled: bool = False
    mean_gross_return_pct: float = 0.0
    mean_net_return_pct: float = 0.0
    mean_tc_cost_pct: float = 0.0
    mean_tc_drag_annualized_pct: float = 0.0
    tc_model_params: Optional[dict[str, Any]] = None
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict (NaN/Inf converted to ``None``)."""

        # asdict() walks nested dataclasses (each BacktestReport included).
        # The shared sanitiser handles NaN/Inf so the FastAPI default encoder
        # accepts the payload without ``allow_nan`` shenanigans.
        return _sanitize_for_json(asdict(self))


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class EtfRotationWalkforwardAnalyzer:
    """Roll :class:`EtfRotationBacktester` across overlapping windows.

    Usage::

        analyzer = EtfRotationWalkforwardAnalyzer(
            config=build_strategy_config(...),
            price_history=price_matrix,
            window_months=3,
            step_months=1,
            period_start="2024-01-01",
            period_end="2025-04-30",
        )
        report = analyzer.run()
        print(report.consistency_score, report.pct_positive_windows)

    Determinism: identical inputs always produce identical reports — no
    RNG, no live data, no environment knobs.
    """

    def __init__(
        self,
        config: EtfRotationConfig,
        price_history: pd.DataFrame,
        *,
        window_months: int = DEFAULT_WINDOW_MONTHS,
        step_months: int = DEFAULT_STEP_MONTHS,
        period_start: Optional[Union[str, datetime, pd.Timestamp]] = None,
        period_end: Optional[Union[str, datetime, pd.Timestamp]] = None,
        policy_signal_factor_enabled: bool = False,
        industry_signals: Optional[Mapping[str, Mapping[str, Any]]] = None,
        etf_industry_map: Optional[Mapping[str, str]] = None,
        rebalance_freq_days: int = DEFAULT_REBALANCE_FREQ_DAYS,
        initial_capital: float = DEFAULT_INITIAL_CAPITAL,
        tc_model: Optional[TransactionCostModel] = None,
    ) -> None:
        if window_months < 1:
            raise ValueError("window_months must be >= 1")
        if step_months < 1:
            raise ValueError("step_months must be >= 1")
        if rebalance_freq_days < 1:
            raise ValueError("rebalance_freq_days must be >= 1")
        if initial_capital <= 0:
            raise ValueError("initial_capital must be > 0")

        self._config = config
        # Keep the full price history intact so every per-window backtest
        # sees the strategy's warmup (60 days by default). The backtester
        # slices AFTER signal generation — passing a pre-sliced frame
        # would lose the warmup or force callers to pre-pad.
        self._price_history = price_history
        self._window_months = int(window_months)
        self._step_months = int(step_months)
        self._period_start = _to_timestamp(period_start)
        self._period_end = _to_timestamp(period_end)
        self._policy_factor_enabled = bool(policy_signal_factor_enabled)
        self._industry_signals = dict(industry_signals) if industry_signals else None
        self._etf_industry_map = dict(etf_industry_map) if etf_industry_map else None
        self._rebalance_freq_days = int(rebalance_freq_days)
        self._initial_capital = float(initial_capital)
        self._tc_model = tc_model

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> WalkforwardReport:
        """Generate windows, run each, aggregate, return a :class:`WalkforwardReport`.

        Returns an empty-windows report (with ``caveats`` explaining why)
        rather than raising on degenerate inputs, mirroring the v0.1
        backtester contract.
        """

        outer_start = self._period_start
        outer_end = self._period_end
        windows_bounds = list(
            _iter_window_bounds(
                outer_start,
                outer_end,
                window_months=self._window_months,
                step_months=self._step_months,
            )
        )
        if not windows_bounds:
            return self._empty_report("no_windows_generated")

        window_reports: list[BacktestReport] = []
        for win_start, win_end in windows_bounds:
            backtester = EtfRotationBacktester(
                config=self._config,
                price_history=self._price_history,
                period_start=win_start,
                period_end=win_end,
                policy_signal_factor_enabled=self._policy_factor_enabled,
                industry_signals=self._industry_signals,
                etf_industry_map=self._etf_industry_map,
                rebalance_freq_days=self._rebalance_freq_days,
                initial_capital=self._initial_capital,
                tc_model=self._tc_model,
            )
            report = backtester.run()
            window_reports.append(report)

        # Keep only windows that actually produced returns; an empty/short
        # window contributes noise to medians and won't have a meaningful
        # Sharpe / drawdown reading.
        executed = [r for r in window_reports if r.n_bars >= 2]
        if not executed:
            return self._empty_report(
                "all_windows_empty (insufficient_history_or_window_too_small)",
                windows=window_reports,
            )

        agg = _aggregate_metrics(executed)
        caveats = self._build_caveats(executed)

        return WalkforwardReport(
            period_start=(
                str(outer_start.date()) if outer_start is not None else None
            ),
            period_end=(
                str(outer_end.date()) if outer_end is not None else None
            ),
            window_months=self._window_months,
            step_months=self._step_months,
            n_windows=len(executed),
            rebalance_freq_days=self._rebalance_freq_days,
            initial_capital=self._initial_capital,
            policy_signal_factor_enabled=self._policy_factor_enabled,
            windows=executed,
            aggregate_return_pct=agg["aggregate_return_pct"],
            mean_window_return_pct=agg["mean_window_return_pct"],
            median_window_return_pct=agg["median_window_return_pct"],
            return_std_pct=agg["return_std_pct"],
            pct_positive_windows=agg["pct_positive_windows"],
            mean_sharpe=agg["mean_sharpe"],
            median_sharpe=agg["median_sharpe"],
            mean_max_dd_pct=agg["mean_max_dd_pct"],
            worst_window_dd_pct=agg["worst_window_dd_pct"],
            mean_buy_hold_return_pct=agg["mean_buy_hold_return_pct"],
            consistency_score=agg["consistency_score"],
            tc_enabled=self._tc_model is not None,
            mean_gross_return_pct=agg["mean_gross_return_pct"],
            mean_net_return_pct=agg["mean_net_return_pct"],
            mean_tc_cost_pct=agg["mean_tc_cost_pct"],
            mean_tc_drag_annualized_pct=agg["mean_tc_drag_annualized_pct"],
            tc_model_params=(
                self._tc_model.to_dict() if self._tc_model is not None else None
            ),
            caveats=caveats,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_caveats(self, executed: Sequence[BacktestReport]) -> list[str]:
        # Walkforward-specific caveats first, then dedupe/merge per-window
        # caveats so the user sees the full provenance without N copies of
        # "no_transaction_costs_modeled".
        out: list[str] = [
            "walkforward_overlapping_windows_double_count_overlap",
            "sequential_execution_no_parallelism",
            f"window_months={self._window_months}_step_months={self._step_months}",
        ]
        seen: set[str] = set(out)
        for report in executed:
            for caveat in report.caveats:
                if caveat not in seen:
                    out.append(caveat)
                    seen.add(caveat)
        return out

    def _empty_report(
        self,
        reason: str,
        *,
        windows: Optional[Sequence[BacktestReport]] = None,
    ) -> WalkforwardReport:
        caveats = [
            "walkforward_overlapping_windows_double_count_overlap",
            "sequential_execution_no_parallelism",
            f"window_months={self._window_months}_step_months={self._step_months}",
            f"empty_report:{reason}",
        ]
        seen: set[str] = set(caveats)
        for report in windows or ():
            for caveat in report.caveats:
                if caveat not in seen:
                    caveats.append(caveat)
                    seen.add(caveat)

        return WalkforwardReport(
            period_start=(
                str(self._period_start.date()) if self._period_start is not None else None
            ),
            period_end=(
                str(self._period_end.date()) if self._period_end is not None else None
            ),
            window_months=self._window_months,
            step_months=self._step_months,
            n_windows=0,
            rebalance_freq_days=self._rebalance_freq_days,
            initial_capital=self._initial_capital,
            policy_signal_factor_enabled=self._policy_factor_enabled,
            windows=[],
            tc_enabled=self._tc_model is not None,
            tc_model_params=(
                self._tc_model.to_dict() if self._tc_model is not None else None
            ),
            caveats=caveats,
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _to_timestamp(
    value: Optional[Union[str, datetime, pd.Timestamp]],
) -> Optional[pd.Timestamp]:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value
    return pd.Timestamp(value)


def _iter_window_bounds(
    period_start: Optional[pd.Timestamp],
    period_end: Optional[pd.Timestamp],
    *,
    window_months: int,
    step_months: int,
) -> Iterator[tuple[pd.Timestamp, pd.Timestamp]]:
    """Yield ``(window_start, window_end)`` for each rolling window.

    Both bounds use ``DateOffset(months=...)`` so calendar months are
    honoured (e.g. ``2024-01-31`` + 1 month = ``2024-02-29``). Windows
    end at ``start + window_months - 1 day`` so a 3-month window starting
    2024-01-01 ends 2024-03-31, not 2024-04-01 (no overlap of bound
    days). We keep generating windows while ``window_end <= period_end``.

    When ``period_start`` or ``period_end`` is ``None``, the iterator
    yields nothing — the walkforward needs explicit bounds to define
    "rolling". This matches the CLI/API where both are required.
    """

    if period_start is None or period_end is None:
        return
    if period_end < period_start:
        return

    window_delta = pd.DateOffset(months=window_months)
    step_delta = pd.DateOffset(months=step_months)
    one_day = pd.Timedelta(days=1)

    cursor = period_start
    while True:
        window_end = (cursor + window_delta) - one_day
        if window_end > period_end:
            return
        yield cursor, window_end
        cursor = cursor + step_delta


def _aggregate_metrics(reports: Sequence[BacktestReport]) -> dict[str, float]:
    """Reduce a non-empty list of :class:`BacktestReport` into the aggregate stats."""

    returns = [float(r.total_return_pct) for r in reports]
    sharpes = [float(r.sharpe_ratio) for r in reports]
    drawdowns = [float(r.max_drawdown_pct) for r in reports]
    buy_holds = [float(r.comparable_buy_hold_return_pct) for r in reports]

    n = len(reports)
    mean_return = sum(returns) / n
    median_return = float(statistics.median(returns))
    return_std = float(statistics.stdev(returns)) if n >= 2 else 0.0
    positive = sum(1 for r in returns if r > 0.0)
    pct_positive = positive / n
    mean_sharpe = sum(sharpes) / n
    median_sharpe = float(statistics.median(sharpes))
    mean_dd = sum(drawdowns) / n
    worst_dd = max(drawdowns) if drawdowns else 0.0
    mean_bh = sum(buy_holds) / n

    # Geometric aggregate: product of (1 + r_i / 100), minus 1, * 100.
    # NOT the literal "trade every window back to back" P&L because
    # overlapping windows double-count their shared bars. Surfaced
    # alongside the explicit caveat in the report.
    compounded = 1.0
    for r in returns:
        compounded *= 1.0 + (r / 100.0)
    aggregate_return = (compounded - 1.0) * 100.0

    consistency = _compute_consistency_score(returns, pct_positive)

    # TC summaries — arithmetic means across the executed windows so
    # callers can read "average per-window cost" without diving into
    # per-report payloads. When TC is off, every window has zeros for
    # these fields → the means are zero too.
    gross_returns = [float(r.gross_total_return_pct) for r in reports]
    net_returns = [float(r.net_total_return_pct) for r in reports]
    tc_costs = [float(r.total_tc_cost_pct) for r in reports]
    tc_drags = [float(r.tc_drag_annualized_pct) for r in reports]
    mean_gross = sum(gross_returns) / n
    mean_net = sum(net_returns) / n
    mean_cost = sum(tc_costs) / n
    mean_drag = sum(tc_drags) / n

    return {
        "aggregate_return_pct": float(aggregate_return),
        "mean_window_return_pct": float(mean_return),
        "median_window_return_pct": float(median_return),
        "return_std_pct": float(return_std),
        "pct_positive_windows": float(pct_positive),
        "mean_sharpe": float(mean_sharpe),
        "median_sharpe": float(median_sharpe),
        "mean_max_dd_pct": float(mean_dd),
        "worst_window_dd_pct": float(worst_dd),
        "mean_buy_hold_return_pct": float(mean_bh),
        "consistency_score": float(consistency),
        "mean_gross_return_pct": float(mean_gross),
        "mean_net_return_pct": float(mean_net),
        "mean_tc_cost_pct": float(mean_cost),
        "mean_tc_drag_annualized_pct": float(mean_drag),
    }


def _compute_consistency_score(
    returns: Sequence[float],
    pct_positive: float,
) -> float:
    """0-to-1 stability score from a list of per-window total returns.

    Definition::

        score = pct_positive * (1 / (1 + coefficient_of_variation))

    where ``coefficient_of_variation = std(returns) / mean(|returns|)``
    using the *absolute* mean so a near-zero mean doesn't blow the CV up
    to infinity (which would otherwise drag the score to zero even for a
    near-flat tape).

    Edge cases:

    * Single window: CV is undefined (std needs ≥2 samples) — return
      ``pct_positive`` straight (1.0 if positive, 0.0 otherwise). The
      window count alone is enough information at that point.
    * All returns exactly zero: CV undefined and ``pct_positive=0`` — by
      definition the strategy did nothing, score is 0.0.
    * Returns include ``NaN`` / ``Inf``: not expected because the
      backtester's metric path is finite-only, but defensively coerced to
      0.0 to avoid leaking non-finite into the report.

    The blend punishes both "few windows positive" (via the positive
    fraction) and "wildly variable when positive" (via CV). A strategy
    that's positive in 100% of windows with near-zero dispersion scores
    near 1.0; one that's positive in 50% with high dispersion scores
    near 0.0. Always clipped to ``[0, 1]`` for downstream consumers.
    """

    n = len(returns)
    if n == 0:
        return 0.0
    if n == 1:
        return float(pct_positive)

    finite = [float(r) for r in returns if math.isfinite(float(r))]
    if not finite or len(finite) < 2:
        return float(pct_positive)

    mean = sum(finite) / len(finite)
    std = statistics.stdev(finite)
    # Coefficient of variation guarded against zero mean. Using |mean|
    # so the sign of the average doesn't flip CV negative.
    denom = abs(mean)
    if denom < 1e-9:
        # Mean ≈ 0 → CV unbounded; if std is also ~0 it means every
        # window was flat (zero return), so return pct_positive verbatim
        # (which will be 0). Otherwise dispersion dominates → score 0.
        if std < 1e-9:
            return float(pct_positive)
        return 0.0

    cv = std / denom
    score = pct_positive * (1.0 / (1.0 + cv))
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return float(score)


__all__ = [
    "DEFAULT_STEP_MONTHS",
    "DEFAULT_WINDOW_MONTHS",
    "EtfRotationWalkforwardAnalyzer",
    "WalkforwardReport",
]
