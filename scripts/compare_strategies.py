#!/usr/bin/env python3
"""Compare ETF rotation / mean-reversion / blend strategies head-to-head.

Wraps :class:`StrategyComparator` so the same code path the backend
endpoint uses can also be driven from the shell. Designed to answer:

* "On the *same* historical window, which strategy posts the best
  Sharpe / total return / Calmar?"
* "Does the blender beat both children, or just average them?"
* "Does rotation dominate the trending half but bleed in chop, where
  mean reversion takes over?" → ``regime_analysis`` in the output.

Typical use::

    python scripts/compare_strategies.py \\
        --prices-csv data/etf_backtest/etf_prices_4y.csv \\
        --period-start 2024-01-01 \\
        --period-end 2025-04-30 \\
        --strategies rotation,mean_reversion,blend \\
        --output-md docs/sample_strategy_comparison.md \\
        --output-json output/strategy_comparison.json

All v0.1 caveats from the underlying single-strategy backtester carry
over unchanged — no TC, no spread/slippage, no impact, next-bar close
fills only. The comparison is internally apples-to-apples but absolute
returns are not cost-adjusted.
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
from src.backtest.strategy_comparison import (  # noqa: E402
    DEFAULT_STRATEGY_LABELS,
    ComparisonReport,
    StrategyComparator,
    build_default_strategy_specs,
    render_comparison_markdown,
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

    Mirrors :func:`scripts.walkforward_etf_rotation_strategy.load_price_matrix`
    so the three CLIs (backtest / walkforward / compare) share one
    source of price-loading semantics.
    """

    frame = pd.read_csv(prices_csv, index_col=0)
    frame.index = pd.to_datetime(frame.index)
    return (
        frame.apply(pd.to_numeric, errors="coerce")
        .sort_index()
        .ffill()
        .dropna(how="all")
    )


def _parse_strategy_list(raw: str) -> list[str]:
    """Parse the comma-separated --strategies flag and validate each label."""

    if not raw:
        return list(DEFAULT_STRATEGY_LABELS)
    items = [piece.strip() for piece in raw.split(",") if piece.strip()]
    unknown = [item for item in items if item not in DEFAULT_STRATEGY_LABELS]
    if unknown:
        raise ValueError(
            f"Unknown strategies {unknown!r}; valid options are "
            f"{list(DEFAULT_STRATEGY_LABELS)}"
        )
    # Preserve user-supplied order so the report layout follows what
    # the caller asked for; ``set`` would scramble it.
    deduped: list[str] = []
    for item in items:
        if item not in deduped:
            deduped.append(item)
    return deduped


def run_comparison(
    prices_csv: Path,
    *,
    period_start: str,
    period_end: str,
    strategy_labels: Sequence[str] = DEFAULT_STRATEGY_LABELS,
    enable_policy_signal: bool = False,
    rebalance_freq_days: int = DEFAULT_REBALANCE_FREQ_DAYS,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    strategy_config_path: Optional[Path] = None,
    strategy_config_overrides: Optional[dict[str, Any]] = None,
    blend_regime: str = "unknown",
    tc_model: Optional[TransactionCostModel] = None,
    compute_statistical_tests: bool = False,
    statistical_alpha: float = 0.05,
    statistical_block_size: int = 10,
    statistical_n_bootstrap: int = 1000,
    statistical_include_buy_hold: bool = True,
) -> ComparisonReport:
    """Top-level orchestration shared by the CLI + API.

    Mirrors the resolution steps of
    :func:`scripts.walkforward_etf_rotation_strategy.run_walkforward`
    so universe / overrides / industry-signal loading stay consistent
    across CLIs.
    """

    prices = load_price_matrix(prices_csv)
    strategy_cfg = load_strategy_config(strategy_config_path)
    if strategy_config_overrides:
        strategy_cfg = _apply_strategy_overrides(strategy_cfg, strategy_config_overrides)

    holdings = [h for h in load_default_holdings() if h.code in prices.columns]
    if not holdings:
        rotation_config = build_strategy_config(load_default_holdings(), strategy_cfg)
    else:
        rotation_config = build_strategy_config(holdings, strategy_cfg)

    industry_signals: dict[str, dict[str, Any]] = {}
    etf_industry_map: dict[str, str] = dict(strategy_cfg.etf_industry_map)
    if enable_policy_signal:
        loaded, _ = load_policy_industry_signals()
        industry_signals = dict(loaded)

    all_specs = build_default_strategy_specs(
        rotation_config, blend_regime=blend_regime,
    )
    chosen = [all_specs[label] for label in strategy_labels if label in all_specs]

    comparator = StrategyComparator(
        strategies=chosen,
        price_history=prices,
        period_start=period_start,
        period_end=period_end,
        industry_signals=industry_signals or None,
        etf_industry_map=etf_industry_map or None,
        rebalance_freq_days=rebalance_freq_days,
        initial_capital=initial_capital,
        tc_model=tc_model,
        compute_statistical_tests=compute_statistical_tests,
        statistical_alpha=statistical_alpha,
        statistical_block_size=statistical_block_size,
        statistical_n_bootstrap=statistical_n_bootstrap,
        statistical_include_buy_hold=statistical_include_buy_hold,
    )
    return comparator.run()


