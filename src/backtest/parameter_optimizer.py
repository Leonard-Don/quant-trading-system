"""Grid-search + sensitivity-analysis parameter optimizer for ETF strategies.

This module extends the one-off ``scripts/strategy_param_scan.py`` harness
into a proper optimization tool: given a strategy class (rotation / mean
reversion / blend), a parameter grid (dict of ``param_name -> list of
candidate values``), and a historical price matrix, it exhaustively runs
the existing :class:`EtfRotationBacktester` engine for every cell of the
cartesian product and returns a structured :class:`OptimizationReport`
that surfaces:

* per-config performance metrics (Sharpe / total return / MaxDD / Calmar /
  turnover);
* the optimum config per headline metric;
* per-parameter Sharpe variance (sensitivity — which knobs actually move
  the needle);
* bootstrap confidence intervals on Sharpe for the top-N configs (so the
  caller can ask "is the optimum statistically distinguishable from the
  runner-up?" rather than chasing a noisy peak);
* an overfitting caveat when the grid size is large relative to the
  number of evaluation periods.

Why a new module
----------------
The legacy ``strategy_param_scan.py`` only sweeps two dimensions
(min_score_to_hold + rebalance_delta) and prints a flat table. It can't
answer questions like:

* Which **single** parameter matters most? (Sensitivity ranking.)
* Are the top configs distinguishable from each other, or is the
  apparent ordering noise? (Bootstrap CI.)
* Does the optimum survive a walk-forward re-test, or only fit the in-sample
  window? (Walkforward integration, opt-in.)
* If I asked for 100k configs by accident, will the harness explode?
  (Cap at ``MAX_GRID_SIZE`` configs and refuse politely.)

This module does all of the above while reusing the production
:class:`EtfRotationBacktester` so the metrics are identical to a direct
backtest invocation.

What this module does NOT do
----------------------------
* No live data fetching. Caller supplies the price matrix.
* No new metrics — Sharpe / MaxDD / Calmar / turnover come from the
  existing :class:`BacktestReport`, no second implementation to keep in
  sync.
* No automatic config selection. The caller picks a metric to optimize;
  the report surfaces multiple winners so the user can break the tie.
* No multi-objective optimization. v0.1 reports per-metric optima
  independently; Pareto-frontier analysis is left to the caller.
* No regularization / shrinkage / cross-validation beyond the optional
  walkforward pass. Treat the report as "here are the best in-sample
  configs and how stable they look", not as a production deploy gate.
"""

from __future__ import annotations

import itertools
import logging
import math
import random
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from typing import Any, Callable, Optional, Union

import pandas as pd

from src.backtest.etf_rotation_backtest import (
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_REBALANCE_FREQ_DAYS,
    BacktestReport,
    EtfRotationBacktester,
    _sanitize_for_json,
)
from src.backtest.etf_rotation_walkforward import (
    DEFAULT_STEP_MONTHS,
    DEFAULT_WINDOW_MONTHS,
    EtfRotationWalkforwardAnalyzer,
    WalkforwardReport,
)
from src.backtest.transaction_costs import TransactionCostModel
from src.strategy.etf_rotation_strategy import EtfRotationConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sanity caps and constants
# ---------------------------------------------------------------------------

#: Hard upper bound on the cartesian-product grid size. The optimizer
#: refuses to run beyond this so a typo in the grid spec doesn't kick off
#: a multi-hour job. Tuned for the synchronous backend endpoint — 200
#: configs × ~1s per backtest ≈ ~3 minutes worst case.
MAX_GRID_SIZE = 200

#: Default metric the optimizer ranks configs by. Caller can override via
#: the ``optimize_for`` argument; the report still carries per-metric
#: optima regardless.
DEFAULT_OPTIMIZE_METRIC = "sharpe_ratio"

#: Bootstrap iterations for the confidence-interval estimate. 200 is the
#: small-N sweet spot — enough to get a stable 95% CI on Sharpe samples,
#: cheap enough that even top-N=20 configs finish in <100ms total CI work.
DEFAULT_BOOTSTRAP_ITERATIONS = 200

#: Quantile bounds for the bootstrap CI. 2.5% / 97.5% gives a symmetric
#: 95% interval — match what most papers cite.
DEFAULT_BOOTSTRAP_CI_LOW = 0.025
DEFAULT_BOOTSTRAP_CI_HIGH = 0.975

