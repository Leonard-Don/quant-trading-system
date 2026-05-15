#!/usr/bin/env python3
"""Walk-forward parameter scan for the ETF rotation strategy.

Walk-forward exposes the gap between *in-sample* (IS) parameter fit and
*out-of-sample* (OOS) realised performance. The script:

1. Splits a price CSV into consecutive ``(train, test)`` windows
   (``--train-days`` / ``--test-days``).
2. For each window, evaluates every ``EtfScoringConfig`` in the grid on
   the train slice and records the IS Sharpe.
3. Picks the best IS config and re-evaluates it on the test slice — that
   OOS Sharpe is the honest performance estimate.
4. Reports per-window IS vs OOS, plus an aggregate "OOS-mean Sharpe by
   config" so you can see which constants survive across regimes.

The grid format is a JSON file mapping ``EtfScoringConfig`` field names
to a list of candidate values. Missing fields default to the production
``EtfScoringConfig`` constants. Example grid lives at
``scripts/etf_scoring_grid.example.json``.
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.daily_etf_signal import build_strategy_config, load_default_holdings  # noqa: E402
from src.backtest.portfolio_backtester import PortfolioBacktester  # noqa: E402
from src.strategy.etf_rotation_strategy import (  # noqa: E402
    DEFAULT_REBALANCE_THRESHOLD,
    EtfRotationStrategy,
    EtfScoringConfig,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Grid expansion
# ---------------------------------------------------------------------------


def load_grid(path: Path) -> Dict[str, List[Any]]:
    """Load a JSON grid file; raise ``ValueError`` if a field is unknown.

    Keys starting with ``_`` are ignored so grid files can carry inline
    comments (``"_comment"``) without choking the loader.
    """

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("grid file must be a JSON object")

    payload = {k: v for k, v in payload.items() if not k.startswith("_")}
    allowed = {f.name for f in EtfScoringConfig.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"Unknown EtfScoringConfig fields in grid: {sorted(unknown)}")

    normalised: Dict[str, List[Any]] = {}
    for key, value in payload.items():
        if not isinstance(value, list):
            raise ValueError(f"Grid field {key!r} must map to a list of candidate values")
        normalised[key] = value
    return normalised


def expand_grid(grid: Dict[str, List[Any]]) -> List[EtfScoringConfig]:
    """Cartesian-expand the grid into a list of concrete scoring configs."""

    if not grid:
        return [EtfScoringConfig()]
    keys = list(grid.keys())
    combos: List[EtfScoringConfig] = []
    for values in itertools.product(*(grid[key] for key in keys)):
        kwargs = dict(zip(keys, values))
        combos.append(replace(EtfScoringConfig(), **kwargs))
    return combos


# ---------------------------------------------------------------------------
# Walk-forward windows
# ---------------------------------------------------------------------------


def iter_windows(
    index: pd.DatetimeIndex,
    train_days: int,
    test_days: int,
    *,
    step_days: Optional[int] = None,
    min_train_days: Optional[int] = None,
) -> Iterable[Tuple[pd.DatetimeIndex, pd.DatetimeIndex]]:
    """Yield consecutive ``(train_index, test_index)`` slices.

    Default ``step_days`` equals ``test_days`` so windows are non-overlapping
    in the test slice (anchored walk-forward). Set ``step_days < test_days``
    for overlapping evaluation.
    """

    if train_days <= 0 or test_days <= 0:
        raise ValueError("train_days and test_days must be > 0")
    step = step_days or test_days
    min_train = min_train_days or train_days
    start = 0
    n = len(index)
    while True:
        train_end = start + train_days
        test_end = train_end + test_days
        if test_end > n:
            return
        train_slice = index[max(0, train_end - train_days): train_end]
        test_slice = index[train_end: test_end]
        if len(train_slice) >= min_train and len(test_slice) >= test_days:
            yield train_slice, test_slice
        start += step


# ---------------------------------------------------------------------------
# Per-window evaluation
# ---------------------------------------------------------------------------


def _run_one(
    price_matrix: pd.DataFrame,
    scoring: EtfScoringConfig,
    *,
    initial_capital: float,
    commission: float,
    slippage: float,
    min_rebalance_weight_delta: float,
) -> Optional[Dict[str, Any]]:
    holdings = [h for h in load_default_holdings() if h.code in price_matrix.columns]
    if not holdings:
        return None
    base_config = build_strategy_config(holdings)
    config = replace(base_config, scoring=scoring)
    strategy = EtfRotationStrategy(config)
    backtester = PortfolioBacktester(
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
        allow_fractional_shares=False,
        max_gross_exposure=0.90,
        min_rebalance_weight_delta=min_rebalance_weight_delta,
    )
    result = backtester.run(strategy, price_matrix)
    if not result:
        return None
    return {
        "final_value": float(result.get("final_value", 0.0)),
        "total_return": float(result.get("total_return", 0.0)),
        "annualized_return": float(result.get("annualized_return", 0.0)),
        "max_drawdown": float(result.get("max_drawdown", 0.0)),
        "sharpe_ratio": float(result.get("sharpe_ratio", 0.0)),
        "num_trades": int(result.get("num_trades", 0)),
    }


def evaluate_window(
    prices: pd.DataFrame,
    train_index: pd.DatetimeIndex,
    test_index: pd.DatetimeIndex,
    configs: Sequence[EtfScoringConfig],
    *,
    initial_capital: float,
    commission: float,
    slippage: float,
    min_rebalance_weight_delta: float,
    objective: str = "sharpe_ratio",
) -> Dict[str, Any]:
    """Evaluate every config IS, pick the best, then evaluate it OOS."""

    train_prices = prices.loc[train_index]
    test_prices = prices.loc[test_index]

    in_sample: List[Dict[str, Any]] = []
    for idx, config in enumerate(configs):
        metrics = _run_one(
            train_prices,
            config,
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
            min_rebalance_weight_delta=min_rebalance_weight_delta,
        )
        if metrics is None:
            continue
        in_sample.append({
            "config_index": idx,
            "metrics": metrics,
            "objective": metrics.get(objective, 0.0),
        })

    if not in_sample:
        return {
            "train_range": [str(train_index[0].date()), str(train_index[-1].date())],
            "test_range": [str(test_index[0].date()), str(test_index[-1].date())],
            "best_config_index": None,
            "in_sample": [],
            "out_of_sample": None,
        }

    best = max(in_sample, key=lambda row: row["objective"])
    oos_metrics = _run_one(
        test_prices,
        configs[best["config_index"]],
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
        min_rebalance_weight_delta=min_rebalance_weight_delta,
    )
    return {
        "train_range": [str(train_index[0].date()), str(train_index[-1].date())],
        "test_range": [str(test_index[0].date()), str(test_index[-1].date())],
        "best_config_index": best["config_index"],
        "in_sample_objective": best["objective"],
        "out_of_sample": oos_metrics,
    }


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def run_walkforward(
    prices_csv: Path,
    grid_path: Optional[Path],
    *,
    train_days: int = 504,
    test_days: int = 63,
    step_days: Optional[int] = None,
    initial_capital: float = 100_000.0,
    commission: float = 0.001,
    slippage: float = 0.001,
    min_rebalance_weight_delta: float = DEFAULT_REBALANCE_THRESHOLD,
    objective: str = "sharpe_ratio",
) -> Dict[str, Any]:
    prices = pd.read_csv(prices_csv, index_col=0)
    prices.index = pd.to_datetime(prices.index)
    prices = prices.apply(pd.to_numeric, errors="coerce").ffill().dropna(how="all")

    grid = load_grid(grid_path) if grid_path is not None else {}
    configs = expand_grid(grid)
    logger.info("walk-forward: %d configs × windows", len(configs))

    windows: List[Dict[str, Any]] = []
    for train_index, test_index in iter_windows(
        prices.index, train_days=train_days, test_days=test_days, step_days=step_days,
    ):
        windows.append(
            evaluate_window(
                prices,
                train_index,
                test_index,
                configs,
                initial_capital=initial_capital,
                commission=commission,
                slippage=slippage,
                min_rebalance_weight_delta=min_rebalance_weight_delta,
                objective=objective,
            )
        )

    oos_values: List[float] = []
    for window in windows:
        oos = window.get("out_of_sample") or {}
        value = oos.get(objective)
        if value is not None:
            oos_values.append(value)

    summary = {
        "objective": objective,
        "num_windows": len(windows),
        "oos_objective_mean": (sum(oos_values) / len(oos_values)) if oos_values else None,
        "oos_objective_min": min(oos_values) if oos_values else None,
        "oos_objective_max": max(oos_values) if oos_values else None,
    }
    return {
        "summary": summary,
        "configs": [asdict(c) for c in configs],
        "windows": windows,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Walk-forward parameter scan for EtfRotationStrategy.",
    )
    parser.add_argument("--prices-csv", required=True, type=Path)
    parser.add_argument(
        "--grid-json",
        type=Path,
        default=None,
        help="JSON grid mapping EtfScoringConfig fields to candidate lists.",
    )
    parser.add_argument("--train-days", type=int, default=504)
    parser.add_argument("--test-days", type=int, default=63)
    parser.add_argument("--step-days", type=int, default=None)
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--commission", type=float, default=0.001)
    parser.add_argument("--slippage", type=float, default=0.001)
    parser.add_argument(
        "--min-rebalance-weight-delta",
        type=float,
        default=DEFAULT_REBALANCE_THRESHOLD,
    )
    parser.add_argument(
        "--objective",
        choices=("sharpe_ratio", "annualized_return", "total_return"),
        default="sharpe_ratio",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _build_arg_parser().parse_args(argv)
    result = run_walkforward(
        args.prices_csv,
        args.grid_json,
        train_days=args.train_days,
        test_days=args.test_days,
        step_days=args.step_days,
        initial_capital=args.initial_capital,
        commission=args.commission,
        slippage=args.slippage,
        min_rebalance_weight_delta=args.min_rebalance_weight_delta,
        objective=args.objective,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
