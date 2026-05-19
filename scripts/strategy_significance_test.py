#!/usr/bin/env python3
"""Stand-alone CLI for the formal pairwise statistical tests.

Wraps :class:`StrategyComparator` with ``compute_statistical_tests=True``
and prints just the hypothesis-test block (DM + block bootstrap +
Sharpe difference + multi-testing correction) so paper / discussion
authors don't have to grep the JSON output of ``compare_strategies``.

Typical use::

    python scripts/strategy_significance_test.py \\
        --prices-csv data/etf_backtest/etf_prices_4y.csv \\
        --period-start 2024-01-01 \\
        --period-end 2025-04-30 \\
        --strategies rotation,mean_reversion,blend \\
        --alpha 0.05 \\
        --block-size 5 \\
        --n-bootstrap 1000

Outputs a terminal-friendly summary table and a JSON blob with the raw
test results so downstream tooling can ingest the same payload.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.compare_strategies import run_comparison  # noqa: E402
from src.backtest.etf_rotation_backtest import (  # noqa: E402
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_REBALANCE_FREQ_DAYS,
)
from src.backtest.strategy_comparison import (  # noqa: E402
    DEFAULT_STRATEGY_LABELS,
    ComparisonReport,
    StatisticalTestsReport,
)

logger = logging.getLogger(__name__)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute formal pairwise hypothesis tests "
            "(Diebold-Mariano, block bootstrap, Sharpe difference) on "
            "ETF strategies. H0 throughout: strategy A and B have the "
            "same expected return / Sharpe."
        ),
    )
    parser.add_argument("--prices-csv", required=True, type=Path)
    parser.add_argument("--period-start", required=True)
    parser.add_argument("--period-end", required=True)
    parser.add_argument(
        "--strategies",
        default=",".join(DEFAULT_STRATEGY_LABELS),
        help=f"Comma-separated subset of {','.join(DEFAULT_STRATEGY_LABELS)}.",
    )
    parser.add_argument(
        "--rebalance-freq-days",
        type=int,
        default=DEFAULT_REBALANCE_FREQ_DAYS,
    )
    parser.add_argument(
        "--initial-capital", type=float, default=DEFAULT_INITIAL_CAPITAL,
    )
    parser.add_argument("--strategy-config", type=Path, default=None)
    parser.add_argument(
        "--blend-regime",
        default="unknown",
        choices=("bull", "correction", "sideways", "bear", "crisis", "unknown"),
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Significance level for multiple-testing correction.",
    )
    parser.add_argument(
        "--block-size",
        type=int,
        default=10,
        help="Block size for the Politis-Romano circular block bootstrap.",
    )
    parser.add_argument(
        "--n-bootstrap",
        type=int,
        default=1000,
        help="Number of bootstrap replicates.",
    )
    parser.add_argument(
        "--no-buy-hold",
        action="store_true",
        help="Exclude buy-and-hold from the pairwise grid.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Dump the full statistical_tests block to this JSON path.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help=(
            "Optional Markdown summary path. Writes the terminal table plus "
            "a metadata header so the report can be checked into ``docs/``."
        ),
    )
    return parser


def _parse_strategy_list(raw: str) -> list[str]:
    if not raw:
        return list(DEFAULT_STRATEGY_LABELS)
    items = [s.strip() for s in raw.split(",") if s.strip()]
    unknown = [s for s in items if s not in DEFAULT_STRATEGY_LABELS]
    if unknown:
        raise ValueError(
            f"Unknown strategies {unknown!r}; valid: {list(DEFAULT_STRATEGY_LABELS)}"
        )
    deduped: list[str] = []
    for s in items:
        if s not in deduped:
            deduped.append(s)
    return deduped


def _render_summary(report: ComparisonReport) -> str:
    """One-screen terminal summary of the statistical tests block."""

    tests = report.statistical_tests
    if tests is None:
        return "(no statistical_tests block — comparator did not opt in)"
    lines: list[str] = []
    lines.append(
        f"Period: {report.period_start} → {report.period_end} · "
        f"pairs k={len(tests.pair_labels)} · α={tests.alpha:.3f}"
    )
    bonf_thr = tests.alpha / max(len(tests.pair_labels), 1)
    lines.append(f"Bonferroni threshold α/k = {bonf_thr:.5f}")
    lines.append("")
    lines.append(
        f"{'pair':<40}{'DM stat':>9}{'DM p':>9}{'Sharpe Δ':>11}"
        f"{'Sharpe p':>11}{'BS p':>9}{'Bonf':>6}{'Holm':>6}"
    )
    for i, pair in enumerate(tests.pair_labels):
        dm = tests.dm_results[i]
        sh = tests.sharpe_results[i]
        bs = tests.block_bootstrap_results[i]
        bonf_flag = "yes" if tests.bonferroni_dm.rejected[i] else "no"
        holm_flag = "yes" if tests.holm_dm.rejected[i] else "no"
        lines.append(
            f"{pair:<40}{dm.dm_statistic:>+9.3f}{dm.p_value:>9.4f}"
            f"{sh.sharpe_difference:>+11.4f}{sh.p_value:>11.4f}"
            f"{bs.p_value_two_sided:>9.4f}{bonf_flag:>6}{holm_flag:>6}"
        )
    lines.append("")
    lines.append("Notes:")
    for note in tests.notes:
        lines.append(f"  · {note}")
    return "\n".join(lines)


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
        rebalance_freq_days=args.rebalance_freq_days,
        initial_capital=args.initial_capital,
        strategy_config_path=args.strategy_config,
        blend_regime=args.blend_regime,
        compute_statistical_tests=True,
        statistical_alpha=args.alpha,
        statistical_block_size=args.block_size,
        statistical_n_bootstrap=args.n_bootstrap,
        statistical_include_buy_hold=not args.no_buy_hold,
    )

    if report.statistical_tests is None:
        print(
            "(insufficient observations to run pairwise tests — increase "
            "the period or rebalance more frequently)",
            file=sys.stderr,
        )
        return 1

    print(_render_summary(report))

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {
            "period_start": report.period_start,
            "period_end": report.period_end,
            "statistical_tests": _serialize_tests(report.statistical_tests),
        }
        args.output_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    if args.output_md is not None:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(_render_markdown(report), encoding="utf-8")
    return 0


def _serialize_tests(tests: StatisticalTestsReport) -> dict[str, object]:
    """Render the statistical_tests block as a JSON-clean dict."""

    return {
        "pair_labels": list(tests.pair_labels),
        "dm_results": [asdict(r) for r in tests.dm_results],
        "block_bootstrap_results": [
            asdict(r) for r in tests.block_bootstrap_results
        ],
        "sharpe_results": [asdict(r) for r in tests.sharpe_results],
        "bonferroni_dm": asdict(tests.bonferroni_dm),
        "bonferroni_sharpe": asdict(tests.bonferroni_sharpe),
        "holm_dm": asdict(tests.holm_dm),
        "holm_sharpe": asdict(tests.holm_sharpe),
        "alpha": tests.alpha,
        "notes": list(tests.notes),
    }


if __name__ == "__main__":
    raise SystemExit(main())
