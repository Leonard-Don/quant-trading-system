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
from collections.abc import Iterable, Sequence
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

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

EXECUTION_CONTRACT: dict[str, Any] = {
    "mode": "manual_only",
    "not_auto_ordering": True,
    "broker_api_calls": False,
    "review_required": True,
}


# ---------------------------------------------------------------------------
# Grid expansion
# ---------------------------------------------------------------------------


def load_grid(path: Path) -> dict[str, list[Any]]:
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

    normalised: dict[str, list[Any]] = {}
    for key, value in payload.items():
        if not isinstance(value, list):
            raise ValueError(f"Grid field {key!r} must map to a list of candidate values")
        normalised[key] = value
    return normalised


def expand_grid(grid: dict[str, list[Any]]) -> list[EtfScoringConfig]:
    """Cartesian-expand the grid into a list of concrete scoring configs."""

    if not grid:
        return [EtfScoringConfig()]
    keys = list(grid.keys())
    combos: list[EtfScoringConfig] = []
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
) -> Iterable[tuple[pd.DatetimeIndex, pd.DatetimeIndex]]:
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
#
# Faithful walk-forward semantics: the strategy must see the *full* price
# history so its warmup window (``warmup_days``, 60 by default) is
# satisfied, and the IS/OOS window is sliced out of the produced weights
# AFTER ``generate_signals``. Running ``generate_signals`` directly on a
# bare window starves the strategy — with warmup_days=60 and a 63-bar
# test slice only ~3 bars get live signals — so the reported metrics are
# not a faithful read of the window. This mirrors the correct behaviour
# in ``src/backtest/etf_rotation_walkforward.py`` (slice after signals).
# ---------------------------------------------------------------------------


class _PrecomputedSignalStrategy:
    """Adapter that replays a pre-computed full-history weight frame.

    ``PortfolioBacktester.run`` calls ``strategy.generate_signals(window)``
    itself. To slice the test window *after* signal generation we compute
    the weights once on the whole price history and wrap them here: each
    ``generate_signals`` call returns the rows of the precomputed frame
    that line up with the window the backtester is executing.
    """

    def __init__(self, full_weights: pd.DataFrame) -> None:
        self._full_weights = full_weights

    def generate_signals(self, price_matrix: pd.DataFrame) -> pd.DataFrame:
        # Reindex onto the executed window's index/columns; bars outside
        # the precomputed frame (shouldn't happen) default to zero weight.
        sliced = self._full_weights.reindex(
            index=price_matrix.index,
            columns=price_matrix.columns,
        )
        return sliced.fillna(0.0)


def _full_history_weights(
    prices: pd.DataFrame,
    scoring: EtfScoringConfig,
) -> Optional[pd.DataFrame]:
    """Run ``EtfRotationStrategy`` on the FULL price history once.

    Returns the target-weight frame for every bar (warmup bars included,
    those are zero). ``None`` when no seed holding overlaps the price
    columns. The caller slices IS/OOS windows out of this frame.
    """

    holdings = [h for h in load_default_holdings() if h.code in prices.columns]
    if not holdings:
        return None
    base_config = build_strategy_config(holdings)
    config = replace(base_config, scoring=scoring)
    strategy = EtfRotationStrategy(config)
    return strategy.generate_signals(prices)


def _run_window(
    window_prices: pd.DataFrame,
    full_weights: pd.DataFrame,
    *,
    initial_capital: float,
    commission: float,
    slippage: float,
    min_rebalance_weight_delta: float,
) -> Optional[dict[str, Any]]:
    """Backtest one IS/OOS window using pre-computed full-history weights.

    ``window_prices`` is the slice the backtester executes on;
    ``full_weights`` is the strategy output over the *entire* history, so
    the window's weights are already fully warmed.
    """

    if window_prices.empty:
        return None
    backtester = PortfolioBacktester(
        initial_capital=initial_capital,
        commission=commission,
        slippage=slippage,
        allow_fractional_shares=False,
        max_gross_exposure=0.90,
        min_rebalance_weight_delta=min_rebalance_weight_delta,
    )
    result = backtester.run(
        _PrecomputedSignalStrategy(full_weights), window_prices
    )
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
) -> dict[str, Any]:
    """Evaluate every config IS, pick the best, then evaluate it OOS.

    Both legs run the strategy on the full ``prices`` history (so its
    warmup is satisfied) and slice the IS/OOS window out of the produced
    weights — the test window is never starved of warmup.
    """

    train_prices = prices.loc[train_index]
    test_prices = prices.loc[test_index]

    in_sample: list[dict[str, Any]] = []
    # Cache the full-history weights per config so the OOS leg reuses the
    # IS leg's computation instead of re-running generate_signals.
    full_weights_by_config: dict[int, pd.DataFrame] = {}
    for idx, config in enumerate(configs):
        full_weights = _full_history_weights(prices, config)
        if full_weights is None:
            continue
        full_weights_by_config[idx] = full_weights
        metrics = _run_window(
            train_prices,
            full_weights,
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
    oos_metrics = _run_window(
        test_prices,
        full_weights_by_config[best["config_index"]],
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


def load_price_matrix(prices_csv: Path) -> pd.DataFrame:
    """Load a wide ETF close-price CSV with a DatetimeIndex."""

    prices = pd.read_csv(prices_csv, index_col=0)
    prices.index = pd.to_datetime(prices.index)
    return prices.apply(pd.to_numeric, errors="coerce").ffill().dropna(how="all")


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
) -> dict[str, Any]:
    prices = load_price_matrix(prices_csv)

    grid = load_grid(grid_path) if grid_path is not None else {}
    configs = expand_grid(grid)
    logger.info("walk-forward: %d configs × windows", len(configs))

    windows: list[dict[str, Any]] = []
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

    oos_values: list[float] = []
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
        "execution_contract": dict(EXECUTION_CONTRACT),
        "configs": [asdict(c) for c in configs],
        "windows": windows,
    }


