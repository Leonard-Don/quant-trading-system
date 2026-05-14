#!/usr/bin/env python3
"""Backtest the ETF rotation strategy from a local CSV price matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.daily_etf_signal import build_strategy_config, load_default_holdings  # noqa: E402
from src.backtest.portfolio_backtester import PortfolioBacktester  # noqa: E402
from src.strategy.etf_rotation_strategy import EtfRotationStrategy  # noqa: E402


def load_price_matrix(prices_csv: str | Path) -> pd.DataFrame:
    """Load a CSV whose first column is date/index and remaining columns are ETF closes."""

    frame = pd.read_csv(prices_csv, index_col=0)
    frame.index = pd.to_datetime(frame.index)
    # Sort by date before ffill so missing prices inherit from earlier dates,
    # never from later ones — protects against descending-date CSV exports.
    return (
        frame.apply(pd.to_numeric, errors="coerce")
        .sort_index()
        .ffill()
        .dropna(how="all")
    )


def run_backtest(
    prices_csv: str | Path,
    *,
    initial_capital: float = 100_000.0,
    commission: float = 0.001,
    slippage: float = 0.001,
) -> Dict[str, Any]:
    """Run PortfolioBacktester with EtfRotationStrategy on a local price CSV."""

    price_matrix = load_price_matrix(prices_csv)
    holdings = [holding for holding in load_default_holdings() if holding.code in price_matrix.columns]
    if not holdings:
        return {}

    strategy = EtfRotationStrategy(build_strategy_config(holdings))
    backtester = PortfolioBacktester(
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
        allow_fractional_shares=False,
        max_gross_exposure=0.90,
        min_rebalance_weight_delta=0.01,
    )
    return backtester.run(strategy, price_matrix)


def _summarize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Keep CLI JSON compact while preserving key metrics."""

    if not result:
        return {}
    keys = [
        "initial_capital",
        "final_value",
        "total_return",
        "annualized_return",
        "max_drawdown",
        "sharpe_ratio",
        "num_trades",
        "assets",
        "execution_costs",
    ]
    return {key: result[key] for key in keys if key in result}


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backtest the manual ETF rotation target-weight strategy from a local CSV."
    )
    parser.add_argument("--prices-csv", required=True, help="CSV price matrix with date index.")
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--commission", type=float, default=0.001)
    parser.add_argument("--slippage", type=float, default=0.001)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    result = run_backtest(
        args.prices_csv,
        initial_capital=args.initial_capital,
        commission=args.commission,
        slippage=args.slippage,
    )
    print(json.dumps(_summarize_result(result), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
