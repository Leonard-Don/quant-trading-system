"""Multi-strategy comparison harness for the ETF rotation family.

The single-strategy backtester (``EtfRotationBacktester``, see
``src/backtest/etf_rotation_backtest.py`` at commit ``840addf``) answers
"how did *this* strategy perform on *this* window?". The walkforward
analyzer answers "how stable is one strategy across many windows?". But
the user still cannot tell *which* strategy in the existing family
(rotation / mean-reversion / blend) wins under the same conditions
without manually A/B/C-ing three separate runs.

This module closes that gap: it runs each strategy through the same
``EtfRotationBacktester`` engine over the *same* historical window, then
aggregates the per-strategy ``BacktestReport``s into a
:class:`ComparisonReport` that surfaces the winner per metric, a regime
breakdown (which strategy wins in trending vs. choppy halves), and the
pairwise return spreads (rotation vs MR, rotation vs blend, MR vs
blend) so the caller has both the headline ranking and the relative
performance fan-out.

Look-ahead semantics
--------------------
We delegate the lagging to the backtester / wrapped strategies (they
already enforce ``lag_days=1``), and we feed every strategy the *same*
price matrix and bounds. There is no cross-strategy peeking — each
strategy sees only its own configuration.

v0.1 caveats (inherited from ``EtfRotationBacktester``)
-------------------------------------------------------
* No transaction costs / bid-ask spread / slippage / market impact.
* Next-bar close fills only, no execution delay beyond the one-bar lag.
* No survivorship handling.
* Comparisons within this report are apples-to-apples (all strategies
  ate the same caveats), but absolute returns degrade once you bolt on
  TC / slippage in live trading. Don't read this report as a
  cost-adjusted live forecast.

What this report *can* answer
-----------------------------
* "Which strategy posted the highest Sharpe over the window?"
* "Did the blender beat both children, or just be the average?"
* "Does rotation dominate in trending halves but bleed in chop, where
  mean-reversion takes over?" → ``regime_analysis``.
* "How wide is the gap between best and worst?" → ``pairwise_spreads``.

What this report *cannot* answer
--------------------------------
* "Which strategy is best out-of-sample?" — pair with the walkforward
  analyzer per-strategy if you need that.
* "Which strategy wins net of execution costs?" — inherits the v0.1
  no-TC caveat. The ranking can flip once a 5–10 bps round-trip fee is
  added if one strategy turns over much more than the others.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from typing import Any, Callable, Optional, Protocol, Union

import numpy as np
import pandas as pd

from src.backtest.etf_rotation_backtest import (
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_REBALANCE_FREQ_DAYS,
    BacktestReport,
    EtfRotationBacktester,
    _sanitize_for_json,
    _summarise_tc,
)
from src.backtest.strategy_statistical_tests import (
    BlockBootstrapResult,
    DMResult,
    MultipleTestingCorrection,
    SharpeTestResult,
    bonferroni_correct,
    diebold_mariano_test,
    holm_correct,
    politis_romano_block_bootstrap,
    sharpe_ratio_test,
)
from src.backtest.transaction_costs import TransactionCostModel
from src.strategy.etf_mean_reversion_strategy import (
    EtfMeanReversionRotationConfig,
    EtfMeanReversionStrategy,
)
from src.strategy.etf_rotation_strategy import (
    EtfRotationConfig,
    EtfRotationStrategy,
    EtfSignal,
)
from src.strategy.etf_strategy_blend import (
    EtfStrategyBlend,
    EtfStrategyBlendConfig,
)

logger = logging.getLogger(__name__)


# Canonical labels — surfaced in the report keys, the CLI flags, and the
# JSON/markdown output. Keep these as snake_case so CLI flag parsing and
# JSON consumption stay uniform.
STRATEGY_LABEL_ROTATION = "rotation"
STRATEGY_LABEL_MEAN_REVERSION = "mean_reversion"
STRATEGY_LABEL_BLEND = "blend"
DEFAULT_STRATEGY_LABELS: tuple[str, ...] = (
    STRATEGY_LABEL_ROTATION,
    STRATEGY_LABEL_MEAN_REVERSION,
    STRATEGY_LABEL_BLEND,
)


# ---------------------------------------------------------------------------
# Strategy descriptor + signal-adapter wrappers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategySpec:
    """Lightweight strategy descriptor handed to :class:`StrategyComparator`.

    The comparator needs three things per strategy:

    * a stable ``label`` (becomes the report key + CLI flag value);
    * a ``config`` (``EtfRotationConfig``) so the inner
      ``EtfRotationBacktester`` knows which universe / gross_cap /
      warmup to honour. **All comparand strategies must share the same
      universe** — otherwise the comparison isn't apples-to-apples.
    * a ``signal_generator`` — a callable producing a wide-form
      target-weight DataFrame (same shape as ``EtfRotationStrategy.generate_signals``).
      Built-in wrappers are provided below so callers don't have to
      write this for the standard three strategies.
    """

    label: str
    config: EtfRotationConfig
    signal_generator: SignalGenerator
    description: str = ""


class SignalGenerator(Protocol):
    """Callable that converts a price matrix into a lagged target-weight DataFrame.

    Mirrors ``EtfRotationStrategy.generate_signals`` shape so the
    backtester can stay strategy-agnostic. ``lag_days=1`` is the
    causal-correctness default; pass ``0`` only for diagnostic peeking.
    """

    def __call__(
        self,
        price_matrix: pd.DataFrame,
        *,
        lag_days: int = 1,
        industry_signals: Optional[Mapping[str, Mapping[str, Any]]] = None,
        etf_industry_map: Optional[Mapping[str, str]] = None,
    ) -> pd.DataFrame: ...


def _signals_to_weight_row(
    signals: Iterable[EtfSignal],
    columns: pd.Index,
) -> pd.Series:
    """Project an EtfSignal iterable into a single-bar weight row aligned to ``columns``.

    Symbols not present in the signal list (or with no weight) fall
    through to ``0.0`` so the row always has the full universe layout.
    """

    row = pd.Series(0.0, index=columns, dtype=float)
    for sig in signals:
        if sig.symbol in row.index:
            row[sig.symbol] = float(sig.target_weight)
    return row


def make_rotation_signal_generator(
    config: EtfRotationConfig,
) -> SignalGenerator:
    """Return a signal generator that delegates to ``EtfRotationStrategy.generate_signals``.

    Reuses the production strategy verbatim — no second implementation
    to keep in sync. The wrapper exists purely so the comparator can
    treat rotation, MR, and blend uniformly.
    """

    strategy = EtfRotationStrategy(config)

    def _generate(
        price_matrix: pd.DataFrame,
        *,
        lag_days: int = 1,
        industry_signals: Optional[Mapping[str, Mapping[str, Any]]] = None,
        etf_industry_map: Optional[Mapping[str, str]] = None,
    ) -> pd.DataFrame:
        return strategy.generate_signals(
            price_matrix,
            lag_days=lag_days,
            industry_signals=industry_signals,
            etf_industry_map=etf_industry_map,
        )

    return _generate


def _bar_by_bar_generate_signals(
    *,
    price_matrix: pd.DataFrame,
    warmup_days: int,
    evaluator: Callable[[pd.DataFrame], list[EtfSignal]],
    lag_days: int,
) -> pd.DataFrame:
    """Walk a price matrix bar-by-bar, asking ``evaluator`` for signals each step.

    Mirrors the inner loop of ``EtfRotationStrategy.generate_signals`` so
    strategies that only expose ``evaluate(...)`` (mean reversion,
    blend) can be backtested via the same engine. ``evaluator`` receives
    a *prefix* slice (``prices.iloc[: idx + 1]``) so it sees only past +
    current data — no look-ahead.

    Causal contract: ``lag_days=1`` (the default) shifts the result by
    one bar so the weight on row ``t`` is what the strategy decided on
    row ``t-1`` — identical to the rotation strategy's own contract.
    """

    if lag_days < 0:
        raise ValueError("lag_days must be >= 0")

    weights = pd.DataFrame(0.0, index=price_matrix.index, columns=price_matrix.columns)
    for idx in range(warmup_days, len(price_matrix)):
        window = price_matrix.iloc[: idx + 1]
        signals = evaluator(window)
        for signal in signals:
            if signal.symbol in weights.columns:
                weights.iat[idx, weights.columns.get_loc(signal.symbol)] = (
                    float(signal.target_weight)
                )

    if lag_days > 0:
        weights = weights.shift(lag_days).fillna(0.0)
    else:
        weights = weights.fillna(0.0)
    return weights


def make_mean_reversion_signal_generator(
    config: EtfMeanReversionRotationConfig,
) -> SignalGenerator:
    """Wrap ``EtfMeanReversionStrategy`` into the SignalGenerator protocol.

    The MR strategy only exposes ``evaluate(latest_row)``; we re-use it
    per bar with the prefix slice so the comparator can replay it like
    the rotation strategy.
    """

    strategy = EtfMeanReversionStrategy(config)

    def _generate(
        price_matrix: pd.DataFrame,
        *,
        lag_days: int = 1,
        industry_signals: Optional[Mapping[str, Mapping[str, Any]]] = None,
        etf_industry_map: Optional[Mapping[str, str]] = None,
    ) -> pd.DataFrame:
        # MR strategy intentionally ignores industry / policy signals
        # (mean-reversion already trades against momentum; layering a
        # policy boost on it would double-count). Args accepted for
        # protocol parity, unused on purpose.
        del industry_signals, etf_industry_map
        prepared = price_matrix.apply(pd.to_numeric, errors="coerce").sort_index()
        prepared = prepared.ffill().dropna(how="all")
        return _bar_by_bar_generate_signals(
            price_matrix=prepared,
            warmup_days=config.warmup_days,
            evaluator=lambda window: strategy.evaluate(window),
            lag_days=lag_days,
        )

    return _generate


def make_blend_signal_generator(
    *,
    rotation_config: EtfRotationConfig,
    mr_config: EtfMeanReversionRotationConfig,
    blend_config: Optional[EtfStrategyBlendConfig] = None,
    regime: str = "unknown",
) -> SignalGenerator:
    """Wrap ``EtfStrategyBlend`` for the comparator.

    Builds child strategies from the supplied configs and asks the
    blender for combined signals at each bar. Picks the strictest
    warmup across children so neither child gets called before it has
    enough history.
    """

    rotation_strategy = EtfRotationStrategy(rotation_config)
    mr_strategy = EtfMeanReversionStrategy(mr_config)
    blender = EtfStrategyBlend(
        trend_strategy=rotation_strategy,
        mr_strategy=mr_strategy,
        config=blend_config or EtfStrategyBlendConfig(enabled=True),
        regime=regime,
    )
    effective_warmup = max(rotation_config.warmup_days, mr_config.warmup_days)

    def _generate(
        price_matrix: pd.DataFrame,
        *,
        lag_days: int = 1,
        industry_signals: Optional[Mapping[str, Mapping[str, Any]]] = None,
        etf_industry_map: Optional[Mapping[str, str]] = None,
    ) -> pd.DataFrame:
        prepared = price_matrix.apply(pd.to_numeric, errors="coerce").sort_index()
        prepared = prepared.ffill().dropna(how="all")
        return _bar_by_bar_generate_signals(
            price_matrix=prepared,
            warmup_days=effective_warmup,
            evaluator=lambda window: blender.evaluate(
                window,
                industry_signals=industry_signals,
                etf_industry_map=etf_industry_map,
            ),
            lag_days=lag_days,
        )

    return _generate


def derive_mean_reversion_config(
    rotation_config: EtfRotationConfig,
) -> EtfMeanReversionRotationConfig:
    """Build an MR config from a rotation config using the same universe.

    The comparator needs the two strategies to share an asset universe
    so the comparison is apples-to-apples. We reuse the rotation
    config's ``assets`` / ``gross_cap`` / ``warmup_days`` and let the
    MR scoring defaults handle the rest. Callers that want non-default
    MR scoring should construct ``EtfMeanReversionRotationConfig``
    directly and pass it via ``StrategySpec``.
    """

    return EtfMeanReversionRotationConfig(
        assets=list(rotation_config.assets),
        gross_cap=rotation_config.gross_cap,
        warmup_days=rotation_config.warmup_days,
    )


def build_default_strategy_specs(
    rotation_config: EtfRotationConfig,
    *,
    mr_config: Optional[EtfMeanReversionRotationConfig] = None,
    blend_config: Optional[EtfStrategyBlendConfig] = None,
    blend_regime: str = "unknown",
) -> dict[str, StrategySpec]:
    """Convenience: build the standard 3 specs from a rotation config.

    Returns a dict keyed by canonical label so callers can subset via
    ``{label: build_default_strategy_specs(...)[label] for label in chosen}``.
    """

    effective_mr_config = mr_config or derive_mean_reversion_config(rotation_config)
    return {
        STRATEGY_LABEL_ROTATION: StrategySpec(
            label=STRATEGY_LABEL_ROTATION,
            config=rotation_config,
            signal_generator=make_rotation_signal_generator(rotation_config),
            description="Pure trend-following rotation (EtfRotationStrategy).",
        ),
        STRATEGY_LABEL_MEAN_REVERSION: StrategySpec(
            label=STRATEGY_LABEL_MEAN_REVERSION,
            config=rotation_config,  # reuse rotation config for backtester universe / warmup
            signal_generator=make_mean_reversion_signal_generator(effective_mr_config),
            description="Buy-the-dip mean reversion gated by long-term trend (EtfMeanReversionStrategy).",
        ),
        STRATEGY_LABEL_BLEND: StrategySpec(
            label=STRATEGY_LABEL_BLEND,
            config=rotation_config,
            signal_generator=make_blend_signal_generator(
                rotation_config=rotation_config,
                mr_config=effective_mr_config,
                blend_config=blend_config,
                regime=blend_regime,
            ),
            description=(
                "Regime-aware linear blend of rotation + mean-reversion "
                f"(EtfStrategyBlend, regime={blend_regime})."
            ),
        ),
    }


# ---------------------------------------------------------------------------
# Comparator that drives the existing backtester with arbitrary strategies
# ---------------------------------------------------------------------------


class _ExternalSignalRotationBacktester(EtfRotationBacktester):
    """``EtfRotationBacktester`` variant that takes pre-generated signals.

    The base backtester always asks ``EtfRotationStrategy.generate_signals``
    internally — fine for the rotation strategy but blocks the comparator
    from feeding MR or blend signals through the same simulation engine.
    This subclass overrides only the signal-fetch step; everything else
    (warmup checks, slicing, ``_simulate``, ``_compute_metrics``,
    ``_comparable_buy_hold_return``) reuses the v0.1 implementation
    verbatim so the comparison stays metrics-identical to a direct
    single-strategy backtest.
    """

    def __init__(
        self,
        config: EtfRotationConfig,
        price_history: pd.DataFrame,
        *,
        signal_generator: SignalGenerator,
        strategy_label: str,
        period_start: Optional[Union[str, datetime, pd.Timestamp]] = None,
        period_end: Optional[Union[str, datetime, pd.Timestamp]] = None,
        industry_signals: Optional[Mapping[str, Mapping[str, Any]]] = None,
        etf_industry_map: Optional[Mapping[str, str]] = None,
        rebalance_freq_days: int = DEFAULT_REBALANCE_FREQ_DAYS,
        initial_capital: float = DEFAULT_INITIAL_CAPITAL,
        tc_model: Optional[TransactionCostModel] = None,
    ) -> None:
        # Mean-reversion / blend never honour the policy flag — only the
        # rotation strategy and blend's trend leg consume industry
        # signals. We still forward them through the generator so the
        # rotation generator can apply them; the MR generator ignores
        # them by contract.
        super().__init__(
            config=config,
            price_history=price_history,
            period_start=period_start,
            period_end=period_end,
            policy_signal_factor_enabled=bool(industry_signals),
            industry_signals=industry_signals,
            etf_industry_map=etf_industry_map,
            rebalance_freq_days=rebalance_freq_days,
            initial_capital=initial_capital,
            tc_model=tc_model,
        )
        self._signal_generator = signal_generator
        self._strategy_label = strategy_label

    def run(self) -> BacktestReport:
        prices = self._prices
        if prices.empty:
            return self._empty_report("no_price_data")
        warmup = self._config.warmup_days
        if len(prices) <= warmup:
            return self._empty_report(
                f"insufficient_history(have={len(prices)}, need>{warmup})"
            )

        target_weights = self._signal_generator(
            prices,
            lag_days=1,
            industry_signals=(
                self._industry_signals if self._policy_factor_enabled else None
            ),
            etf_industry_map=(
                self._etf_industry_map if self._policy_factor_enabled else None
            ),
        )

        # Align target_weights to the same column order as prices.
        target_weights = target_weights.reindex(columns=prices.columns).fillna(0.0)

        window_mask = pd.Series(True, index=prices.index)
        if self._period_start is not None:
            window_mask &= prices.index >= self._period_start
        if self._period_end is not None:
            window_mask &= prices.index <= self._period_end
        window_prices = prices.loc[window_mask]
        window_weights = target_weights.loc[window_mask]

        if window_prices.empty or len(window_prices) < 2:
            return self._empty_report("window_too_small_after_filtering")

        equity, rebalance_log, win_rate, avg_turnover = self._simulate(
            window_prices, window_weights,
        )
        if len(equity) < 2:
            return self._empty_report("not_enough_bars_for_returns")

        metrics = self._compute_metrics(equity, win_rate, avg_turnover)
        bh_return = self._comparable_buy_hold_return(window_prices)

        gross_equity = getattr(self, "_last_gross_equity", equity)
        tc_summary = _summarise_tc(
            rebalance_log=rebalance_log,
            n_bars=len(window_prices),
            tc_enabled=self._tc_model is not None,
            equity=equity,
            gross_equity=gross_equity,
        )

        return BacktestReport(
            period_start=str(window_prices.index[0].date()),
            period_end=str(window_prices.index[-1].date()),
            n_bars=len(window_prices),
            n_assets=window_prices.shape[1],
            n_rebalances=len(rebalance_log),
            initial_capital=self._initial_capital,
            final_equity=float(equity.iloc[-1]),
            total_return_pct=metrics["total_return_pct"],
            annualized_return_pct=metrics["annualized_return_pct"],
            sharpe_ratio=metrics["sharpe_ratio"],
            max_drawdown_pct=metrics["max_drawdown_pct"],
            calmar_ratio=metrics["calmar_ratio"],
            avg_turnover_pct=metrics["avg_turnover_pct"],
            win_rate=metrics["win_rate"],
            comparable_buy_hold_return_pct=bh_return,
            policy_signal_factor_enabled=self._policy_factor_enabled,
            rebalance_freq_days=self._rebalance_freq_days,
            tc_enabled=self._tc_model is not None,
            gross_total_return_pct=tc_summary["gross_total_return_pct"]
            if self._tc_model is not None
            else metrics["total_return_pct"],
            net_total_return_pct=metrics["total_return_pct"]
            if self._tc_model is not None
            else metrics["total_return_pct"],
            total_tc_cost_pct=tc_summary["total_tc_cost_pct"],
            avg_tc_per_rebalance_bps=tc_summary["avg_tc_per_rebalance_bps"],
            tc_drag_annualized_pct=tc_summary["tc_drag_annualized_pct"],
            tc_model_params=(
                self._tc_model.to_dict() if self._tc_model is not None else None
            ),
            rebalance_log=rebalance_log,
            caveats=[*self._build_caveats(), f"strategy_label:{self._strategy_label}"],
        )


# ---------------------------------------------------------------------------
# Report dataclass + winner / regime / pairwise analysis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WinnerSummary:
    """Which strategy wins a single metric, plus its score.

    Surfaces ``None`` for the score when the metric is undefined for
    every strategy (e.g. Calmar when every strategy posted zero
    drawdown). The label stays populated so consumers can render
    "no clear winner" without re-deriving it.
    """

    metric: str
    label: Optional[str]
    score: Optional[float]
    higher_is_better: bool = True


@dataclass(frozen=True)
class RegimeBreakdown:
    """How each strategy performed in trending vs choppy halves.

    Regime is inferred from the buy-and-hold equity curve over the
    comparison window: we split the period at the midpoint and compute
    a simple R^2 of the cumulative-return curve against a linear fit per
    half. The half with the higher R^2 is labelled ``trending``; the
    other ``choppy``. This is a deliberately *cheap* tag — the goal is
    to surface "did X strategy dominate the smooth half?" not to
    classify regimes the way a HMM would.
    """

    trending_half: str
    choppy_half: str
    trending_window: tuple[str, str]
    choppy_window: tuple[str, str]
    returns_per_half: dict[str, dict[str, float]]  # {strategy: {trending, choppy}}
    winner_trending: Optional[str]
    winner_choppy: Optional[str]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PairwiseSpread:
    """Relative performance for one ordered pair (A vs B).

    ``return_spread_pct`` = A.total_return_pct - B.total_return_pct (in
    percent, signed). ``sharpe_spread`` = A.sharpe - B.sharpe.
    """

    pair: tuple[str, str]
    return_spread_pct: float
    sharpe_spread: float
    max_dd_spread_pct: float  # A.MDD - B.MDD (lower MDD wins)


@dataclass(frozen=True)
class StatisticalTestsReport:
    """Pairwise hypothesis-test bundle for a :class:`ComparisonReport`.

    Wraps Diebold-Mariano + Politis-Romano block bootstrap + Memmel
    Sharpe-ratio test results for every unordered strategy pair (and
    optionally each strategy vs the buy-and-hold benchmark series), plus
    Bonferroni / Holm multiple-testing corrections.

    Stored on the parent :class:`ComparisonReport` under
    ``statistical_tests``; surfaces ``None`` when the caller opts out
    (the default, for backwards-compat with v0.1 reports).
    """

    pair_labels: list[str]  # one entry per unordered pair, e.g. "rotation_vs_blend"
    dm_results: list[DMResult]
    block_bootstrap_results: list[BlockBootstrapResult]
    sharpe_results: list[SharpeTestResult]
    bonferroni_dm: MultipleTestingCorrection
    bonferroni_sharpe: MultipleTestingCorrection
    holm_dm: MultipleTestingCorrection
    holm_sharpe: MultipleTestingCorrection
    alpha: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _sanitize_for_json(asdict(self))


@dataclass(frozen=True)
class ComparisonReport:
    """Aggregate over per-strategy :class:`BacktestReport`s.

    Designed to be consumed by both the markdown renderer and the
    backend endpoint:

    * ``per_strategy_metrics`` — full ``BacktestReport`` per strategy
      (label -> report). Preserves the rebalance log so callers can
      drill into turnover differences without a second backtest.
    * ``winner_by_*`` — :class:`WinnerSummary` per headline metric.
      ``None`` label when the metric was undefined for every strategy.
    * ``regime_analysis`` — :class:`RegimeBreakdown` tagging the
      trending/choppy halves and the winner in each.
    * ``pairwise_spreads`` — every ordered strategy pair's return /
      sharpe / max-dd spread, so dashboards can show "blend beat
      rotation by +1.2pp" tags without re-doing the subtraction.
    * ``caveats`` — every per-strategy caveat, deduped, plus the
      comparator-specific entry pointing back to v0.1 inheritance.

    All metrics are JSON-clean via ``to_dict`` (NaN/Inf swapped for
    ``None`` so FastAPI's default encoder accepts the payload).
    """

    period_start: Optional[str]
    period_end: Optional[str]
    n_strategies: int
    strategy_labels: list[str]
    per_strategy_metrics: dict[str, BacktestReport]
    winner_by_sharpe: WinnerSummary
    winner_by_return: WinnerSummary
    winner_by_calmar: WinnerSummary
    winner_by_max_dd: WinnerSummary  # lower drawdown wins
    winner_by_turnover: WinnerSummary  # lower turnover wins
    regime_analysis: Optional[RegimeBreakdown]
    # Transaction-cost metadata at the comparison level. Each per-strategy
    # ``BacktestReport`` carries its own TC summary; these two top-level
    # fields let callers learn "is this comparison net of TC?" without
    # walking the nested reports.
    tc_enabled: bool = False
    tc_model_params: Optional[dict[str, Any]] = None
    pairwise_spreads: list[PairwiseSpread] = field(default_factory=list)
    # Formal hypothesis tests (DM, block bootstrap, Sharpe-difference) +
    # multiple-testing corrections. ``None`` when the caller did not opt
    # in (default; preserves v0.1 report shape).
    statistical_tests: Optional[StatisticalTestsReport] = None
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return _sanitize_for_json(payload)


# ---------------------------------------------------------------------------
# Comparator
# ---------------------------------------------------------------------------


class StrategyComparator:
    """Drive the v0.1 backtester across multiple strategies on the same window.

    Usage::

        comparator = StrategyComparator(
            strategies=list(build_default_strategy_specs(config).values()),
            price_history=prices,
            period_start="2024-01-01",
            period_end="2025-04-30",
        )
        report = comparator.run()
        print(report.winner_by_sharpe.label, report.winner_by_sharpe.score)

    Determinism: identical inputs → identical reports. No RNG, no live
    data fetching, no environment knobs.
    """

    def __init__(
        self,
        strategies: Sequence[StrategySpec],
        price_history: pd.DataFrame,
        *,
        period_start: Optional[Union[str, datetime, pd.Timestamp]] = None,
        period_end: Optional[Union[str, datetime, pd.Timestamp]] = None,
        industry_signals: Optional[Mapping[str, Mapping[str, Any]]] = None,
        etf_industry_map: Optional[Mapping[str, str]] = None,
        rebalance_freq_days: int = DEFAULT_REBALANCE_FREQ_DAYS,
        initial_capital: float = DEFAULT_INITIAL_CAPITAL,
        tc_model: Optional[TransactionCostModel] = None,
        compute_statistical_tests: bool = False,
        statistical_alpha: float = 0.05,
        statistical_block_size: int = 10,
        statistical_n_bootstrap: int = 1000,
        statistical_include_buy_hold: bool = True,
    ) -> None:
        if rebalance_freq_days < 1:
            raise ValueError("rebalance_freq_days must be >= 1")
        if initial_capital <= 0:
            raise ValueError("initial_capital must be > 0")
        if not 0.0 < statistical_alpha < 1.0:
            raise ValueError("statistical_alpha must be in (0, 1)")
        # Allow an empty strategy list — produces a fully empty report
        # with a clear caveat. Easier on CLI callers that pass an empty
        # selection than raising and forcing them to special-case it.
        self._strategies = list(strategies)
        self._price_history = price_history
        self._period_start = period_start
        self._period_end = period_end
        self._industry_signals = (
            dict(industry_signals) if industry_signals else None
        )
        self._etf_industry_map = (
            dict(etf_industry_map) if etf_industry_map else None
        )
        self._rebalance_freq_days = int(rebalance_freq_days)
        self._initial_capital = float(initial_capital)
        self._tc_model = tc_model
        self._compute_statistical_tests = bool(compute_statistical_tests)
        self._statistical_alpha = float(statistical_alpha)
        self._statistical_block_size = int(statistical_block_size)
        self._statistical_n_bootstrap = int(statistical_n_bootstrap)
        self._statistical_include_buy_hold = bool(statistical_include_buy_hold)

        # Validate that labels are unique up-front so the report's dict
        # keys don't silently collide and shadow one strategy.
        labels = [spec.label for spec in self._strategies]
        if len(set(labels)) != len(labels):
            raise ValueError(
                f"StrategySpec labels must be unique; got duplicates in {labels}"
            )

    def run(self) -> ComparisonReport:
        if not self._strategies:
            return self._empty_report("no_strategies_supplied")

        per_strategy: dict[str, BacktestReport] = {}
        for spec in self._strategies:
            backtester = _ExternalSignalRotationBacktester(
                config=spec.config,
                price_history=self._price_history,
                signal_generator=spec.signal_generator,
                strategy_label=spec.label,
                period_start=self._period_start,
                period_end=self._period_end,
                industry_signals=self._industry_signals,
                etf_industry_map=self._etf_industry_map,
                rebalance_freq_days=self._rebalance_freq_days,
                initial_capital=self._initial_capital,
                tc_model=self._tc_model,
            )
            per_strategy[spec.label] = backtester.run()

        labels = [spec.label for spec in self._strategies]
        winner_sharpe = _winner_higher_better(
            "sharpe_ratio", per_strategy, lambda r: r.sharpe_ratio,
        )
        winner_return = _winner_higher_better(
            "total_return_pct", per_strategy, lambda r: r.total_return_pct,
        )
        winner_calmar = _winner_higher_better(
            "calmar_ratio", per_strategy, lambda r: r.calmar_ratio,
        )
        winner_max_dd = _winner_lower_better(
            "max_drawdown_pct", per_strategy, lambda r: r.max_drawdown_pct,
        )
        winner_turnover = _winner_lower_better(
            "avg_turnover_pct", per_strategy, lambda r: r.avg_turnover_pct,
        )

        regime = self._infer_regime(per_strategy)
        spreads = self._pairwise_spreads(per_strategy, labels)
        statistical_tests = (
            self._compute_pairwise_tests(per_strategy, labels)
            if self._compute_statistical_tests
            else None
        )

        # Period bounds: snap to the first/last *executed* window across
        # strategies so the headline matches what was actually backtested
        # (not the abstract caller bounds). Fall back to caller bounds
        # when no strategy produced a non-empty window.
        executed_starts = [
            r.period_start for r in per_strategy.values() if r.period_start
        ]
        executed_ends = [
            r.period_end for r in per_strategy.values() if r.period_end
        ]
        period_start = min(executed_starts) if executed_starts else _to_iso(
            self._period_start
        )
        period_end = max(executed_ends) if executed_ends else _to_iso(
            self._period_end
        )

        caveats = _collect_caveats(per_strategy.values())
        caveats.append(
            "comparison_window_shared_across_strategies — all strategies "
            "evaluated on the same prices / dates / rebalance cadence"
        )

        return ComparisonReport(
            period_start=period_start,
            period_end=period_end,
            n_strategies=len(per_strategy),
            strategy_labels=labels,
            per_strategy_metrics=per_strategy,
            winner_by_sharpe=winner_sharpe,
            winner_by_return=winner_return,
            winner_by_calmar=winner_calmar,
            winner_by_max_dd=winner_max_dd,
            winner_by_turnover=winner_turnover,
            regime_analysis=regime,
            tc_enabled=self._tc_model is not None,
            tc_model_params=(
                self._tc_model.to_dict() if self._tc_model is not None else None
            ),
            pairwise_spreads=spreads,
            statistical_tests=statistical_tests,
            caveats=caveats,
        )

    # ------------------------------------------------------------------
    # Regime + pairwise helpers
    # ------------------------------------------------------------------

    def _infer_regime(
        self,
        per_strategy: dict[str, BacktestReport],
    ) -> Optional[RegimeBreakdown]:
        """Split the window at midpoint, tag trending vs choppy, score per strategy.

        Cheap heuristic: compute the buy-and-hold cumulative return for
        each half, then label the half with the higher R^2 against a
        linear fit (steady move = high R^2) as ``trending``. Per
        strategy, the realised return inside each half is the equity
        curve change between the half's first and last bar (we don't
        re-build a separate backtest — the rebalance_log on each
        ``BacktestReport`` already encodes period-by-period equity).
        """

        prices = self._prepare_prices_for_regime(per_strategy)
        if prices is None or len(prices) < 4:
            return None

        midpoint = len(prices) // 2
        first_half = prices.iloc[:midpoint]
        second_half = prices.iloc[midpoint:]
        if first_half.empty or second_half.empty:
            return None

        first_r2 = _linear_fit_r2(first_half.mean(axis=1).to_numpy())
        second_r2 = _linear_fit_r2(second_half.mean(axis=1).to_numpy())

        if first_r2 >= second_r2:
            trending_half_data = first_half
            choppy_half_data = second_half
            trending_label = "first_half"
            choppy_label = "second_half"
        else:
            trending_half_data = second_half
            choppy_half_data = first_half
            trending_label = "second_half"
            choppy_label = "first_half"

        trending_window = (
            str(trending_half_data.index[0].date()),
            str(trending_half_data.index[-1].date()),
        )
        choppy_window = (
            str(choppy_half_data.index[0].date()),
            str(choppy_half_data.index[-1].date()),
        )

        returns_per_half: dict[str, dict[str, float]] = {}
        for label, report in per_strategy.items():
            returns_per_half[label] = self._half_returns_from_log(
                report=report,
                trending_window=trending_window,
                choppy_window=choppy_window,
            )

        winner_trending = _pick_winner_by_dict_field(returns_per_half, "trending")
        winner_choppy = _pick_winner_by_dict_field(returns_per_half, "choppy")

        notes = [
            f"regime split at midpoint (trending R^2={max(first_r2, second_r2):.3f}, "
            f"choppy R^2={min(first_r2, second_r2):.3f})",
            "half-returns derived from per-strategy rebalance_log equity-after series",
        ]

        return RegimeBreakdown(
            trending_half=trending_label,
            choppy_half=choppy_label,
            trending_window=trending_window,
            choppy_window=choppy_window,
            returns_per_half=returns_per_half,
            winner_trending=winner_trending,
            winner_choppy=winner_choppy,
            notes=notes,
        )

    def _prepare_prices_for_regime(
        self,
        per_strategy: dict[str, BacktestReport],
    ) -> Optional[pd.DataFrame]:
        """Slice the input price matrix to the executed comparison window."""

        if self._price_history is None or self._price_history.empty:
            return None
        prices = self._price_history.apply(pd.to_numeric, errors="coerce").sort_index()
        prices = prices.ffill().dropna(how="all")

        bounds_start: Optional[pd.Timestamp] = None
        bounds_end: Optional[pd.Timestamp] = None
        for report in per_strategy.values():
            if report.period_start:
                ts = pd.Timestamp(report.period_start)
                bounds_start = ts if bounds_start is None else min(bounds_start, ts)
            if report.period_end:
                ts = pd.Timestamp(report.period_end)
                bounds_end = ts if bounds_end is None else max(bounds_end, ts)

        if bounds_start is None or bounds_end is None:
            return None

        mask = (prices.index >= bounds_start) & (prices.index <= bounds_end)
        sliced = prices.loc[mask]
        return sliced if not sliced.empty else None

    @staticmethod
    def _half_returns_from_log(
        *,
        report: BacktestReport,
        trending_window: tuple[str, str],
        choppy_window: tuple[str, str],
    ) -> dict[str, float]:
        """Compute per-half return % for one strategy from its rebalance log.

        Falls back to splitting the full ``total_return_pct`` evenly when
        the rebalance log is too sparse to localise (e.g. empty window).
        Always returns floats so the consumer doesn't have to None-check.
        """

        log = list(report.rebalance_log or [])
        if not log:
            half = float(report.total_return_pct) / 2.0
            return {"trending": half, "choppy": half}

        entries = []
        for entry in log:
            try:
                date = pd.Timestamp(entry.get("date"))
                equity = float(entry.get("equity_after", report.initial_capital))
            except (TypeError, ValueError):
                continue
            entries.append((date, equity))

        if not entries:
            half = float(report.total_return_pct) / 2.0
            return {"trending": half, "choppy": half}

        entries.sort(key=lambda pair: pair[0])

        def _slice_return(start_iso: str, end_iso: str) -> float:
            start = pd.Timestamp(start_iso)
            end = pd.Timestamp(end_iso)
            inside = [eq for dt, eq in entries if start <= dt <= end]
            if not inside:
                return 0.0
            first = inside[0]
            last = inside[-1]
            if first <= 0:
                return 0.0
            return float((last / first - 1.0) * 100.0)

        return {
            "trending": _slice_return(*trending_window),
            "choppy": _slice_return(*choppy_window),
        }

    # ------------------------------------------------------------------
    # Formal statistical tests
    # ------------------------------------------------------------------

    def _compute_pairwise_tests(
        self,
        per_strategy: dict[str, BacktestReport],
        labels: list[str],
    ) -> Optional[StatisticalTestsReport]:
        """Run DM + block-bootstrap + Sharpe tests on every unordered pair.

        Returns ``None`` when fewer than two strategies have enough
        per-period observations to test (we need at least two pairs of
        rebalance-period returns to make any statistic non-degenerate).
        """

        returns_per_strategy: dict[str, list[float]] = {}
        for label, report in per_strategy.items():
            returns = _returns_from_rebalance_log(report)
            if len(returns) >= 3:
                returns_per_strategy[label] = returns

        # Optionally append a buy-and-hold "strategy" computed from the
        # comparison-window prices so the user can ask "is rotation
        # significantly different from passive?".
        bh_returns: Optional[list[float]] = None
        if self._statistical_include_buy_hold:
            bh_returns = self._build_buy_hold_period_returns(per_strategy)
            if bh_returns is not None and len(bh_returns) >= 3:
                returns_per_strategy["buy_hold"] = bh_returns

        labels_to_test = [
            label for label in labels if label in returns_per_strategy
        ]
        if "buy_hold" in returns_per_strategy and "buy_hold" not in labels_to_test:
            labels_to_test.append("buy_hold")

        if len(labels_to_test) < 2:
            return None

        pair_labels: list[str] = []
        dm_results: list[DMResult] = []
        bootstrap_results: list[BlockBootstrapResult] = []
        sharpe_results: list[SharpeTestResult] = []
        # Unordered pairs only — we want one entry per (A, B), no
        # duplicates with A and B swapped.
        for i, label_a in enumerate(labels_to_test):
            for label_b in labels_to_test[i + 1 :]:
                ra = returns_per_strategy[label_a]
                rb = returns_per_strategy[label_b]
                # Align lengths defensively — bar-truncate to the shorter.
                min_len = min(len(ra), len(rb))
                ra_aligned = ra[-min_len:]
                rb_aligned = rb[-min_len:]
                pair_labels.append(f"{label_a}_vs_{label_b}")
                # h = rebalance_freq_days: the Newey-West bandwidth uses
                # L = h - 1 autocovariance lags.  For daily data (freq=1)
                # L=0 is appropriate (i.i.d. variance is fine).  For
                # weekly data (freq=5) we include 4 lags, which corrects
                # for the autocorrelation present in rebalance-period
                # returns (e.g. momentum drift, mean-reversion echo).
                # Using h=1 for weekly data underestimates the HAC variance
                # and inflates the DM statistic → spuriously small p-values.
                dm_results.append(
                    diebold_mariano_test(
                        ra_aligned,
                        rb_aligned,
                        loss_fn="negative_return",
                        h=self._rebalance_freq_days,
                    )
                )
                bootstrap_results.append(
                    politis_romano_block_bootstrap(
                        ra_aligned,
                        rb_aligned,
                        block_size=self._statistical_block_size,
                        n_bootstrap=self._statistical_n_bootstrap,
                        seed=42,
                    )
                )
                sharpe_results.append(
                    sharpe_ratio_test(ra_aligned, rb_aligned, method="memmel")
                )

        if not pair_labels:
            return None

        dm_p_values = [r.p_value for r in dm_results]
        sharpe_p_values = [r.p_value for r in sharpe_results]
        bonf_dm = bonferroni_correct(
            dm_p_values, alpha=self._statistical_alpha, labels=pair_labels,
        )
        bonf_sharpe = bonferroni_correct(
            sharpe_p_values, alpha=self._statistical_alpha, labels=pair_labels,
        )
        holm_dm = holm_correct(
            dm_p_values, alpha=self._statistical_alpha, labels=pair_labels,
        )
        holm_sharpe = holm_correct(
            sharpe_p_values, alpha=self._statistical_alpha, labels=pair_labels,
        )

        notes = [
            "DM loss_fn=negative_return (H1: strategy A's expected return differs from B's)",
            "Sharpe difference via Memmel (2003) closed-form, asymptotic z-test",
            "Block bootstrap: Politis-Romano (1994) circular, "
            f"block_size={self._statistical_block_size}, "
            f"n_bootstrap={self._statistical_n_bootstrap}",
            f"Multiple-testing correction over k={len(pair_labels)} unordered pairs",
        ]
        if bh_returns is not None and "buy_hold" in returns_per_strategy:
            notes.append(
                "buy_hold synthesised from equal-weight passive return over window"
            )

        return StatisticalTestsReport(
            pair_labels=pair_labels,
            dm_results=dm_results,
            block_bootstrap_results=bootstrap_results,
            sharpe_results=sharpe_results,
            bonferroni_dm=bonf_dm,
            bonferroni_sharpe=bonf_sharpe,
            holm_dm=holm_dm,
            holm_sharpe=holm_sharpe,
            alpha=self._statistical_alpha,
            notes=notes,
        )

    def _build_buy_hold_period_returns(
        self,
        per_strategy: dict[str, BacktestReport],
    ) -> Optional[list[float]]:
        """Synthesise a buy-and-hold per-rebalance return series.

        We can't reuse the comparable_buy_hold_return_pct scalar — DM and
        the bootstrap need a *series*. Re-derive by equal-weighting the
        configured universe over the same executed window, then sampling
        at the same rebalance cadence the strategies used (so the
        comparison is apples-to-apples per-period).
        """

        prices = self._prepare_prices_for_regime(per_strategy)
        if prices is None or prices.empty or len(prices) < 2:
            return None
        equity = (prices / prices.iloc[0]).mean(axis=1)
        # Sample at the same cadence the strategies fired rebalances —
        # mirrors the bar_position % rebalance_freq_days == 0 logic in
        # ``EtfRotationBacktester._simulate``. This gives us period
        # returns directly comparable to the rebalance-log returns.
        sample_idx = list(range(0, len(equity), self._rebalance_freq_days))
        if len(sample_idx) < 2:
            return None
        sampled = equity.iloc[sample_idx].to_numpy(dtype=float)
        returns = (sampled[1:] / sampled[:-1] - 1.0).tolist()
        # Drop NaN / Inf defensively.
        return [r for r in returns if math.isfinite(r)]

    @staticmethod
    def _pairwise_spreads(
        per_strategy: dict[str, BacktestReport],
        labels: list[str],
    ) -> list[PairwiseSpread]:
        """All ordered (A, B) pairs with A != B — both directions surfaced.

        We do both directions deliberately so a UI can render
        "rotation vs blend" without inverting signs client-side.
        """

        out: list[PairwiseSpread] = []
        for a in labels:
            for b in labels:
                if a == b:
                    continue
                ra = per_strategy[a]
                rb = per_strategy[b]
                out.append(PairwiseSpread(
                    pair=(a, b),
                    return_spread_pct=float(ra.total_return_pct - rb.total_return_pct),
                    sharpe_spread=float(ra.sharpe_ratio - rb.sharpe_ratio),
                    max_dd_spread_pct=float(ra.max_drawdown_pct - rb.max_drawdown_pct),
                ))
        return out

    def _empty_report(self, reason: str) -> ComparisonReport:
        none_winner = WinnerSummary(
            metric="undefined", label=None, score=None, higher_is_better=True,
        )
        return ComparisonReport(
            period_start=_to_iso(self._period_start),
            period_end=_to_iso(self._period_end),
            n_strategies=0,
            strategy_labels=[],
            per_strategy_metrics={},
            winner_by_sharpe=replace(none_winner, metric="sharpe_ratio"),
            winner_by_return=replace(none_winner, metric="total_return_pct"),
            winner_by_calmar=replace(none_winner, metric="calmar_ratio"),
            winner_by_max_dd=replace(
                none_winner, metric="max_drawdown_pct", higher_is_better=False,
            ),
            winner_by_turnover=replace(
                none_winner, metric="avg_turnover_pct", higher_is_better=False,
            ),
            regime_analysis=None,
            tc_enabled=self._tc_model is not None,
            tc_model_params=(
                self._tc_model.to_dict() if self._tc_model is not None else None
            ),
            pairwise_spreads=[],
            statistical_tests=None,
            caveats=[f"empty_report:{reason}"],
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _to_iso(
    value: Optional[Union[str, datetime, pd.Timestamp]],
) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, pd.Timestamp):
        return str(value.date())
    return str(pd.Timestamp(value).date())


def _winner_higher_better(
    metric: str,
    per_strategy: dict[str, BacktestReport],
    extractor: Callable[[BacktestReport], Optional[float]],
) -> WinnerSummary:
    """Pick the strategy with the highest extractor(value), ignoring None / NaN."""

    best_label: Optional[str] = None
    best_score: Optional[float] = None
    for label, report in per_strategy.items():
        value = extractor(report)
        if value is None:
            continue
        try:
            fv = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(fv):
            continue
        if best_score is None or fv > best_score:
            best_score = fv
            best_label = label
    return WinnerSummary(
        metric=metric, label=best_label, score=best_score, higher_is_better=True,
    )


def _winner_lower_better(
    metric: str,
    per_strategy: dict[str, BacktestReport],
    extractor: Callable[[BacktestReport], Optional[float]],
) -> WinnerSummary:
    """Pick the strategy with the lowest extractor(value), ignoring None / NaN.

    Used for max_drawdown_pct + turnover where smaller is better.
    """

    best_label: Optional[str] = None
    best_score: Optional[float] = None
    for label, report in per_strategy.items():
        value = extractor(report)
        if value is None:
            continue
        try:
            fv = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(fv):
            continue
        if best_score is None or fv < best_score:
            best_score = fv
            best_label = label
    return WinnerSummary(
        metric=metric, label=best_label, score=best_score, higher_is_better=False,
    )


def _pick_winner_by_dict_field(
    returns_per_half: dict[str, dict[str, float]],
    field_name: str,
) -> Optional[str]:
    """Among labels mapping to dicts, return the one whose ``field_name`` is largest."""

    best: Optional[str] = None
    best_value: Optional[float] = None
    for label, payload in returns_per_half.items():
        v = payload.get(field_name)
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(fv):
            continue
        if best_value is None or fv > best_value:
            best_value = fv
            best = label
    return best


def _returns_from_rebalance_log(report: BacktestReport) -> list[float]:
    """Pull a per-rebalance return series from a :class:`BacktestReport`.

    Each rebalance log entry carries ``period_return_pct`` — the
    multiplicative return over the *prior* holding period. We strip the
    first entry (it's 0% by construction at simulation start) and convert
    percent → fraction so the result is a clean returns series suitable
    for :func:`diebold_mariano_test` and friends.
    """

    log = report.rebalance_log or []
    out: list[float] = []
    for i, entry in enumerate(log):
        if i == 0:
            # First entry is the initial allocation — period_return is 0.
            continue
        raw = entry.get("period_return_pct")
        if raw is None:
            continue
        try:
            val = float(raw) / 100.0
        except (TypeError, ValueError):
            continue
        if math.isfinite(val):
            out.append(val)
    return out


def _collect_caveats(reports: Iterable[BacktestReport]) -> list[str]:
    """Union per-strategy caveats, preserving insertion order for readability."""

    seen: dict[str, None] = {}
    for report in reports:
        for caveat in report.caveats:
            if caveat not in seen:
                seen[caveat] = None
    return list(seen)


def _linear_fit_r2(values: np.ndarray) -> float:
    """R^2 of ``values`` against a linear fit of x = 0..len-1.

    Returns 0.0 when the series is too short or has zero variance. Used
    by the regime detector as a "how clean is this trend?" tag.
    """

    if values.size < 3:
        return 0.0
    x = np.arange(values.size, dtype=float)
    y = values.astype(float, copy=False)
    var_y = float(y.var())
    if var_y < 1e-15:
        return 0.0
    # Simple least-squares slope/intercept fit.
    x_mean = x.mean()
    y_mean = y.mean()
    denom = float(((x - x_mean) ** 2).sum())
    if denom < 1e-15:
        return 0.0
    slope = float(((x - x_mean) * (y - y_mean)).sum()) / denom
    intercept = y_mean - slope * x_mean
    y_pred = slope * x + intercept
    ss_res = float(((y - y_pred) ** 2).sum())
    ss_tot = float(((y - y_mean) ** 2).sum())
    if ss_tot < 1e-15:
        return 0.0
    return float(max(0.0, min(1.0, 1.0 - ss_res / ss_tot)))


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_comparison_markdown(report: ComparisonReport) -> str:
    """Render a ``ComparisonReport`` into a human-readable markdown block.

    Used by the CLI's ``--output-md`` flag and by the sample report
    committed under ``docs/sample_strategy_comparison.md``. Kept in the
    module (rather than a separate template) so callers can render
    without pulling in jinja and so the structure tracks the dataclass
    one-for-one.
    """

    lines: list[str] = []
    lines.append("# 多策略对照回放报告")
    lines.append("")
    lines.append(
        f"窗口：`{report.period_start}` → `{report.period_end}` · "
        f"参赛策略 = {report.n_strategies}"
    )
    lines.append("")

    if report.n_strategies == 0:
        lines.append("> ⚠️ 无可比策略 —— 空报告。Caveats: " + ", ".join(report.caveats))
        return "\n".join(lines)

    lines.append("## 头条指标")
    lines.append("")
    lines.append(
        "| 策略 | 总收益 % | 年化 % | Sharpe | MaxDD % | Calmar | 平均换手 % | 命中率 | "
        "等权基准 % |"
    )
    lines.append(
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    for label in report.strategy_labels:
        r = report.per_strategy_metrics[label]
        calmar_str = f"{r.calmar_ratio:.3f}" if r.calmar_ratio is not None else "n/a"
        lines.append(
            f"| `{label}` | {r.total_return_pct:.2f} | {r.annualized_return_pct:.2f} | "
            f"{r.sharpe_ratio:.3f} | {r.max_drawdown_pct:.2f} | {calmar_str} | "
            f"{r.avg_turnover_pct:.2f} | {r.win_rate:.2%} | "
            f"{r.comparable_buy_hold_return_pct:.2f} |"
        )
    lines.append("")

    if report.tc_enabled:
        lines.append("## 交易成本拆解 (Gross vs Net)")
        lines.append("")
        lines.append(
            "| 策略 | 毛收益 % | 净收益 % | TC 总成本 % | 平均 bps/调仓 | 年化拖累 % |"
        )
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        for label in report.strategy_labels:
            r = report.per_strategy_metrics[label]
            lines.append(
                f"| `{label}` | {r.gross_total_return_pct:+.2f} | "
                f"{r.net_total_return_pct:+.2f} | {r.total_tc_cost_pct:.4f} | "
                f"{r.avg_tc_per_rebalance_bps:.2f} | "
                f"{r.tc_drag_annualized_pct:.2f} |"
            )
        lines.append("")
        params = report.tc_model_params or {}
        if params:
            lines.append(
                f"> TC 模型: commission={params.get('commission_bps')} bps "
                f"per-side · spread={params.get('bid_ask_spread_bps')} bps half · "
                f"impact={params.get('market_impact_bps_per_pct_adv')} bps/%ADV · "
                f"min_commission={params.get('min_commission_per_trade')} 元 · "
                f"min_trade={params.get('min_trade_size_rmb')} 元"
            )
            lines.append("")

    lines.append("## 单项冠军")
    lines.append("")
    winners: list[tuple[str, WinnerSummary]] = [
        ("Sharpe", report.winner_by_sharpe),
        ("总收益", report.winner_by_return),
        ("Calmar", report.winner_by_calmar),
        ("最大回撤（越小越优）", report.winner_by_max_dd),
        ("平均换手（越小越优）", report.winner_by_turnover),
    ]
    lines.append("| 指标 | 优胜策略 | 分数 |")
    lines.append("| --- | --- | ---: |")
    for label, w in winners:
        score = "n/a" if w.score is None else f"{w.score:.4f}"
        lines.append(f"| {label} | `{w.label or 'n/a'}` | {score} |")
    lines.append("")

    if report.regime_analysis is not None:
        regime = report.regime_analysis
        lines.append("## 区间体制（trending / choppy）")
        lines.append("")
        lines.append(
            f"- Trending half (`{regime.trending_half}`): "
            f"{regime.trending_window[0]} → {regime.trending_window[1]}"
        )
        lines.append(
            f"- Choppy half (`{regime.choppy_half}`): "
            f"{regime.choppy_window[0]} → {regime.choppy_window[1]}"
        )
        lines.append("")
        lines.append("| 策略 | 趋势段收益 % | 震荡段收益 % |")
        lines.append("| --- | ---: | ---: |")
        for label in report.strategy_labels:
            payload = regime.returns_per_half.get(label, {})
            lines.append(
                f"| `{label}` | "
                f"{payload.get('trending', 0.0):.2f} | "
                f"{payload.get('choppy', 0.0):.2f} |"
            )
        lines.append("")
        lines.append(
            f"- 趋势段优胜: `{regime.winner_trending or 'n/a'}`  ·  "
            f"震荡段优胜: `{regime.winner_choppy or 'n/a'}`"
        )
        lines.append("")
        for note in regime.notes:
            lines.append(f"> {note}")
        lines.append("")

    if report.pairwise_spreads:
        lines.append("## 相对表现（A vs B = A 减 B）")
        lines.append("")
        lines.append("| 对比 | 收益差 pp | Sharpe 差 | MaxDD 差 pp |")
        lines.append("| --- | ---: | ---: | ---: |")
        for spread in report.pairwise_spreads:
            a, b = spread.pair
            lines.append(
                f"| `{a}` vs `{b}` | {spread.return_spread_pct:+.2f} | "
                f"{spread.sharpe_spread:+.3f} | {spread.max_dd_spread_pct:+.2f} |"
            )
        lines.append("")

    if report.statistical_tests is not None:
        lines.extend(_render_statistical_tests_markdown(report.statistical_tests))

    lines.append("## Caveats")
    lines.append("")
    for caveat in report.caveats:
        lines.append(f"- {caveat}")
    lines.append("")

    return "\n".join(lines)


def _render_statistical_tests_markdown(tests: StatisticalTestsReport) -> list[str]:
    """Render the formal statistical-tests block as a list of markdown lines.

    Surfaces three tables — DM, Sharpe-difference, block-bootstrap CI —
    one row per pair, plus a final "which p-values survive multiple-
    testing correction?" summary.
    """

    lines: list[str] = []
    lines.append("## 统计显著性检验 (Statistical hypothesis tests)")
    lines.append("")
    lines.append(
        f"配对数 k = {len(tests.pair_labels)} · 显著性水平 α = {tests.alpha:.3f}"
    )
    lines.append("")

    lines.append("### Diebold-Mariano (1995) test (loss = -return)")
    lines.append("")
    lines.append(
        "| 配对 | DM stat | p (2-sided) | p (1-sided, A>B) | mean(L_a - L_b) | n |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for pair, dm in zip(tests.pair_labels, tests.dm_results):
        lines.append(
            f"| `{pair}` | {dm.dm_statistic:+.3f} | {dm.p_value:.4f} | "
            f"{dm.p_value_one_sided:.4f} | {dm.mean_loss_differential:+.6f} | "
            f"{dm.n_obs} |"
        )
    lines.append("")

    lines.append("### Sharpe-ratio difference (Memmel 2003)")
    lines.append("")
    lines.append(
        "| 配对 | Sharpe_a | Sharpe_b | z | p (2-sided) | n |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for pair, sh in zip(tests.pair_labels, tests.sharpe_results):
        lines.append(
            f"| `{pair}` | {sh.sharpe_a:+.4f} | {sh.sharpe_b:+.4f} | "
            f"{sh.z_statistic:+.3f} | {sh.p_value:.4f} | {sh.n_obs} |"
        )
    lines.append("")

    lines.append("### Block bootstrap 95% CI on return differential")
    lines.append("")
    lines.append(
        "| 配对 | mean(A-B) | CI low | CI high | p (2-sided) | block | n_boot |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for pair, bs in zip(tests.pair_labels, tests.block_bootstrap_results):
        lines.append(
            f"| `{pair}` | {bs.mean_diff:+.6f} | {bs.ci_low:+.6f} | "
            f"{bs.ci_high:+.6f} | {bs.p_value_two_sided:.4f} | "
            f"{bs.block_size} | {bs.n_bootstrap} |"
        )
    lines.append("")

    lines.append("### Multiple-testing correction (Bonferroni & Holm)")
    lines.append("")
    lines.append(
        f"Bonferroni threshold α/k = {tests.alpha / max(len(tests.pair_labels), 1):.5f}"
    )
    lines.append("")
    lines.append(
        "| 配对 | DM raw p | DM survives Bonferroni? | DM survives Holm? | "
        "Sharpe raw p | Sharpe survives Bonferroni? | Sharpe survives Holm? |"
    )
    lines.append("| --- | ---: | :-: | :-: | ---: | :-: | :-: |")
    for i, pair in enumerate(tests.pair_labels):
        dm_p = tests.dm_results[i].p_value
        sh_p = tests.sharpe_results[i].p_value
        dm_bonf = "yes" if tests.bonferroni_dm.rejected[i] else "no"
        dm_holm = "yes" if tests.holm_dm.rejected[i] else "no"
        sh_bonf = "yes" if tests.bonferroni_sharpe.rejected[i] else "no"
        sh_holm = "yes" if tests.holm_sharpe.rejected[i] else "no"
        lines.append(
            f"| `{pair}` | {dm_p:.4f} | {dm_bonf} | {dm_holm} | "
            f"{sh_p:.4f} | {sh_bonf} | {sh_holm} |"
        )
    lines.append("")
    for note in tests.notes:
        lines.append(f"> {note}")
    lines.append("")
    return lines


__all__ = [
    "DEFAULT_STRATEGY_LABELS",
    "STRATEGY_LABEL_BLEND",
    "STRATEGY_LABEL_MEAN_REVERSION",
    "STRATEGY_LABEL_ROTATION",
    "ComparisonReport",
    "PairwiseSpread",
    "RegimeBreakdown",
    "SignalGenerator",
    "StatisticalTestsReport",
    "StrategyComparator",
    "StrategySpec",
    "WinnerSummary",
    "build_default_strategy_specs",
    "derive_mean_reversion_config",
    "make_blend_signal_generator",
    "make_mean_reversion_signal_generator",
    "make_rotation_signal_generator",
    "render_comparison_markdown",
]