#: Heuristic threshold above which the report flags an overfitting risk.
#: When ``n_configs / n_periods > _OVERFIT_CONFIG_PER_PERIOD`` we add a
#: caveat — there's no exact number that's "safe", but >0.5 means you
#: have at least one config to fit per two evaluation periods which is
#: how researchers earn the "I-fit-noise" badge.
_OVERFIT_CONFIG_PER_PERIOD = 0.5

#: Supported metric names. The optimizer asks the report directly so any
#: numeric field is fair game, but we whitelist the headline ones because
#: the "winner" calculation has to know whether higher or lower is better.
METRICS_HIGHER_IS_BETTER: frozenset[str] = frozenset(
    {
        "sharpe_ratio",
        "total_return_pct",
        "annualized_return_pct",
        "calmar_ratio",
        "win_rate",
    }
)
METRICS_LOWER_IS_BETTER: frozenset[str] = frozenset(
    {
        "max_drawdown_pct",
        "avg_turnover_pct",
    }
)
SUPPORTED_METRICS: frozenset[str] = (
    METRICS_HIGHER_IS_BETTER | METRICS_LOWER_IS_BETTER
)


# ---------------------------------------------------------------------------
# Report dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigResult:
    """Per-configuration backtest result row.

    A flat row keyed by the parameter overrides applied; carries every
    metric the report needs so downstream consumers don't have to
    re-slice the full :class:`BacktestReport`. ``report`` is the full
    underlying report — kept by reference so the caller can drill into
    the rebalance log or caveats without the optimizer flattening them.
    """

    config_id: int
    parameters: dict[str, Any]
    sharpe_ratio: float
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    calmar_ratio: Optional[float]
    avg_turnover_pct: float
    win_rate: float
    n_bars: int
    n_rebalances: int
    report: BacktestReport

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe dict. ``report`` is rendered via its own ``to_dict``."""

        payload: dict[str, Any] = {
            "config_id": self.config_id,
            "parameters": dict(self.parameters),
            "sharpe_ratio": self.sharpe_ratio,
            "total_return_pct": self.total_return_pct,
            "annualized_return_pct": self.annualized_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "calmar_ratio": self.calmar_ratio,
            "avg_turnover_pct": self.avg_turnover_pct,
            "win_rate": self.win_rate,
            "n_bars": self.n_bars,
            "n_rebalances": self.n_rebalances,
            "report": self.report.to_dict() if self.report is not None else None,
        }
        return _sanitize_for_json(payload)


@dataclass(frozen=True)
class WinnerByMetric:
    """Best-of-N winner for one metric.

    ``score`` is ``None`` when the metric is undefined for every config
    (e.g. Calmar when no config posted any drawdown). The label stays
    populated so consumers can render "no clear winner" without crashing
    on a missing key.
    """

    metric: str
    config_id: Optional[int]
    parameters: Optional[dict[str, Any]]
    score: Optional[float]


@dataclass(frozen=True)
class ParameterSensitivity:
    """Per-parameter sensitivity reading on Sharpe.

    Computed as the standard deviation of the per-parameter mean Sharpe
    when the parameter is grouped by its value. High std → toggling
    this parameter materially moves Sharpe; low std → the parameter is a
    no-op or its effect is dominated by other knobs.

    Fields
    ------
    * ``parameter`` — name of the parameter swept.
    * ``values`` — every value the parameter took in the grid.
    * ``mean_sharpe_per_value`` — mapping ``value -> mean Sharpe across
      all configs that pinned this parameter to value``.
    * ``sharpe_std`` — population standard deviation of the mean-Sharpe
      list above. Single sensitivity number you can rank parameters by.
    * ``sharpe_range`` — max - min of the mean-Sharpe list. Easier to
      interpret than std for human readers ("toggling this parameter
      moves Sharpe by at most X").
    """

    parameter: str
    values: list[Any]
    mean_sharpe_per_value: dict[str, float]
    sharpe_std: float
    sharpe_range: float


@dataclass(frozen=True)
class ConfidenceInterval:
    """Bootstrap CI on Sharpe for one config.

    Computed by resampling the per-bar daily returns of the executed
    backtest with replacement and re-computing Sharpe ``n_iterations``
    times. The empirical 2.5% / 97.5% quantiles form a 95% CI.

    Caveats:

    * Bootstrap CIs on Sharpe are notoriously wide for sample sizes < 3
      months — interpret the interval as a sanity check, not a proof.
    * The resampling is i.i.d. by bar; correlation between bars is
      treated as zero. For ETF rotation that's a pessimistic assumption
      (real returns are mildly autocorrelated → realised CI even wider).
    """

    config_id: int
    parameters: dict[str, Any]
    point_estimate_sharpe: float
    ci_low: float
    ci_high: float
    n_iterations: int


@dataclass(frozen=True)
class OptimizationReport:
    """Top-level report returned by :meth:`ParameterOptimizer.run`.

    Structure
    ---------
    * ``configurations`` — every config the optimizer evaluated, in grid
      order. ``per_config_metrics`` is the same list but keyed by
      config_id for quick lookup.
    * ``optimal_by_metric`` — best config per supported metric. Use the
      ``metric`` field to know which metric the entry refers to.
    * ``top_n_by_metric`` — top-N configs by the user's chosen metric
      (``DEFAULT_OPTIMIZE_METRIC`` unless overridden), ordered from best
      to worst. Used for the bootstrap CI step and for the report header.
    * ``parameter_sensitivity`` — per-parameter Sharpe variance ranking.
    * ``confidence_intervals`` — bootstrap 95% CI on Sharpe for the
      top-N configs. Empty when ``n_configs == 0`` or when no config
      produced enough bars to bootstrap.
    * ``walkforward_results`` — optional per-config walkforward
      :class:`WalkforwardReport`. Empty unless the caller passed
      ``with_walkforward=True`` to :meth:`ParameterOptimizer.run`.
    * ``caveats`` — text annotations (overfitting risk, grid truncation,
      etc).

    Everything is JSON-serialisable via :meth:`to_dict` so the backend
    endpoint can hand it back to the frontend unchanged.
    """

    optimize_metric: str
    period_start: Optional[str]
    period_end: Optional[str]
    n_configs_requested: int
    n_configs_evaluated: int
    parameter_grid: dict[str, list[Any]]
    configurations: list[ConfigResult]
    per_config_metrics: dict[int, ConfigResult]
    optimal_by_metric: dict[str, WinnerByMetric]
    top_n_by_metric: list[ConfigResult]
    parameter_sensitivity: list[ParameterSensitivity]
    confidence_intervals: list[ConfidenceInterval]
    walkforward_results: dict[int, WalkforwardReport] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a fully JSON-serialisable dict mirroring the dataclass."""

        payload: dict[str, Any] = {
            "optimize_metric": self.optimize_metric,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "n_configs_requested": self.n_configs_requested,
            "n_configs_evaluated": self.n_configs_evaluated,
            "parameter_grid": {
                k: list(v) for k, v in self.parameter_grid.items()
            },
            "configurations": [c.to_dict() for c in self.configurations],
            "per_config_metrics": {
                str(k): v.to_dict() for k, v in self.per_config_metrics.items()
            },
            "optimal_by_metric": {
                k: asdict(v) for k, v in self.optimal_by_metric.items()
            },
            "top_n_by_metric": [c.to_dict() for c in self.top_n_by_metric],
            "parameter_sensitivity": [
                asdict(p) for p in self.parameter_sensitivity
            ],
            "confidence_intervals": [
                asdict(ci) for ci in self.confidence_intervals
            ],
            "walkforward_results": {
                str(k): v.to_dict() for k, v in self.walkforward_results.items()
            },
            "caveats": list(self.caveats),
        }
        return _sanitize_for_json(payload)


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------


class ParameterOptimizer:
    """Grid-search optimizer over arbitrary :class:`EtfRotationConfig` knobs.

    Usage::

        optimizer = ParameterOptimizer(
            base_config=build_strategy_config(...),
            price_history=prices,
            parameter_grid={
                "gross_cap": [0.6, 0.8, 0.9, 1.0],
                "min_score_to_hold": [15, 20, 25, 30, 35],
            },
            period_start="2024-01-01",
            period_end="2025-04-30",
        )
        report = optimizer.run()
        print(report.optimal_by_metric["sharpe_ratio"].parameters)

    Determinism: identical inputs → identical reports. The bootstrap CI
    uses a deterministic seed so a re-run produces byte-identical
    intervals.

    Parameter override semantics
    ----------------------------
    Each grid key must be a field on :class:`EtfRotationConfig`. The
    optimizer uses ``dataclasses.replace`` to spawn a fresh config per
    cell; nested fields (e.g. ``scoring.trend_above_ma20_points``) can
    be addressed via dotted names — the optimizer walks the dotted path
    and recursively replaces the nested dataclass. Unknown keys raise
    ``ValueError`` at construction time so typos surface immediately.
    """

    def __init__(
        self,
        base_config: EtfRotationConfig,
        price_history: pd.DataFrame,
        parameter_grid: Mapping[str, Sequence[Any]],
        *,
        period_start: Optional[Union[str, datetime, pd.Timestamp]] = None,
        period_end: Optional[Union[str, datetime, pd.Timestamp]] = None,
        policy_signal_factor_enabled: bool = False,
        industry_signals: Optional[Mapping[str, Mapping[str, Any]]] = None,
        etf_industry_map: Optional[Mapping[str, str]] = None,
        rebalance_freq_days: int = DEFAULT_REBALANCE_FREQ_DAYS,
        initial_capital: float = DEFAULT_INITIAL_CAPITAL,
        tc_model: Optional[TransactionCostModel] = None,
        optimize_for: str = DEFAULT_OPTIMIZE_METRIC,
        top_n: int = 10,
        backtester_factory: Optional[
            Callable[..., EtfRotationBacktester]
        ] = None,
        max_grid_size: int = MAX_GRID_SIZE,
        random_seed: int = 0xC0FFEE,
        bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    ) -> None:
        if not isinstance(parameter_grid, Mapping):
            raise ValueError("parameter_grid must be a Mapping[str, Sequence]")
        if rebalance_freq_days < 1:
            raise ValueError("rebalance_freq_days must be >= 1")
        if initial_capital <= 0:
            raise ValueError("initial_capital must be > 0")
        if top_n < 1:
            raise ValueError("top_n must be >= 1")
        if max_grid_size < 1:
            raise ValueError("max_grid_size must be >= 1")
        if bootstrap_iterations < 0:
            raise ValueError("bootstrap_iterations must be >= 0")
        if optimize_for not in SUPPORTED_METRICS:
            raise ValueError(
                f"optimize_for={optimize_for!r} not in supported metrics "
                f"{sorted(SUPPORTED_METRICS)}"
            )

        # Validate every grid key resolves to an EtfRotationConfig field
        # (recursing into nested dataclasses for dotted names) before we
        # touch the backtester so a typo doesn't get caught halfway through
        # the run.
        normalised_grid: dict[str, list[Any]] = {}
        for key, values in parameter_grid.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"parameter_grid keys must be non-empty strings; got {key!r}")
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                raise ValueError(
                    f"parameter_grid[{key!r}] must be a sequence of candidate "
                    f"values; got {type(values).__name__}"
                )
            value_list = list(values)
            if not value_list:
                raise ValueError(
                    f"parameter_grid[{key!r}] must have at least one candidate value"
                )
            _validate_dotted_field(base_config, key)
            normalised_grid[key] = value_list

        # Cartesian product size: refuse upfront if too large.
        if normalised_grid:
            grid_size = 1
            for values in normalised_grid.values():
                grid_size *= len(values)
        else:
            grid_size = 0
        if grid_size > max_grid_size:
            raise ValueError(
                f"parameter_grid cartesian product is {grid_size} configs, "
                f"exceeds max_grid_size={max_grid_size}. Shrink the grid "
                "or raise the cap explicitly."
            )

        self._base_config = base_config
        self._price_history = price_history
        self._parameter_grid = normalised_grid
        self._grid_size = grid_size
        self._period_start = period_start
        self._period_end = period_end
        self._policy_factor_enabled = bool(policy_signal_factor_enabled)
        self._industry_signals = (
            dict(industry_signals) if industry_signals else None
        )
        self._etf_industry_map = (
            dict(etf_industry_map) if etf_industry_map else None
        )
        self._rebalance_freq_days = int(rebalance_freq_days)
        self._initial_capital = float(initial_capital)
        self._tc_model = tc_model
        self._optimize_for = optimize_for
        self._top_n = int(top_n)
        self._max_grid_size = int(max_grid_size)
        self._random_seed = int(random_seed)
        self._bootstrap_iterations = int(bootstrap_iterations)
        # Allow tests / advanced callers to plug in a stub backtester so
        # the engine itself can be exercised without spinning up the real
        # one. Defaults to the production class.
        self._backtester_factory = backtester_factory or EtfRotationBacktester

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        with_walkforward: bool = False,
        walkforward_window_months: int = DEFAULT_WINDOW_MONTHS,
        walkforward_step_months: int = DEFAULT_STEP_MONTHS,
    ) -> OptimizationReport:
        """Execute the grid search and return the assembled report.

        Arguments
        ---------
        * ``with_walkforward`` — when True, also run
          :class:`EtfRotationWalkforwardAnalyzer` for each of the top-N
          configs. Useful as a stability check: a config that wins on a
          single window but blows up across walkforward windows is a
          fragile fit, not a robust optimum.
        * ``walkforward_window_months`` / ``walkforward_step_months`` —
          forwarded to the walkforward analyzer when enabled.
        """

        if self._grid_size == 0:
            return self._empty_report("empty_parameter_grid")

        # Sort grid keys lexicographically so the cartesian product is
        # deterministic regardless of dict insertion order. Tests rely on
        # the ordering being stable across Python versions.
        sorted_keys = sorted(self._parameter_grid.keys())
        value_lists = [self._parameter_grid[k] for k in sorted_keys]

        configurations: list[ConfigResult] = []
        for cid, combo in enumerate(itertools.product(*value_lists)):
            params = dict(zip(sorted_keys, combo))
            cfg = _apply_overrides(self._base_config, params)
            backtester = self._backtester_factory(
                config=cfg,
                price_history=self._price_history,
                period_start=self._period_start,
                period_end=self._period_end,
                policy_signal_factor_enabled=self._policy_factor_enabled,
                industry_signals=self._industry_signals,
                etf_industry_map=self._etf_industry_map,
                rebalance_freq_days=self._rebalance_freq_days,
                initial_capital=self._initial_capital,
                tc_model=self._tc_model,
            )
            report = backtester.run()
            configurations.append(
                ConfigResult(
                    config_id=cid,
                    parameters=params,
                    sharpe_ratio=float(report.sharpe_ratio),
                    total_return_pct=float(report.total_return_pct),
                    annualized_return_pct=float(report.annualized_return_pct),
                    max_drawdown_pct=float(report.max_drawdown_pct),
                    calmar_ratio=report.calmar_ratio,
                    avg_turnover_pct=float(report.avg_turnover_pct),
                    win_rate=float(report.win_rate),
                    n_bars=int(report.n_bars),
                    n_rebalances=int(report.n_rebalances),
                    report=report,
                )
            )

        per_config_metrics = {c.config_id: c for c in configurations}
        optimal_by_metric = _winners_per_metric(configurations)
        top_n_by_metric = _top_n_by_metric(
            configurations, metric=self._optimize_for, n=self._top_n,
        )
        sensitivity = _compute_sensitivity(configurations, sorted_keys)
        cis = _bootstrap_top_n_cis(
            top_n_by_metric,
            n_iterations=self._bootstrap_iterations,
            seed=self._random_seed,
        )
        caveats = self._build_caveats(configurations)

        walkforward_results: dict[int, WalkforwardReport] = {}
        if with_walkforward and top_n_by_metric:
            for cr in top_n_by_metric:
                cfg = _apply_overrides(self._base_config, cr.parameters)
                analyzer = EtfRotationWalkforwardAnalyzer(
                    config=cfg,
                    price_history=self._price_history,
                    window_months=walkforward_window_months,
                    step_months=walkforward_step_months,
                    period_start=self._period_start,
                    period_end=self._period_end,
                    policy_signal_factor_enabled=self._policy_factor_enabled,
                    industry_signals=self._industry_signals,
                    etf_industry_map=self._etf_industry_map,
                    rebalance_freq_days=self._rebalance_freq_days,
                    initial_capital=self._initial_capital,
                    tc_model=self._tc_model,
                )
                walkforward_results[cr.config_id] = analyzer.run()
            caveats.append(
                f"walkforward_stability_check_applied_to_top_{len(top_n_by_metric)}_configs"
            )

        executed_period_start: Optional[str] = None
        executed_period_end: Optional[str] = None
        for cr in configurations:
            if cr.report.period_start is not None:
                executed_period_start = cr.report.period_start
                executed_period_end = cr.report.period_end
                break

        return OptimizationReport(
            optimize_metric=self._optimize_for,
            period_start=executed_period_start
            or _to_iso(self._period_start),
            period_end=executed_period_end or _to_iso(self._period_end),
            n_configs_requested=self._grid_size,
            n_configs_evaluated=len(configurations),
            parameter_grid={k: list(v) for k, v in self._parameter_grid.items()},
            configurations=configurations,
            per_config_metrics=per_config_metrics,
            optimal_by_metric=optimal_by_metric,
            top_n_by_metric=top_n_by_metric,
            parameter_sensitivity=sensitivity,
            confidence_intervals=cis,
            walkforward_results=walkforward_results,
            caveats=caveats,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_caveats(
        self,
        configurations: Sequence[ConfigResult],
    ) -> list[str]:
        out: list[str] = []

        # Overfitting heuristic: configs/period ratio.
        n_configs = len(configurations)
        # Approximate "n_periods" as the median rebalance count across
        # executed configs — a single window with 13 rebalances should
        # tolerate ~6 configs before we flag overfitting (heuristic).
        rebalance_counts = [
            c.n_rebalances for c in configurations if c.n_rebalances > 0
        ]
        if rebalance_counts:
            median_rebals = float(statistics.median(rebalance_counts))
            if median_rebals > 0:
                ratio = n_configs / median_rebals
                if ratio > _OVERFIT_CONFIG_PER_PERIOD:
                    out.append(
                        f"overfitting_risk(n_configs={n_configs}, "
                        f"median_rebalances={median_rebals:.0f}, "
                        f"ratio={ratio:.2f}>"
                        f"{_OVERFIT_CONFIG_PER_PERIOD}); consider "
                        "walkforward validation before trusting any "
                        "config beyond the in-sample window."
                    )

        # Always remind the user that single-window optimization is fragile.
        out.append("single_window_optimization_is_in_sample_by_construction")
        out.append(
            "bootstrap_ci_assumes_iid_returns_and_understates_real_uncertainty"
        )
        if self._tc_model is None:
            out.append("no_transaction_costs_modeled_for_any_config")
        return out

    def _empty_report(self, reason: str) -> OptimizationReport:
        return OptimizationReport(
            optimize_metric=self._optimize_for,
            period_start=_to_iso(self._period_start),
            period_end=_to_iso(self._period_end),
            n_configs_requested=0,
            n_configs_evaluated=0,
            parameter_grid={k: list(v) for k, v in self._parameter_grid.items()},
            configurations=[],
            per_config_metrics={},
            optimal_by_metric={},
            top_n_by_metric=[],
            parameter_sensitivity=[],
            confidence_intervals=[],
            walkforward_results={},
            caveats=[f"empty_report:{reason}"],
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _validate_dotted_field(config: EtfRotationConfig, dotted: str) -> None:
    """Raise ValueError when ``dotted`` doesn't resolve to a config field.

    Walks the dotted path through the config dataclass tree; the final
    component must be an actual field on the parent dataclass.
    """

    parts = dotted.split(".")
    current: Any = config
    for i, part in enumerate(parts):
        field_names = getattr(current, "__dataclass_fields__", None)
        if field_names is None or part not in field_names:
            raise ValueError(
                f"parameter_grid key {dotted!r} segment {part!r} (index {i}) "
                f"is not a dataclass field on "
                f"{type(current).__name__}"
            )
        if i < len(parts) - 1:
            current = getattr(current, part)


def _apply_overrides(
    config: EtfRotationConfig,
    overrides: Mapping[str, Any],
) -> EtfRotationConfig:
    """Return a new config with the override dict applied via replace().

    Top-level keys map directly to :class:`EtfRotationConfig` fields. Dotted
    keys (``scoring.trend_above_ma20_points``) recurse into the nested
    dataclass and rebuild it from the inside out so the outer config stays
    frozen-friendly.
    """

    if not overrides:
        return config

    # Group overrides by their top-level field so we can apply nested
    # overrides in a single replace() call per nested dataclass.
    top_level: dict[str, Any] = {}
    nested: dict[str, dict[str, Any]] = {}
    for dotted, value in overrides.items():
        if "." in dotted:
            top, sub = dotted.split(".", 1)
            nested.setdefault(top, {})[sub] = value
        else:
            top_level[dotted] = value

    new_field_values: dict[str, Any] = dict(top_level)
    for top_field, sub_overrides in nested.items():
        existing = getattr(config, top_field)
        new_field_values[top_field] = _apply_overrides_dataclass(
            existing, sub_overrides,
        )

    return replace(config, **new_field_values)


def _apply_overrides_dataclass(obj: Any, overrides: Mapping[str, Any]) -> Any:
    """Apply dotted overrides to a (possibly nested) dataclass instance.

    Mirrors :func:`_apply_overrides` for the recursive case. Frozen
    dataclasses are fine — we use ``replace`` which creates a new instance.
    """

    top_level: dict[str, Any] = {}
    nested: dict[str, dict[str, Any]] = {}
    for dotted, value in overrides.items():
        if "." in dotted:
            top, sub = dotted.split(".", 1)
            nested.setdefault(top, {})[sub] = value
        else:
            top_level[dotted] = value

    new_field_values: dict[str, Any] = dict(top_level)
    for top_field, sub_overrides in nested.items():
        existing = getattr(obj, top_field)
        new_field_values[top_field] = _apply_overrides_dataclass(
            existing, sub_overrides,
        )
    return replace(obj, **new_field_values)


def _winners_per_metric(
    configs: Sequence[ConfigResult],
) -> dict[str, WinnerByMetric]:
    """Pick the best config for each supported metric.

    For "higher is better" metrics (Sharpe / return / Calmar) we pick
    argmax; for "lower is better" (MaxDD / turnover) we pick argmin.
    Skips entries where the metric is None (e.g. Calmar undefined when
    drawdown is zero).
    """

    out: dict[str, WinnerByMetric] = {}
    for metric in sorted(SUPPORTED_METRICS):
        higher_better = metric in METRICS_HIGHER_IS_BETTER
        best: Optional[ConfigResult] = None
        best_score: Optional[float] = None
        for cr in configs:
            score = _metric_value(cr, metric)
            if score is None or not math.isfinite(score):
                continue
            if best_score is None:
                best = cr
                best_score = score
                continue
            if (higher_better and score > best_score) or ((not higher_better) and score < best_score):
                best = cr
                best_score = score
        out[metric] = WinnerByMetric(
            metric=metric,
            config_id=best.config_id if best is not None else None,
            parameters=dict(best.parameters) if best is not None else None,
            score=best_score,
        )
    return out


def _top_n_by_metric(
    configs: Sequence[ConfigResult],
    *,
    metric: str,
    n: int,
) -> list[ConfigResult]:
    """Return the top-N configs by ``metric``, best first.

    Configs where the metric is None / NaN are dropped before ranking so
    they don't sort to the top via Python's None-handling quirks.
    """

    higher_better = metric in METRICS_HIGHER_IS_BETTER
    ranked: list[tuple[float, ConfigResult]] = []
    for cr in configs:
        score = _metric_value(cr, metric)
        if score is None or not math.isfinite(score):
            continue
        ranked.append((score, cr))
    ranked.sort(key=lambda t: t[0], reverse=higher_better)
    return [cr for _, cr in ranked[:n]]


def _metric_value(cr: ConfigResult, metric: str) -> Optional[float]:
    """Extract ``metric`` from a :class:`ConfigResult` row."""

    value = getattr(cr, metric, None)
    if value is None:
        return None
    return float(value)


def _compute_sensitivity(
    configs: Sequence[ConfigResult],
    parameter_keys: Sequence[str],
) -> list[ParameterSensitivity]:
    """One sensitivity entry per swept parameter, sorted by descending std.

    For each parameter, group the configs by the value of that parameter
    and compute the mean Sharpe per group. The std of those group means
    is the sensitivity reading — higher = the parameter matters more.

    A single-value grid produces a one-element ``mean_sharpe_per_value``
    map and zero std / range — those parameters end up at the bottom of
    the ranking (consistent with "didn't sweep, doesn't matter").
    """

    out: list[ParameterSensitivity] = []
    for param in parameter_keys:
        grouped: dict[Any, list[float]] = {}
        for cr in configs:
            value = cr.parameters.get(param)
            if value is None:
                continue
            sharpe = cr.sharpe_ratio
            if not math.isfinite(sharpe):
                continue
            grouped.setdefault(value, []).append(sharpe)
        if not grouped:
            continue
        means: dict[str, float] = {}
        for v, samples in grouped.items():
            if samples:
                # Stringify the key so the JSON payload survives mixed
                # int/float/str values without dict-key collisions.
                means[str(v)] = float(statistics.fmean(samples))
        mean_values = list(means.values())
        if len(mean_values) >= 2:
            std = float(statistics.pstdev(mean_values))
            spread = float(max(mean_values) - min(mean_values))
        else:
            std = 0.0
            spread = 0.0
        out.append(
            ParameterSensitivity(
                parameter=param,
                values=sorted(grouped.keys(), key=lambda x: str(x)),
                mean_sharpe_per_value=means,
                sharpe_std=std,
                sharpe_range=spread,
            )
        )
    out.sort(key=lambda p: p.sharpe_std, reverse=True)
    return out


def _bootstrap_top_n_cis(
    top_n: Sequence[ConfigResult],
    *,
    n_iterations: int,
    seed: int,
) -> list[ConfidenceInterval]:
    """Compute a 95% bootstrap CI on Sharpe for each top-N config.

    Resamples the equity curve's daily returns with replacement
    ``n_iterations`` times and recomputes Sharpe each iteration. The
    empirical 2.5% / 97.5% quantiles bracket the 95% CI.

    Returns an empty list when ``n_iterations == 0`` or when no config
    has enough bars to bootstrap (every report short-circuits before the
    equity curve is recorded).
    """

    if n_iterations <= 0:
        return []
    out: list[ConfidenceInterval] = []
    for cr in top_n:
        rebalance_log = cr.report.rebalance_log
        # Use rebalance-period returns when available — they're the
        # bars the strategy actually trades on. Skip configs with too
        # few rebalances; their Sharpe is already noise.
        returns = [
            float(entry.get("period_return_pct", 0.0)) / 100.0
            for entry in rebalance_log
            if entry.get("period_return_pct") is not None
        ]
        if len(returns) < 3:
            continue
        rng = random.Random(seed + cr.config_id)
        sharpes: list[float] = []
        n = len(returns)
        for _ in range(n_iterations):
            sample = [returns[rng.randrange(n)] for _ in range(n)]
            sample_sharpe = _sharpe_from_returns(sample)
            sharpes.append(sample_sharpe)
        sharpes.sort()
        lo = sharpes[int(DEFAULT_BOOTSTRAP_CI_LOW * len(sharpes))]
        hi = sharpes[int(DEFAULT_BOOTSTRAP_CI_HIGH * len(sharpes))]
        out.append(
            ConfidenceInterval(
                config_id=cr.config_id,
                parameters=dict(cr.parameters),
                point_estimate_sharpe=cr.sharpe_ratio,
                ci_low=float(lo),
                ci_high=float(hi),
                n_iterations=n_iterations,
            )
        )
    return out


def _sharpe_from_returns(returns: Sequence[float]) -> float:
    """Per-period Sharpe (no annualization).

    Bootstrap consumers care about the *shape* of the distribution, not
    the absolute level, so we skip the annualization factor — it would
    just rescale every bootstrap sample uniformly.
    """

    if len(returns) < 2:
        return 0.0
    mean = statistics.fmean(returns)
    try:
        std = statistics.pstdev(returns)
    except statistics.StatisticsError:
        return 0.0
    if std < 1e-15:
        return 0.0
    return mean / std


def _to_iso(value: Optional[Union[str, datetime, pd.Timestamp]]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, pd.Timestamp):
        return str(value.date())
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)


__all__ = [
    "DEFAULT_BOOTSTRAP_CI_HIGH",
    "DEFAULT_BOOTSTRAP_CI_LOW",
    "DEFAULT_BOOTSTRAP_ITERATIONS",
    "DEFAULT_OPTIMIZE_METRIC",
    "MAX_GRID_SIZE",
    "METRICS_HIGHER_IS_BETTER",
    "METRICS_LOWER_IS_BETTER",
    "SUPPORTED_METRICS",
    "ConfidenceInterval",
    "ConfigResult",
    "OptimizationReport",
    "ParameterOptimizer",
    "ParameterSensitivity",
    "WinnerByMetric",
]
