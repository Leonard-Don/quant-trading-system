#!/usr/bin/env python3
"""One-off parameter sweep over the full-pipeline backtest.

Runs ``FullPipelineStrategy`` with a grid of strategy.json overrides and
prints a tidy comparison table. The goal is to ground my recommendations
in actual numbers rather than intuition.
"""

from __future__ import annotations

import sys
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.full_pipeline_backtest import FullPipelineStrategy, load_price_matrix
from src.backtest.portfolio_backtester import PortfolioBacktester
from src.strategy.etf_rotation_config_loader import load_strategy_config

PRICES = "data/etf_backtest/etf_prices_4y.csv"


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


def _run(label, base_cfg, *, mode, rebalance_delta=0.03, **overrides):
    cfg = _override_config(base_cfg, **overrides)
    prices = load_price_matrix(PRICES)
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


def main() -> int:
    base = load_strategy_config()
    # Ensure ensemble is OFF for clean comparison of trend-only variants;
    # we'll re-test ensemble explicitly at the end.
    base = dc_replace(
        base,
        ensemble={**dict(base.ensemble), "enabled": False},
    )

    runs: List[Dict[str, Any]] = []

    # Sweep min_score_to_hold to test my recommendation
    for score in (15, 20, 25, 30, 35):
        full_hold = score + 10  # keep gap
        runs.append(_run(
            f"trend|min_score={score}",
            base, mode="trend",
            min_score_to_hold=score,
            min_score_full_hold=full_hold,
        ))

    # Sweep rebalance_delta (was the friction story right?)
    for rd in (0.03, 0.05, 0.07, 0.10, 0.15):
        runs.append(_run(
            f"trend|rebalance_delta={rd}",
            base, mode="trend", rebalance_delta=rd,
        ))

    # Test enabling commodity overweight (path A from recommendations)
    # — does raising max_weight on the winners help?
    # We can't override per-asset caps via strategy config dict easily
    # without rebuilding the universe; skip for this scan.

    # Compare with regime ON, ensemble OFF
    runs.append(_run("regime_only", base, mode="regime"))

    # Final sanity: ensemble ON
    base_ens = dc_replace(
        base,
        ensemble={**dict(base.ensemble), "enabled": True},
    )
    runs.append(_run("ensemble_on", base_ens, mode="ensemble"))

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