# ---------------------------------------------------------------------------
# Credibility report helpers
# ---------------------------------------------------------------------------


def _mean(values: Sequence[float]) -> Optional[float]:
    return (sum(values) / len(values)) if values else None


def _fmt_pct(value: Optional[float], *, signed: bool = True) -> str:
    if value is None:
        return "n/a"
    fmt = "+.2f" if signed else ".2f"
    return f"{value * 100:{fmt}}%"


def _fmt_num(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _equal_weight_buy_hold_return(
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> Optional[float]:
    """Naive equal-weight buy-and-hold return for one OOS window."""

    window = prices.loc[pd.Timestamp(start_date): pd.Timestamp(end_date)]
    if len(window) < 2:
        return None
    complete = window.dropna(axis=1, how="any")
    if complete.empty:
        return None
    first = complete.iloc[0].replace(0, pd.NA)
    rel = complete.iloc[-1] / first - 1.0
    rel = pd.to_numeric(rel, errors="coerce").dropna()
    if rel.empty:
        return None
    return float(rel.mean())


def build_credibility_summary(
    result: dict[str, Any],
    prices: pd.DataFrame,
) -> dict[str, Any]:
    """Summarize whether OOS walk-forward windows beat a naive benchmark."""

    returns: list[float] = []
    sharpes: list[float] = []
    drawdowns: list[float] = []
    trades: list[float] = []
    benchmark_returns: list[float] = []
    excess_returns: list[float] = []
    wins = 0
    comparable = 0

    for window in result.get("windows", []):
        oos = window.get("out_of_sample") or {}
        if not oos:
            continue
        ret = oos.get("total_return")
        if ret is not None:
            returns.append(float(ret))
        if oos.get("sharpe_ratio") is not None:
            sharpes.append(float(oos["sharpe_ratio"]))
        if oos.get("max_drawdown") is not None:
            drawdowns.append(float(oos["max_drawdown"]))
        if oos.get("num_trades") is not None:
            trades.append(float(oos["num_trades"]))

        test_range = window.get("test_range") or []
        if len(test_range) == 2 and ret is not None:
            benchmark = _equal_weight_buy_hold_return(prices, test_range[0], test_range[1])
            if benchmark is not None:
                comparable += 1
                benchmark_returns.append(benchmark)
                excess = float(ret) - benchmark
                excess_returns.append(excess)
                if excess > 0:
                    wins += 1

    win_rate = (wins / comparable) if comparable else None
    mean_excess = _mean(excess_returns)
    mean_return = _mean(returns)
    mean_sharpe = _mean(sharpes)

    if (
        win_rate is not None
        and win_rate >= 0.6
        and (mean_excess or 0.0) > 0
        and (mean_sharpe or 0.0) > 0
    ):
        verdict = "credible_watchlist"
    elif (win_rate is not None and win_rate >= 0.4) or (mean_return or 0.0) > 0:
        verdict = "mixed_watchlist"
    else:
        verdict = "not_credible"

    return {
        "benchmark_name": "equal_weight_buy_hold",
        "num_windows": int(
            result.get("summary", {}).get("num_windows", len(result.get("windows", [])))
        ),
        "comparable_windows": comparable,
        "oos_positive_windows": sum(1 for value in returns if value > 0),
        "oos_win_count_vs_benchmark": wins,
        "oos_win_rate_vs_benchmark": win_rate,
        "mean_oos_return": mean_return,
        "mean_benchmark_return": _mean(benchmark_returns),
        "mean_oos_excess_return": mean_excess,
        "min_oos_return": min(returns) if returns else None,
        "max_oos_return": max(returns) if returns else None,
        "mean_oos_sharpe": mean_sharpe,
        "mean_oos_max_drawdown": _mean(drawdowns),
        "worst_oos_drawdown": max(drawdowns) if drawdowns else None,
        "avg_trades_per_window": _mean(trades),
        "verdict": verdict,
    }


def render_walkforward_report(
    result: dict[str, Any],
    prices: pd.DataFrame,
    *,
    source_label: str,
    generated_at: Optional[str] = None,
) -> str:
    """Render a self-contained Markdown credibility report."""

    generated_at = generated_at or datetime.now().strftime("%Y-%m-%d")
    summary = build_credibility_summary(result, prices)
    lines = [
        "# ETF Rotation Walk-Forward Credibility Report",
        "",
        f"- Generated: `{generated_at}`",
        f"- Price source: `{source_label}`",
        f"- Windows: {summary['num_windows']} ({summary['comparable_windows']} comparable vs benchmark)",
        f"- Benchmark: `{summary['benchmark_name']}`",
        f"- Verdict: **{summary['verdict']}**",
        "- Execution contract: manual-only; not auto-ordering; no broker API calls.",
        "",
        "## Headline",
        "",
        f"- Mean OOS return: {_fmt_pct(summary['mean_oos_return'])}",
        f"- Mean benchmark return: {_fmt_pct(summary['mean_benchmark_return'])}",
        f"- Mean OOS excess return: {_fmt_pct(summary['mean_oos_excess_return'])}",
        f"- Win rate vs benchmark: {_fmt_pct(summary['oos_win_rate_vs_benchmark'], signed=False)}",
        f"- Mean OOS Sharpe: {_fmt_num(summary['mean_oos_sharpe'])}",
        f"- Worst OOS drawdown: {_fmt_pct(summary['worst_oos_drawdown'], signed=False)}",
        f"- Avg trades/window: {_fmt_num(summary['avg_trades_per_window'])}",
        "",
        "## Window Detail",
        "",
        "| Test window | Strategy return | Benchmark return | Excess | Sharpe | Max DD | Trades |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for window in result.get("windows", []):
        oos = window.get("out_of_sample") or {}
        test_range = window.get("test_range") or ["n/a", "n/a"]
        benchmark = None
        if len(test_range) == 2:
            benchmark = _equal_weight_buy_hold_return(prices, test_range[0], test_range[1])
        strategy_return = oos.get("total_return")
        excess = (
            float(strategy_return) - benchmark
            if strategy_return is not None and benchmark is not None
            else None
        )
        lines.append(
            "| {start} → {end} | {ret} | {bench} | {excess} | {sharpe} | {dd} | {trades} |".format(
                start=test_range[0],
                end=test_range[1],
                ret=_fmt_pct(strategy_return),
                bench=_fmt_pct(benchmark),
                excess=_fmt_pct(excess),
                sharpe=_fmt_num(oos.get("sharpe_ratio")),
                dd=_fmt_pct(oos.get("max_drawdown"), signed=False),
                trades=oos.get("num_trades", "n/a"),
            )
        )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "Treat `credible_watchlist` as permission to keep manually tracking the signal, not as evidence of production edge. `mixed_watchlist` means the strategy has some useful regimes but needs sizing discipline and continued audit. `not_credible` means the default scoring layer should not guide real allocation without redesign.",
        "",
        "## Caveats",
        "",
        "- Equal-weight buy-and-hold is a naive benchmark, not Leonard's exact executed portfolio.",
        "- Walk-forward windows are historical and do not include future liquidity, premium/discount, tax, or execution constraints beyond the configured commission/slippage parameters.",
        "- This report evaluates the scoring/backtest layer; live decisions must still use the manual trade plan, premium vetoes, and risk rules.",
        "- Manual-only remains a hard contract: this project produces suggestions, not orders.",
        "",
    ])
    return "\n".join(lines)


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
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write the JSON walk-forward payload.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="Optional path to write a Markdown credibility report.",
    )
    parser.add_argument(
        "--source-label",
        default="price CSV",
        help="Human-readable price source label for the Markdown report.",
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
    prices = load_price_matrix(args.prices_csv)
    result["credibility"] = build_credibility_summary(result, prices)

    payload = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

    if args.output_md is not None:
        report = render_walkforward_report(
            result,
            prices,
            source_label=args.source_label,
        )
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
