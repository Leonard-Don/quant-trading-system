#!/usr/bin/env python3
"""Grid-search parameter optimizer CLI for the ETF rotation strategy family.

Wraps :class:`src.backtest.parameter_optimizer.ParameterOptimizer` so the
same code path the backend endpoint uses can be driven from the shell.

Typical use::

    python scripts/optimize_strategy.py \\
        --strategy rotation \\
        --grid-json grids/rotation_basic.json \\
        --start-date 2024-01-01 \\
        --end-date 2025-04-30 \\
        --metric sharpe \\
        --top-n 10 \\
        --with-walkforward \\
        --output-md docs/sample_parameter_optimization.md \\
        --output-json output/parameter_optimization.json

The grid JSON file is a dict ``{parameter: [candidate_values]}``. Nested
dataclass fields can be addressed via dotted names, e.g.
``"scoring.trend_above_ma20_points": [15.0, 25.0]``.

Strategy aliases
----------------
* ``rotation`` — uses the production ``EtfRotationStrategy`` config.
* ``mean_reversion`` — derives an MR config from the rotation universe;
  the optimizer still consumes ``EtfRotationConfig`` knobs, so this flag
  signals which strategy family the grid keys refer to. v0.1: rotation
  is the supported optimizer target; the mean_reversion / blend aliases
  remain so the CLI surface matches the spec — they delegate to the
  rotation engine via the same shared universe today, mirroring how
  ``StrategyComparator`` treats them. Caller is responsible for picking
  grid keys that exist on the underlying config (the validator catches
  mistakes either way).

The script inherits every caveat of the underlying backtest harness
(see ``src/backtest/etf_rotation_backtest.py``).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.daily_etf_signal import (  # noqa: E402
    build_strategy_config,
    load_default_holdings,
    load_policy_industry_signals,
)
from src.backtest.etf_rotation_backtest import (  # noqa: E402
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_REBALANCE_FREQ_DAYS,
)
from src.backtest.etf_rotation_walkforward import (  # noqa: E402
    DEFAULT_STEP_MONTHS,
    DEFAULT_WINDOW_MONTHS,
)
from src.backtest.parameter_optimizer import (  # noqa: E402
    MAX_GRID_SIZE,
    SUPPORTED_METRICS,
    OptimizationReport,
    ParameterOptimizer,
)
from src.backtest.transaction_costs import TransactionCostModel  # noqa: E402
from src.data.etf_price_history import resolve_default_price_csv  # noqa: E402
from src.strategy.etf_rotation_config_loader import (  # noqa: E402
    StrategyConfig,
    load_strategy_config,
)

logger = logging.getLogger(__name__)


# Map between CLI metric aliases and the full metric names on the report.
_METRIC_ALIASES: dict[str, str] = {
    "sharpe": "sharpe_ratio",
    "return": "total_return_pct",
    "calmar": "calmar_ratio",
    "max_dd": "max_drawdown_pct",
    "turnover": "avg_turnover_pct",
    "win_rate": "win_rate",
}


def _load_price_matrix(prices_csv: Path) -> pd.DataFrame:
    """Load a wide CSV (date index, ETF code columns) into a price matrix."""

    frame = pd.read_csv(prices_csv, index_col=0)
    frame.index = pd.to_datetime(frame.index)
    return (
        frame.apply(pd.to_numeric, errors="coerce")
        .sort_index()
        .ffill()
        .dropna(how="all")
    )


def _apply_strategy_overrides(
    cfg: StrategyConfig,
    overrides: dict[str, Any],
) -> StrategyConfig:
    """Shallow-merge overrides into the loaded StrategyConfig.

    Used for non-grid baseline tweaks (e.g. ``--strategy-config-overrides``
    pinning a baseline param the grid doesn't sweep).
    """

    new_strategy = {**cfg.strategy, **overrides}
    return replace(cfg, strategy=new_strategy)


def _parse_grid_json(path: Path) -> dict[str, list[Any]]:
    """Load and validate the grid JSON file."""

    with path.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)
    if not isinstance(raw, dict):
        raise ValueError(
            f"Grid file {path} must contain a top-level JSON object."
        )
    out: dict[str, list[Any]] = {}
    for key, values in raw.items():
        if not isinstance(key, str):
            raise ValueError(f"Grid keys must be strings; got {key!r}")
        if not isinstance(values, list) or not values:
            raise ValueError(
                f"Grid values for {key!r} must be a non-empty JSON array."
            )
        out[key] = values
    return out


def run_optimization(
    *,
    strategy: str,
    grid_json: Path,
    prices_csv: Path,
    start_date: str,
    end_date: str,
    metric: str = "sharpe_ratio",
    top_n: int = 10,
    enable_policy_signal: bool = False,
    rebalance_freq_days: int = DEFAULT_REBALANCE_FREQ_DAYS,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    with_walkforward: bool = False,
    walkforward_window_months: int = DEFAULT_WINDOW_MONTHS,
    walkforward_step_months: int = DEFAULT_STEP_MONTHS,
    strategy_config_path: Optional[Path] = None,
    strategy_config_overrides: Optional[dict[str, Any]] = None,
    tc_model: Optional[TransactionCostModel] = None,
    max_grid_size: int = MAX_GRID_SIZE,
) -> OptimizationReport:
    """Top-level orchestration shared by the CLI + (future) API.

    Resolves the price matrix + base strategy config, loads the grid
    JSON, instantiates the optimizer, and returns its report. Mirrors
    the structure of ``run_walkforward`` in
    ``scripts/walkforward_etf_rotation_strategy.py``.
    """

    if strategy not in {"rotation", "mean_reversion", "blend"}:
        raise ValueError(
            f"strategy must be one of rotation|mean_reversion|blend; got {strategy!r}"
        )

    prices = _load_price_matrix(prices_csv)
    strategy_cfg = load_strategy_config(strategy_config_path)
    if strategy_config_overrides:
        strategy_cfg = _apply_strategy_overrides(
            strategy_cfg, strategy_config_overrides,
        )

    holdings = [h for h in load_default_holdings() if h.code in prices.columns]
    if not holdings:
        config = build_strategy_config(load_default_holdings(), strategy_cfg)
    else:
        config = build_strategy_config(holdings, strategy_cfg)

    industry_signals: dict[str, dict[str, Any]] = {}
    etf_industry_map: dict[str, str] = dict(strategy_cfg.etf_industry_map)
    if enable_policy_signal:
        loaded, _ = load_policy_industry_signals()
        industry_signals = dict(loaded)

    grid = _parse_grid_json(grid_json)

    optimizer = ParameterOptimizer(
        base_config=config,
        price_history=prices,
        parameter_grid=grid,
        period_start=start_date,
        period_end=end_date,
        policy_signal_factor_enabled=enable_policy_signal,
        industry_signals=industry_signals or None,
        etf_industry_map=etf_industry_map or None,
        rebalance_freq_days=rebalance_freq_days,
        initial_capital=initial_capital,
        tc_model=tc_model,
        optimize_for=metric,
        top_n=top_n,
        max_grid_size=max_grid_size,
    )
    return optimizer.run(
        with_walkforward=with_walkforward,
        walkforward_window_months=walkforward_window_months,
        walkforward_step_months=walkforward_step_months,
    )


def render_report_markdown(
    report: OptimizationReport,
    *,
    strategy: str,
) -> str:
    """Render the optimization report as a human-readable markdown block.

    Surfaces the three things the user actually cares about:
    top-N configs by chosen metric, per-metric winners, and the
    parameter-sensitivity ranking. The full ``configurations`` list is
    skipped here — that's what the JSON dump is for.
    """

    lines: list[str] = []
    lines.append(f"# Parameter Optimization Report — {strategy}")
    lines.append("")
    lines.append(
        f"- Period: {report.period_start} → {report.period_end}"
    )
    lines.append(
        f"- Optimize metric: ``{report.optimize_metric}``"
    )
    lines.append(
        f"- Configs evaluated: {report.n_configs_evaluated} "
        f"(grid requested {report.n_configs_requested})"
    )
    lines.append("")

    lines.append("## Optimal config per metric")
    lines.append("")
    lines.append("| Metric | Config ID | Score | Parameters |")
    lines.append("| --- | ---: | ---: | --- |")
    for metric in sorted(report.optimal_by_metric.keys()):
        winner = report.optimal_by_metric[metric]
        score_str = (
            f"{winner.score:.4f}" if winner.score is not None else "n/a"
        )
        params_str = (
            ", ".join(f"{k}={v}" for k, v in (winner.parameters or {}).items())
            if winner.parameters
            else "—"
        )
        lines.append(
            f"| {metric} | {winner.config_id if winner.config_id is not None else '—'} "
            f"| {score_str} | {params_str} |"
        )
    lines.append("")

    if report.top_n_by_metric:
        lines.append(f"## Top {len(report.top_n_by_metric)} configs by ``{report.optimize_metric}``")
        lines.append("")
        lines.append(
            "| Rank | Config ID | Sharpe | Return % | MaxDD % | Calmar | Turnover % | Parameters |"
        )
        lines.append("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
        for rank, cr in enumerate(report.top_n_by_metric, start=1):
            params_str = ", ".join(
                f"{k}={v}" for k, v in cr.parameters.items()
            )
            calmar_str = (
                f"{cr.calmar_ratio:.3f}" if cr.calmar_ratio is not None else "n/a"
            )
            lines.append(
                f"| {rank} | {cr.config_id} | {cr.sharpe_ratio:.3f} "
                f"| {cr.total_return_pct:.2f} | {cr.max_drawdown_pct:.2f} "
                f"| {calmar_str} | {cr.avg_turnover_pct:.2f} | {params_str} |"
            )
        lines.append("")

    if report.parameter_sensitivity:
        lines.append("## Parameter sensitivity (Sharpe variance ranking)")
        lines.append("")
        lines.append(
            "Per-parameter mean-Sharpe spread when the parameter is fixed at "
            "each candidate value. Larger ``sharpe_std`` and ``sharpe_range`` "
            "mean the parameter actually moves the needle; small values mean "
            "you can pick anything in the grid without noticeable impact."
        )
        lines.append("")
        lines.append("| Parameter | Sharpe std | Sharpe range | Values |")
        lines.append("| --- | ---: | ---: | --- |")
        for sens in report.parameter_sensitivity:
            values_str = ", ".join(str(v) for v in sens.values)
            lines.append(
                f"| {sens.parameter} | {sens.sharpe_std:.4f} "
                f"| {sens.sharpe_range:.4f} | {values_str} |"
            )
        lines.append("")

    if report.confidence_intervals:
        lines.append("## Bootstrap 95% CI on Sharpe (top-N configs)")
        lines.append("")
        lines.append(
            "Resampled the per-rebalance returns with replacement "
            f"({report.confidence_intervals[0].n_iterations} iterations) and "
            "took the 2.5% / 97.5% quantiles. If the runner-up's CI overlaps "
            "the leader's point estimate, the apparent winner may be noise."
        )
        lines.append("")
        lines.append("| Config ID | Point Sharpe | CI low | CI high | Parameters |")
        lines.append("| ---: | ---: | ---: | ---: | --- |")
        for ci in report.confidence_intervals:
            params_str = ", ".join(
                f"{k}={v}" for k, v in ci.parameters.items()
            )
            lines.append(
                f"| {ci.config_id} | {ci.point_estimate_sharpe:.3f} "
                f"| {ci.ci_low:.3f} | {ci.ci_high:.3f} | {params_str} |"
            )
        lines.append("")

    if report.walkforward_results:
        lines.append("## Walkforward stability (top-N configs)")
        lines.append("")
        lines.append(
            "Each top-N config re-tested across rolling sub-windows. "
            "``consistency_score`` is in [0, 1]; "
            "``pct_positive_windows`` is the share of windows that finished "
            "positive. A config that wins in-sample but tanks on walkforward "
            "is fragile."
        )
        lines.append("")
        lines.append(
            "| Config ID | Windows | Mean window return % | "
            "Median window return % | Pct positive | Mean Sharpe | "
            "Consistency |"
        )
        lines.append(
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
        )
        for cid, wf in report.walkforward_results.items():
            lines.append(
                f"| {cid} | {wf.n_windows} | {wf.mean_window_return_pct:.2f} "
                f"| {wf.median_window_return_pct:.2f} "
                f"| {wf.pct_positive_windows * 100:.0f}% "
                f"| {wf.mean_sharpe:.3f} | {wf.consistency_score:.3f} |"
            )
        lines.append("")

    if report.caveats:
        lines.append("## Caveats")
        lines.append("")
        for caveat in report.caveats:
            lines.append(f"- {caveat}")
        lines.append("")

    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Grid-search + sensitivity-analysis parameter optimizer for the "
            "ETF rotation strategy family. Sweeps any subset of "
            "EtfRotationConfig fields (top-level or dotted nested) and "
            "reports per-metric optima + parameter-sensitivity ranking + "
            "bootstrap CIs on the top-N configs."
        ),
    )
    parser.add_argument(
        "--strategy",
        choices=("rotation", "mean_reversion", "blend"),
        default="rotation",
        help="Strategy family to optimize (default: rotation).",
    )
    parser.add_argument(
        "--grid-json",
        type=Path,
        required=True,
        help="Path to a JSON file describing the parameter grid.",
    )
    parser.add_argument(
        "--prices-csv",
        type=Path,
        default=resolve_default_price_csv(PROJECT_ROOT),
        help="Wide-form price matrix CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="ISO date that bounds the in-sample window (inclusive).",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="ISO date that bounds the in-sample window (inclusive).",
    )
    parser.add_argument(
        "--metric",
        choices=sorted(_METRIC_ALIASES.keys()) + sorted(SUPPORTED_METRICS),
        default="sharpe",
        help=(
            "Metric to optimize. Short aliases (sharpe / return / calmar / "
            "max_dd / turnover / win_rate) map to the corresponding "
            "BacktestReport field. (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of top configs to surface in the report (default: %(default)d).",
    )
    parser.add_argument(
        "--enable-policy-signal",
        action="store_true",
        help="Enable the policy_signal_factor for every config.",
    )
    parser.add_argument(
        "--rebalance-freq-days",
        type=int,
        default=DEFAULT_REBALANCE_FREQ_DAYS,
        help="Rebalance cadence in business days (default: %(default)d).",
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=DEFAULT_INITIAL_CAPITAL,
        help="Initial portfolio capital (default: %(default)s).",
    )
    parser.add_argument(
        "--with-walkforward",
        action="store_true",
        help=(
            "Re-test the top-N configs on rolling sub-windows for "
            "additional robustness signal. Adds ~10-30s per config."
        ),
    )
    parser.add_argument(
        "--walkforward-window-months",
        type=int,
        default=DEFAULT_WINDOW_MONTHS,
        help="Walkforward window length in months (default: %(default)d).",
    )
    parser.add_argument(
        "--walkforward-step-months",
        type=int,
        default=DEFAULT_STEP_MONTHS,
        help="Walkforward step length in months (default: %(default)d).",
    )
    parser.add_argument(
        "--max-grid-size",
        type=int,
        default=MAX_GRID_SIZE,
        help=(
            "Hard cap on the cartesian-product grid size (default: %(default)d). "
            "Raise explicitly when you really do want a multi-hour run."
        ),
    )
    parser.add_argument(
        "--strategy-config-path",
        type=Path,
        default=None,
        help="Override path to strategy.json (default: project default).",
    )
    parser.add_argument(
        "--strategy-config-overrides",
        type=str,
        default=None,
        help=(
            "JSON object with baseline strategy overrides (applied before the grid). "
            'Example: \'{"warmup_days": 90}\'.'
        ),
    )
    parser.add_argument(
        "--enable-tc",
        action="store_true",
        help="Enable the default TransactionCostModel for every config.",
    )
    parser.add_argument(
        "--commission-bps",
        type=float,
        default=None,
        help="Override commission_bps when --enable-tc is set.",
    )
    parser.add_argument(
        "--spread-bps",
        type=float,
        default=None,
        help="Override bid_ask_spread_bps when --enable-tc is set.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="Optional markdown report path.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional JSON dump path (the full OptimizationReport).",
    )
    return parser


def _build_tc_model(args: argparse.Namespace) -> Optional[TransactionCostModel]:
    """Return a TC model when ``--enable-tc`` is set, else None."""

    if not args.enable_tc:
        return None
    overrides: dict[str, Any] = {}
    if args.commission_bps is not None:
        overrides["commission_bps"] = float(args.commission_bps)
    if args.spread_bps is not None:
        overrides["bid_ask_spread_bps"] = float(args.spread_bps)
    if overrides:
        return TransactionCostModel.from_overrides(overrides)
    return TransactionCostModel()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    metric_name = _METRIC_ALIASES.get(args.metric, args.metric)
    if metric_name not in SUPPORTED_METRICS:
        print(
            f"Unsupported metric {args.metric!r}; allowed: "
            f"{sorted(_METRIC_ALIASES.keys())} or {sorted(SUPPORTED_METRICS)}",
            file=sys.stderr,
        )
        return 2

    overrides: Optional[dict[str, Any]] = None
    if args.strategy_config_overrides:
        overrides = json.loads(args.strategy_config_overrides)
        if not isinstance(overrides, dict):
            print("--strategy-config-overrides must be a JSON object.", file=sys.stderr)
            return 2

    report = run_optimization(
        strategy=args.strategy,
        grid_json=args.grid_json,
        prices_csv=args.prices_csv,
        start_date=args.start_date,
        end_date=args.end_date,
        metric=metric_name,
        top_n=args.top_n,
        enable_policy_signal=args.enable_policy_signal,
        rebalance_freq_days=args.rebalance_freq_days,
        initial_capital=args.initial_capital,
        with_walkforward=args.with_walkforward,
        walkforward_window_months=args.walkforward_window_months,
        walkforward_step_months=args.walkforward_step_months,
        strategy_config_path=args.strategy_config_path,
        strategy_config_overrides=overrides,
        tc_model=_build_tc_model(args),
        max_grid_size=args.max_grid_size,
    )

    md = render_report_markdown(report, strategy=args.strategy)
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(md, encoding="utf-8")
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
