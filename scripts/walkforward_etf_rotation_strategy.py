#!/usr/bin/env python3
"""Walkforward stability analyzer for the ETF rotation strategy.

Wraps :class:`EtfRotationWalkforwardAnalyzer` so the same code path the
backend endpoint uses can also be driven from the shell.

The single-window backtest harness
(``scripts/backtest_etf_rotation_strategy.py`` →
``EtfRotationBacktester``) gives you one data point per call. This script
rolls that harness across multiple overlapping windows of the *same*
committed historical price matrix and reports how stable the strategy's
performance is across windows.

Typical use::

    python scripts/walkforward_etf_rotation_strategy.py \\
        --prices-csv data/etf_backtest/etf_prices_4y.csv \\
        --start-date 2024-01-01 \\
        --end-date 2025-04-30 \\
        --window-months 3 \\
        --step-months 1 \\
        --output-md docs/sample_walkforward_report.md \\
        --output-json output/walkforward.json

The ``--enable-policy-signal`` flag toggles ``policy_signal_factor`` for
the *entire run* — pair it with two separate runs to A/B the factor
across the same set of windows.

v0.1 inherits **every** caveat of the underlying backtest harness — see
``src/backtest/etf_rotation_backtest.py`` and the per-report ``caveats``
list for the full inventory.
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
    EtfRotationWalkforwardAnalyzer,
    WalkforwardReport,
)
from src.backtest.transaction_costs import (  # noqa: E402
    DEFAULT_BID_ASK_SPREAD_BPS,
    DEFAULT_COMMISSION_BPS,
    DEFAULT_MARKET_IMPACT_BPS_PER_PCT_ADV,
    DEFAULT_MIN_COMMISSION_PER_TRADE,
    DEFAULT_MIN_TRADE_SIZE_RMB,
    TransactionCostModel,
)
from src.strategy.etf_rotation_config_loader import (  # noqa: E402
    StrategyConfig,
    load_strategy_config,
)

logger = logging.getLogger(__name__)


def load_price_matrix(prices_csv: Path) -> pd.DataFrame:
    """Load a wide CSV (date index, ETF code columns) into a price matrix.

    Mirrors :func:`scripts.backtest_etf_rotation_strategy.load_price_matrix`
    so the two CLIs have a single source of price-loading semantics.
    """

    frame = pd.read_csv(prices_csv, index_col=0)
    frame.index = pd.to_datetime(frame.index)
    return (
        frame.apply(pd.to_numeric, errors="coerce")
        .sort_index()
        .ffill()
        .dropna(how="all")
    )


def run_walkforward(
    prices_csv: Path,
    *,
    start_date: str,
    end_date: str,
    window_months: int = DEFAULT_WINDOW_MONTHS,
    step_months: int = DEFAULT_STEP_MONTHS,
    enable_policy_signal: bool = False,
    rebalance_freq_days: int = DEFAULT_REBALANCE_FREQ_DAYS,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    strategy_config_path: Optional[Path] = None,
    strategy_config_overrides: Optional[dict[str, Any]] = None,
    tc_model: Optional[TransactionCostModel] = None,
) -> WalkforwardReport:
    """Top-level orchestration shared by the CLI + API.

    Mirrors :func:`scripts.backtest_etf_rotation_strategy.run_backtest`
    so both endpoints share identical strategy-config + universe
    resolution semantics; only the rolling-window layer differs.
    """

    prices = load_price_matrix(prices_csv)
    strategy_cfg = load_strategy_config(strategy_config_path)

    if strategy_config_overrides:
        strategy_cfg = _apply_strategy_overrides(strategy_cfg, strategy_config_overrides)

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

    analyzer = EtfRotationWalkforwardAnalyzer(
        config=config,
        price_history=prices,
        window_months=window_months,
        step_months=step_months,
        period_start=start_date,
        period_end=end_date,
        policy_signal_factor_enabled=enable_policy_signal,
        industry_signals=industry_signals or None,
        etf_industry_map=etf_industry_map or None,
        rebalance_freq_days=rebalance_freq_days,
        initial_capital=initial_capital,
        tc_model=tc_model,
    )
    return analyzer.run()


def _apply_strategy_overrides(
    cfg: StrategyConfig,
    overrides: dict[str, Any],
) -> StrategyConfig:
    """Shallow-merge user overrides into the resolved StrategyConfig.

    Mirrors the v0.1 backtest CLI helper so both share semantics.
    """

    new_strategy = {**cfg.strategy, **overrides}
    return replace(cfg, strategy=new_strategy)


def format_report_markdown(report: WalkforwardReport) -> str:
    """Render a :class:`WalkforwardReport` as a human-readable markdown block.

    The shape mirrors :func:`scripts.backtest_etf_rotation_strategy.format_report_markdown`
    so a reader who knows one document knows the other.
    """

    def _pct(value: float) -> str:
        return f"{value:+.2f}%"

    def _opt(value: Optional[float]) -> str:
        return f"{value:.2f}" if value is not None else "n/a"

    lines: list[str] = []
    lines.append("# ETF Rotation Walkforward Report")
    lines.append("")
    lines.append(f"- Outer period: `{report.period_start} → {report.period_end}`")
    lines.append(
        f"- Windows: {report.n_windows} × {report.window_months}-month, "
        f"stepping {report.step_months}-month"
    )
    lines.append(
        f"- Rebalance cadence: every {report.rebalance_freq_days} bar(s)"
    )
    lines.append(
        f"- policy_signal_factor enabled: **{report.policy_signal_factor_enabled}**"
    )
    lines.append("")
    lines.append("## Aggregate Stability")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Median window return | {_pct(report.median_window_return_pct)} |")
    lines.append(f"| Mean window return | {_pct(report.mean_window_return_pct)} |")
    lines.append(
        f"| Std-dev of window returns | {report.return_std_pct:.2f} pp |"
    )
    n_positive = round(report.pct_positive_windows * report.n_windows)
    lines.append(
        f"| % positive windows | {report.pct_positive_windows * 100:.1f}% "
        f"({n_positive}/{report.n_windows}) |"
    )
    lines.append(f"| Mean Sharpe | {_opt(report.mean_sharpe)} |")
    lines.append(f"| Median Sharpe | {_opt(report.median_sharpe)} |")
    lines.append(f"| Mean max-drawdown | {report.mean_max_dd_pct:.2f}% |")
    lines.append(f"| Worst-window drawdown | {report.worst_window_dd_pct:.2f}% |")
    lines.append(
        f"| Mean buy-and-hold (per window) | {_pct(report.mean_buy_hold_return_pct)} |"
    )
    lines.append(
        f"| Consistency score (0-1) | {report.consistency_score:.3f} |"
    )
    lines.append(
        f"| Aggregate compounded (overlap-double-counted) | "
        f"{_pct(report.aggregate_return_pct)} |"
    )
    lines.append("")
    if report.tc_enabled:
        lines.append("## Transaction Costs (per-window mean)")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        lines.append(
            f"| Mean gross window return | {_pct(report.mean_gross_return_pct)} |"
        )
        lines.append(
            f"| Mean net window return | {_pct(report.mean_net_return_pct)} |"
        )
        lines.append(
            f"| Mean per-window TC cost | {report.mean_tc_cost_pct:.4f}% |"
        )
        lines.append(
            f"| Mean TC drag (annualized) | {report.mean_tc_drag_annualized_pct:.2f}% |"
        )
        lines.append("")
    if report.windows:
        lines.append("## Per-Window Breakdown")
        lines.append("")
        lines.append(
            "| # | Period | Return | Sharpe | MaxDD | Buy-Hold | Win Rate |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for idx, win in enumerate(report.windows, start=1):
            lines.append(
                f"| {idx} | "
                f"{win.period_start} → {win.period_end} | "
                f"{_pct(win.total_return_pct)} | "
                f"{_opt(win.sharpe_ratio)} | "
                f"{win.max_drawdown_pct:.2f}% | "
                f"{_pct(win.comparable_buy_hold_return_pct)} | "
                f"{win.win_rate * 100:.1f}% |"
            )
        lines.append("")
    lines.append("## Caveats")
    lines.append("")
    for caveat in report.caveats:
        lines.append(f"- `{caveat}`")
    lines.append("")
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Roll EtfRotationBacktester across overlapping windows and report stability."
        ),
    )
    parser.add_argument("--prices-csv", required=True, type=Path)
    parser.add_argument(
        "--start-date",
        required=True,
        help="Outer period start, ISO date, inclusive.",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="Outer period end, ISO date, inclusive.",
    )
    parser.add_argument(
        "--window-months",
        type=int,
        default=DEFAULT_WINDOW_MONTHS,
        help=f"Rolling window length in months. Default {DEFAULT_WINDOW_MONTHS}.",
    )
    parser.add_argument(
        "--step-months",
        type=int,
        default=DEFAULT_STEP_MONTHS,
        help=f"Step between consecutive windows in months. Default {DEFAULT_STEP_MONTHS}.",
    )
    parser.add_argument(
        "--enable-policy-signal",
        action="store_true",
        help="Enable policy_signal_factor for every window (default off).",
    )
    parser.add_argument(
        "--strategy-config",
        type=Path,
        default=None,
        help="Optional path to a strategy.json override file.",
    )
    parser.add_argument(
        "--rebalance-freq-days",
        type=int,
        default=DEFAULT_REBALANCE_FREQ_DAYS,
        help=(
            "Rebalance cadence in business days. Default 5 (~weekly)."
        ),
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=DEFAULT_INITIAL_CAPITAL,
    )
    parser.add_argument(
        "--enable-tc",
        action="store_true",
        help=(
            "Enable transaction-cost modelling across every window "
            "(defaults track CN ETF retail brokerage)."
        ),
    )
    parser.add_argument(
        "--commission-bps", type=float, default=DEFAULT_COMMISSION_BPS,
    )
    parser.add_argument(
        "--spread-bps", type=float, default=DEFAULT_BID_ASK_SPREAD_BPS,
    )
    parser.add_argument(
        "--impact-bps-per-pct-adv",
        type=float,
        default=DEFAULT_MARKET_IMPACT_BPS_PER_PCT_ADV,
    )
    parser.add_argument(
        "--min-commission-rmb",
        type=float,
        default=DEFAULT_MIN_COMMISSION_PER_TRADE,
    )
    parser.add_argument(
        "--min-trade-size-rmb",
        type=float,
        default=DEFAULT_MIN_TRADE_SIZE_RMB,
    )
    parser.add_argument("--output-md", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    return parser


def _build_tc_model_from_args(args: argparse.Namespace) -> Optional[TransactionCostModel]:
    """Translate CLI flags into a :class:`TransactionCostModel` or None."""

    if not getattr(args, "enable_tc", False):
        return None
    return TransactionCostModel(
        commission_bps=args.commission_bps,
        bid_ask_spread_bps=args.spread_bps,
        market_impact_bps_per_pct_adv=args.impact_bps_per_pct_adv,
        min_commission_per_trade=args.min_commission_rmb,
        min_trade_size_rmb=args.min_trade_size_rmb,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _build_arg_parser().parse_args(argv)

    report = run_walkforward(
        args.prices_csv,
        start_date=args.start_date,
        end_date=args.end_date,
        window_months=args.window_months,
        step_months=args.step_months,
        enable_policy_signal=args.enable_policy_signal,
        rebalance_freq_days=args.rebalance_freq_days,
        initial_capital=args.initial_capital,
        strategy_config_path=args.strategy_config,
        tc_model=_build_tc_model_from_args(args),
    )

    payload = report.to_dict()

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    if args.output_md is not None:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(format_report_markdown(report), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
