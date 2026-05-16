#!/usr/bin/env python3
"""One-off parameter sweep over the full-pipeline backtest.

Runs ``FullPipelineStrategy`` with a grid of strategy.json overrides and
prints a tidy comparison table. The goal is to ground my recommendations
in actual numbers rather than intuition.

Argparse mirrors the pattern in ``scripts/full_pipeline_backtest.py`` so
the sweep can be re-pointed at different price CSVs / sweep grids without
editing source. All flags default to the values the script previously
hardcoded — existing invocations continue to work.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Iterable, Sequence
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.full_pipeline_backtest import FullPipelineStrategy, load_price_matrix
from src.backtest.portfolio_backtester import PortfolioBacktester
from src.strategy.etf_rotation_config_loader import load_strategy_config

# Legacy module-level default — kept so monkeypatching it from tests still
# works (some existing tests patch ``strategy_param_scan.PRICES`` directly).
PRICES = "data/etf_backtest/etf_prices_4y.csv"

# Default sweep grids — match the historical hardcoded ranges so callers
# without flags get the same 12-cell table as before.
DEFAULT_MIN_SCORES: tuple[float, ...] = (15.0, 20.0, 25.0, 30.0, 35.0)
DEFAULT_REBALANCE_DELTAS: tuple[float, ...] = (0.03, 0.05, 0.07, 0.10, 0.15)


def _override_config(base_cfg, **overrides):
    """Return a StrategyConfig with the supplied strategy / ensemble overrides."""

    new_strategy = dict(base_cfg.strategy)
    new_ensemble = dict(base_cfg.ensemble)
    for key, value in overrides.items():
        if key.startswith("ensemble."):
            new_ensemble[key.split(".", 1)[1]] = value
        else:
            new_strategy[key] = value
    return dc_replace(base_cfg, strategy=new_strategy, ensemble=new_ensemble)


def _run(label, base_cfg, *, mode, rebalance_delta=0.03, prices_csv=None, **overrides):
    cfg = _override_config(base_cfg, **overrides)
    prices = load_price_matrix(prices_csv if prices_csv is not None else PRICES)
    strategy = FullPipelineStrategy(strategy_config=cfg, mode=mode, lag_days=1)
    backtester = PortfolioBacktester(
        initial_capital=100_000.0,
        commission=0.001,
        slippage=0.001,
        allow_fractional_shares=False,
        max_gross_exposure=0.95,
        min_rebalance_weight_delta=rebalance_delta,
    )
    result = backtester.run(strategy, prices)
    if not result:
        return None
    return {
        "label": label,
        "mode": mode,
        "rebalance_delta": rebalance_delta,
        "overrides": overrides,
        "total_return": result["total_return"],
        "annualized": result.get("annualized_return", 0.0),
        "max_drawdown": result.get("max_drawdown", 0.0),
        "sharpe": result.get("sharpe_ratio", 0.0),
        "num_trades": result["num_trades"],
        "slippage": result["execution_costs"].get("estimated_total_slippage_cost", 0.0),
    }


def _parse_float_list(raw: str) -> tuple[float, ...]:
    """Parse a comma-separated list of floats for a sweep dimension."""
    if not raw.strip():
        raise argparse.ArgumentTypeError("sweep list cannot be empty")
    try:
        return tuple(float(p.strip()) for p in raw.split(",") if p.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid float in sweep list: {raw!r}") from exc


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Parameter sweep harness for the full-pipeline ETF rotation "
            "backtest. Sweeps min_score_to_hold and rebalance_delta, plus "
            "regime-only and ensemble-on sanity rows. All defaults match "
            "the legacy hardcoded sweep so existing invocations remain "
            "behaviour-compatible."
        ),
    )
    parser.add_argument(
        "--prices-csv",
        default=PRICES,
        help=(
            "Path to the price-matrix CSV (default: %(default)s). Must be "
            "indexable by date and contain at least the default 5-ETF seed."
        ),
    )
    parser.add_argument(
        "--min-scores",
        type=_parse_float_list,
        default=DEFAULT_MIN_SCORES,
        metavar="V1,V2,...",
        help=(
            "Comma-separated min_score_to_hold values to sweep "
            "(default: %s). min_score_full_hold is set to value+10 for "
            "each cell." % ",".join(str(v) for v in DEFAULT_MIN_SCORES)
        ),
    )
    parser.add_argument(
        "--rebalance-deltas",
        type=_parse_float_list,
        default=DEFAULT_REBALANCE_DELTAS,
        metavar="V1,V2,...",
        help=(
            "Comma-separated rebalance_delta values to sweep "
            "(default: %s)." % ",".join(str(v) for v in DEFAULT_REBALANCE_DELTAS)
        ),
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help=(
            "Optional path for a machine-readable CSV dump of the sweep "
            "results. The pretty-print table is always emitted on stdout."
        ),
    )
    return parser


def _build_sweep(
    base,
    *,
    min_scores: Sequence[float],
    rebalance_deltas: Sequence[float],
    prices_csv: str,
) -> list[dict[str, Any] | None]:
    """Run the full sweep grid and return rows (None entries on failure)."""

    runs: list[dict[str, Any] | None] = []

    # Sweep min_score_to_hold to test the recommendation
    for score in min_scores:
        full_hold = score + 10  # keep gap
        runs.append(_run(
            f"trend|min_score={score:g}",
            base, mode="trend", prices_csv=prices_csv,
            min_score_to_hold=score,
            min_score_full_hold=full_hold,
        ))

    # Sweep rebalance_delta (was the friction story right?)
    for rd in rebalance_deltas:
        runs.append(_run(
            f"trend|rebalance_delta={rd:g}",
            base, mode="trend", rebalance_delta=rd, prices_csv=prices_csv,
        ))

    # Compare with regime ON, ensemble OFF
    runs.append(_run("regime_only", base, mode="regime", prices_csv=prices_csv))

    # Final sanity: ensemble ON
    base_ens = dc_replace(
        base,
        ensemble={**dict(base.ensemble), "enabled": True},
    )
    runs.append(_run("ensemble_on", base_ens, mode="ensemble", prices_csv=prices_csv))
    return runs


def _write_results_csv(runs: list[dict[str, Any] | None], output_csv: Path) -> None:
    """Emit successful sweep rows to a CSV for downstream tooling."""
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "label", "mode", "rebalance_delta", "total_return", "annualized",
        "max_drawdown", "sharpe", "num_trades", "slippage",
    ]
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in runs:
            if row is None:
                continue
            writer.writerow({k: row.get(k) for k in fieldnames})


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)

    base = load_strategy_config()
    # Ensure ensemble is OFF for clean comparison of trend-only variants;
    # we'll re-test ensemble explicitly at the end.
    base = dc_replace(
        base,
        ensemble={**dict(base.ensemble), "enabled": False},
    )

    runs = _build_sweep(
        base,
        min_scores=args.min_scores,
        rebalance_deltas=args.rebalance_deltas,
        prices_csv=args.prices_csv,
    )

    # Pretty print
    print(f"{'label':<35} {'return':>8} {'ann':>7} {'maxDD':>8} {'sharpe':>7} {'trades':>7} {'slipp':>8}")
    print("-" * 90)
    for r in runs:
        if r is None:
            continue
        print(
            f"{r['label']:<35} "
            f"{r['total_return']*100:>7.2f}% "
            f"{r['annualized']*100:>6.2f}% "
            f"{r['max_drawdown']*100:>7.2f}% "
            f"{r['sharpe']:>7.3f} "
            f"{r['num_trades']:>7d} "
            f"¥{r['slippage']:>7,.0f}"
        )

    if args.output_csv is not None:
        _write_results_csv(runs, args.output_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