def _apply_strategy_overrides(
    cfg: StrategyConfig,
    overrides: dict[str, Any],
) -> StrategyConfig:
    """Shallow-merge user overrides into the resolved StrategyConfig."""

    new_strategy = {**cfg.strategy, **overrides}
    return replace(cfg, strategy=new_strategy)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run multiple ETF strategies on the same window and compare "
            "their performance, regime fit, and pairwise spreads."
        ),
    )
    parser.add_argument("--prices-csv", required=True, type=Path)
    parser.add_argument(
        "--period-start",
        required=True,
        help="Comparison window start, ISO date, inclusive.",
    )
    parser.add_argument(
        "--period-end",
        required=True,
        help="Comparison window end, ISO date, inclusive.",
    )
    parser.add_argument(
        "--strategies",
        default=",".join(DEFAULT_STRATEGY_LABELS),
        help=(
            "Comma-separated list of strategy labels to compare. "
            f"Default: all three ({','.join(DEFAULT_STRATEGY_LABELS)})."
        ),
    )
    parser.add_argument(
        "--enable-policy-signal",
        action="store_true",
        help=(
            "Enable policy_signal_factor for the rotation strategy + blend "
            "trend leg (mean-reversion ignores it by contract)."
        ),
    )
    parser.add_argument(
        "--blend-regime",
        default="unknown",
        choices=("bull", "correction", "sideways", "bear", "crisis", "unknown"),
        help="Regime label fed to EtfStrategyBlend (alpha lookup).",
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
        help="Rebalance cadence in business days. Default 5 (~weekly).",
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
            "Enable transaction-cost modelling for every strategy "
            "(defaults reflect CN ETF retail brokerage)."
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
    parser.add_argument(
        "--with-statistical-tests",
        action="store_true",
        help=(
            "Compute formal pairwise hypothesis tests (Diebold-Mariano, "
            "Politis-Romano block bootstrap, Memmel Sharpe-difference) plus "
            "Bonferroni / Holm multiple-testing corrections."
        ),
    )
    parser.add_argument(
        "--statistical-alpha",
        type=float,
        default=0.05,
        help="Significance level for multiple-testing rejection flags.",
    )
    parser.add_argument(
        "--statistical-block-size",
        type=int,
        default=10,
        help="Block size for the Politis-Romano circular block bootstrap.",
    )
    parser.add_argument(
        "--statistical-n-bootstrap",
        type=int,
        default=1000,
        help="Number of bootstrap replicates for block bootstrap.",
    )
    parser.add_argument(
        "--statistical-no-buy-hold",
        action="store_true",
        help=(
            "Skip including equal-weight buy-and-hold in the pairwise grid "
            "(default: include, so you get strategy-vs-passive p-values)."
        ),
    )
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

    try:
        strategy_labels = _parse_strategy_list(args.strategies)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report = run_comparison(
        args.prices_csv,
        period_start=args.period_start,
        period_end=args.period_end,
        strategy_labels=strategy_labels,
        enable_policy_signal=args.enable_policy_signal,
        rebalance_freq_days=args.rebalance_freq_days,
        initial_capital=args.initial_capital,
        strategy_config_path=args.strategy_config,
        blend_regime=args.blend_regime,
        tc_model=_build_tc_model_from_args(args),
        compute_statistical_tests=args.with_statistical_tests,
        statistical_alpha=args.statistical_alpha,
        statistical_block_size=args.statistical_block_size,
        statistical_n_bootstrap=args.statistical_n_bootstrap,
        statistical_include_buy_hold=not args.statistical_no_buy_hold,
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
        args.output_md.write_text(
            render_comparison_markdown(report), encoding="utf-8",
        )

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
