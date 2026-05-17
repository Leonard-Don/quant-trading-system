#!/usr/bin/env python3
"""Classify the current market regime + print a strategy recommendation.

Wraps :class:`src.strategy.market_regime_classifier.MarketRegimeClassifier`
and :func:`src.strategy.strategy_recommender.recommend_strategy` so the
same code path the backend endpoint exposes can be driven from the
shell. Designed to answer:

* "Given today's prices, which strategy should I be running?"
* "Why? Show me the features the classifier looked at."
* "What's the recommended gross_cap override?"

Typical use::

    python scripts/recommend_strategy.py \
        --price-csv data/etf_backtest/etf_prices_4y.csv \
        --lookback-days 90 \
        --output-md output/regime_recommendation.md

Caveats
-------
* Regimes change slowly. The 90-day lookback is a *trailing* view and
  will miss inflection points by up to ~30 days. Use a shorter
  lookback (e.g. 45) if you want a more reactive read at the cost of
  more noise.
* The empirical anchor (commit ``a54b986``) is from the ``2024-01-01
  → 2025-04-30`` window. Out-of-sample regimes (esp. broad bear) are
  mapped on standard portfolio-risk practice, not in-sample
  evidence.
* Deterministic — no ML model. Same input → same output.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy.market_regime_classifier import (  # noqa: E402
    ClassifierConfig,
    MarketRegimeClassifier,
)
from src.strategy.strategy_recommender import (  # noqa: E402
    StrategyRecommendation,
    recommend_strategy,
)

logger = logging.getLogger(__name__)

DEFAULT_PRICE_CSV = (
    PROJECT_ROOT / "data" / "etf_backtest" / "etf_prices_4y.csv"
)
PROTECTED_OUTPUT_DIRS = (
    "src",
    "scripts",
    "backend",
    "frontend",
    "tests",
    ".git",
    ".github",
)
PROTECTED_OUTPUT_FILES = (
    ".env",
    ".env.example",
    ".gitignore",
    ".pre-commit-config.yaml",
    "README.md",
    "VERSION",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
)


def _format_feature(value: Any, fmt: str = "{:.4f}") -> str:
    if value is None:
        return "—"
    try:
        return fmt.format(float(value))
    except (TypeError, ValueError):
        return str(value)


def _render_markdown(
    *,
    regime_dict: dict,
    recommendation: StrategyRecommendation,
    price_csv: Path,
    lookback_days: int,
) -> str:
    lines: list[str] = []
    lines.append("# Market Regime Recommendation")
    lines.append("")
    lines.append(
        f"Generated from `{price_csv.name}` over the last **{lookback_days}** trading days "
        f"(as_of = `{regime_dict.get('as_of')}`)."
    )
    lines.append("")
    lines.append("## Regime")
    lines.append("")
    lines.append(f"- **Regime**: `{regime_dict['regime_name']}`")
    lines.append(f"- **Confidence**: {float(regime_dict['confidence']):.0%}")
    lines.append(f"- **Bars used**: {regime_dict['n_bars_used']}")
    lines.append(f"- **Assets used**: {regime_dict['n_assets_used']}")
    lines.append("")
    lines.append("### Features")
    lines.append("")
    feats = regime_dict.get("features", {}) or {}
    lines.append("| Feature | Value |")
    lines.append("|---|---|")
    lines.append(f"| trend_r2 | {_format_feature(feats.get('trend_r2'), '{:.3f}')} |")
    lines.append(
        f"| trend_slope (log-price / day) | "
        f"{_format_feature(feats.get('trend_slope'), '{:.5f}')} |"
    )
    lines.append(
        f"| realized_vol (annualised) | {_format_feature(feats.get('realized_vol'), '{:.1%}')} |"
    )
    lines.append(f"| return_skew | {_format_feature(feats.get('return_skew'), '{:.2f}')} |")
    lines.append(
        f"| drawdown_ratio (max_dd / vol) | "
        f"{_format_feature(feats.get('drawdown_ratio'), '{:.2f}')} |"
    )
    lines.append(
        f"| avg_pairwise_correlation | "
        f"{_format_feature(feats.get('avg_pairwise_correlation'), '{:.2f}')} |"
    )
    lines.append("")
    lines.append("### Why")
    lines.append("")
    for reason in regime_dict.get("reasons", []) or []:
        lines.append(f"- {reason}")
    lines.append("")
    lines.append("## Recommendation")
    lines.append("")
    lines.append(f"- **Run strategy**: `{recommendation.strategy_name}`")
    if recommendation.config_overrides:
        overrides_repr = ", ".join(
            f"`{k}={v!r}`" for k, v in recommendation.config_overrides.items()
        )
        lines.append(f"- **Config overrides**: {overrides_repr}")
    else:
        lines.append("- **Config overrides**: (none)")
    if recommendation.alternatives:
        lines.append(
            f"- **Alternatives**: {', '.join('`' + a + '`' for a in recommendation.alternatives)}"
        )
    lines.append("")
    lines.append("### Rationale")
    lines.append("")
    lines.append(recommendation.rationale)
    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    lines.append(
        "- Regimes change slowly; 90-day lookback may miss inflection points by ~30 days."
    )
    lines.append(
        "- Bear-regime mapping is based on portfolio-risk practice, "
        "not in-sample evidence (the empirical anchor in commit `a54b986` only covered "
        "trending vs choppy halves of an up-market window)."
    )
    lines.append(
        "- Empirical anchor: in commit `a54b986`'s multi-strategy comparison "
        "(2024-01-01 → 2025-04-30), the choppy first half "
        "(R²=0.370) had `rotation` winning (+5.48%); "
        "the trending second half (R²=0.792) had `mean_reversion` winning (+6.17%). "
        "The recommender encodes that split."
    )
    return "\n".join(lines) + "\n"


def _load_price_matrix(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"price CSV not found: {csv_path}")
    frame = pd.read_csv(csv_path, index_col=0)
    frame.index = pd.to_datetime(frame.index)
    return (
        frame.apply(pd.to_numeric, errors="coerce")
        .sort_index()
        .ffill()
        .dropna(how="all")
    )


def _resolve_for_guard(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _format_guard_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _data_roots_for(price_csv: Path) -> tuple[Path, ...]:
    roots = {PROJECT_ROOT.resolve() / "data"}
    resolved_price_csv = _resolve_for_guard(price_csv)
    for parent in resolved_price_csv.parents:
        if parent.name == "data":
            roots.add(parent)
    return tuple(sorted(roots, key=str))


def _validate_output_path(output_path: Path, *, price_csv: Path, flag_name: str) -> Path:
    """Reject CLI report outputs that would overwrite source or data files."""

    resolved_output = _resolve_for_guard(output_path)
    resolved_price_csv = _resolve_for_guard(price_csv)

    if resolved_output == resolved_price_csv:
        raise ValueError(f"{flag_name} must not overwrite --price-csv: {output_path}")

    if resolved_output.exists() and resolved_output.is_dir():
        raise ValueError(f"{flag_name} must point to a file, not a directory: {output_path}")

    project_root = PROJECT_ROOT.resolve()
    for data_root in _data_roots_for(price_csv):
        if _is_relative_to(resolved_output, data_root):
            raise ValueError(
                f"{flag_name} must not write into a data directory: "
                f"{_format_guard_path(resolved_output)}"
            )

    protected_files = tuple(project_root / name for name in PROTECTED_OUTPUT_FILES)
    if resolved_output in protected_files:
        raise ValueError(
            f"{flag_name} must not overwrite protected project file: "
            f"{_format_guard_path(resolved_output)}"
        )

    protected_roots = tuple(project_root / name for name in PROTECTED_OUTPUT_DIRS)
    for protected_root in protected_roots:
        if _is_relative_to(resolved_output, protected_root):
            raise ValueError(
                f"{flag_name} must not target protected project path: "
                f"{_format_guard_path(resolved_output)}"
            )

    return output_path.expanduser()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Classify the current market regime from a wide-form price "
            "CSV and print the recommended strategy."
        ),
    )
    parser.add_argument(
        "--price-csv",
        type=Path,
        default=DEFAULT_PRICE_CSV,
        help=(
            "Path to a wide-form CSV (date index, one column per asset). "
            "Defaults to data/etf_backtest/etf_prices_4y.csv."
        ),
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=90,
        help="Trailing window length in trading days (default 90).",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="Optional path to write the markdown report to.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write the raw JSON payload to.",
    )
    parser.add_argument(
        "--trend-r2-threshold",
        type=float,
        default=None,
        help="Override the trend-R² threshold (default 0.55).",
    )
    parser.add_argument(
        "--vol-high-threshold",
        type=float,
        default=None,
        help="Override the high-vol threshold in annualised vol units (default 0.25).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress markdown stdout (still writes --output-md / --output-json).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.lookback_days <= 0:
        parser.error("--lookback-days must be positive")

    try:
        output_md = (
            _validate_output_path(
                args.output_md,
                price_csv=args.price_csv,
                flag_name="--output-md",
            )
            if args.output_md is not None
            else None
        )
        output_json = (
            _validate_output_path(
                args.output_json,
                price_csv=args.price_csv,
                flag_name="--output-json",
            )
            if args.output_json is not None
            else None
        )
    except ValueError as exc:
        parser.error(str(exc))

    cfg_kwargs: dict[str, Any] = {}
    if args.trend_r2_threshold is not None:
        cfg_kwargs["trend_r2_threshold"] = float(args.trend_r2_threshold)
    if args.vol_high_threshold is not None:
        cfg_kwargs["vol_high_threshold"] = float(args.vol_high_threshold)
    config = ClassifierConfig(**cfg_kwargs) if cfg_kwargs else ClassifierConfig()

    frame = _load_price_matrix(args.price_csv)
    classifier = MarketRegimeClassifier(config=config)
    regime = classifier.classify(frame, lookback_days=args.lookback_days)
    recommendation = recommend_strategy(regime)
    regime_dict = regime.to_dict()

    markdown = _render_markdown(
        regime_dict=regime_dict,
        recommendation=recommendation,
        price_csv=args.price_csv,
        lookback_days=args.lookback_days,
    )
    if not args.quiet:
        print(markdown)

    if output_md is not None:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(markdown, encoding="utf-8")
        logger.info("Markdown report written to %s", output_md)

    if output_json is not None:
        payload = {
            "regime": regime_dict,
            "recommendation": recommendation.to_dict(),
            "lookback_days": int(args.lookback_days),
            "price_csv": str(args.price_csv),
        }
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False),
            encoding="utf-8",
        )
        logger.info("JSON payload written to %s", output_json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
