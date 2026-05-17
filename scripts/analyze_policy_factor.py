#!/usr/bin/env python3
"""CLI: empirical attribution for ``policy_signal_factor``.

Reads the ETF rotation audit log, fetches close-price history for every
ETF referenced in the window, and prints a Markdown attribution report.

Usage:

    python scripts/analyze_policy_factor.py \\
        --audit-log ~/.config/etf-rotation/audit.jsonl \\
        --period-days 30 \\
        --output-md docs/sample_attribution_report.md \\
        --output-json output/sample_attribution_report.json

Defaults follow the same resolution order as ``scripts.daily_etf_signal``:

* ``--audit-log`` → ``ETF_AUDIT_LOG_PATH`` env var → "
  ``~/.config/etf-rotation/audit.jsonl``.

When ``--synthetic`` is passed, a deterministic 30-day audit log + price
matrix is generated in-memory so reviewers can see the full report shape
without needing real history. The synthetic data set is reproducible
(seeded RNG) and exercises the bullish / bearish / mixed cases.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.research.policy_factor_attribution import (  # noqa: E402
    AttributionReport,
    compute_attribution,
    render_markdown,
)

logger = logging.getLogger(__name__)

DEFAULT_AUDIT_PATH = Path("~/.config/etf-rotation/audit.jsonl").expanduser()
DEFAULT_PERIOD_DAYS = 30


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute empirical attribution for the opt-in policy_signal_factor. "
            "Reads the rebalance audit log and a price matrix, replays each "
            "rebalance with a proportional post-overlay policy-off proxy, "
            "and prints a Markdown report comparing factor-on vs factor-off-proxy P&L."
        ),
    )
    parser.add_argument(
        "--audit-log",
        type=Path,
        default=None,
        help=(
            "Audit log path (JSON Lines). Defaults to ETF_AUDIT_LOG_PATH env "
            "var or ~/.config/etf-rotation/audit.jsonl."
        ),
    )
    parser.add_argument(
        "--period-days",
        type=int,
        default=DEFAULT_PERIOD_DAYS,
        help=f"Window length in calendar days (default {DEFAULT_PERIOD_DAYS}).",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="If set, write the Markdown report to this path.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="If set, write the JSON report (AttributionReport.to_dict()) here.",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help=(
            "Generate a deterministic 30-day audit log + price matrix and run "
            "attribution against it. Useful for previewing the report when no "
            "factor-on history exists yet."
        ),
    )
    parser.add_argument(
        "--synthetic-seed",
        type=int,
        default=2026,
        help="RNG seed for --synthetic (default 2026).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable INFO logging.",
    )
    return parser


def _resolve_audit_path(explicit: Optional[Path]) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser()
    env_value = os.environ.get("ETF_AUDIT_LOG_PATH")
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_AUDIT_PATH


# ---------------------------------------------------------------------------
# Synthetic data generation (deterministic — only used by --synthetic)
# ---------------------------------------------------------------------------


SYNTHETIC_UNIVERSE = ["512400", "515030", "159987", "562880", "510300"]
SYNTHETIC_INDUSTRY_MAP = {
    "512400": "metals",
    "515030": "新能源汽车",
    "159987": "风电",
    "562880": "电网",
    "510300": "broad_market",
}


def _generate_synthetic_prices(
    *,
    end: datetime,
    n_days: int,
    seed: int,
) -> pd.DataFrame:
    """Deterministic 30-day daily close history for the synthetic universe."""

    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=end.date(), periods=n_days, freq="D")
    base = {
        "512400": 6.50,
        "515030": 1.20,
        "159987": 0.85,
        "562880": 1.40,
        "510300": 4.20,
    }
    # Asymmetric drifts so the attribution has both winners and losers.
    drifts = {
        "512400": +0.0040,   # rising — bullish boost will help
        "515030": -0.0050,   # falling — bearish penalty will help
        "159987": +0.0005,
        "562880": +0.0008,
        "510300": +0.0010,
    }
    vols = dict.fromkeys(SYNTHETIC_UNIVERSE, 0.012)
    frames: dict[str, list[float]] = {}
    for code in SYNTHETIC_UNIVERSE:
        p = float(base[code])
        series = [p]
        for _ in range(n_days - 1):
            shock = rng.normal(loc=drifts[code], scale=vols[code])
            p = max(0.01, p * (1.0 + shock))
            series.append(p)
        frames[code] = series
    return pd.DataFrame(frames, index=idx)


def _generate_synthetic_audit(
    *,
    prices: pd.DataFrame,
    end: datetime,
    n_rebalances: int = 6,
) -> list[dict[str, Any]]:
    """Build factor-ON audit rows spaced ~5 days apart over the price window."""

    entries: list[dict[str, Any]] = []
    if prices.empty:
        return entries
    period_total = (prices.index[-1] - prices.index[0]).days
    step_days = max(1, period_total // n_rebalances)
    # Industry signals alternate so we get a mix of boost/penalty.
    signals = [
        {"metals": ("bullish", 0.30), "新能源汽车": ("bearish", -0.32)},
        {"metals": ("bullish", 0.25), "新能源汽车": ("bearish", -0.20)},
        {"metals": ("bullish", 0.15), "新能源汽车": ("neutral", 0.05)},
        {"metals": ("bearish", -0.20), "新能源汽车": ("bullish", 0.20)},
        {"metals": ("bullish", 0.18), "新能源汽车": ("bearish", -0.28)},
        {"metals": ("bullish", 0.22), "新能源汽车": ("bearish", -0.35)},
    ]
    base_weights = {
        "512400": 0.20, "515030": 0.20, "159987": 0.15,
        "562880": 0.15, "510300": 0.20,
    }
    for i in range(min(n_rebalances, len(signals))):
        d = prices.index[0] + pd.Timedelta(days=step_days * i)
        run_at = datetime.combine(
            d.date(), datetime.min.time(),
        ).replace(hour=2, tzinfo=timezone.utc).isoformat()
        sig = signals[i]
        adjusted: dict[str, float] = dict(base_weights)
        policy_meta: dict[str, dict[str, Any]] = {}
        applied = 0
        for code, industry in SYNTHETIC_INDUSTRY_MAP.items():
            if industry not in sig:
                continue
            classification, avg_impact = sig[industry]
            multiplier = 1.0
            if classification == "bullish":
                multiplier = 1.10
            elif classification == "bearish":
                multiplier = 0.90
            before = base_weights[code]
            after = before * multiplier
            adjusted[code] = round(after, 6)
            policy_meta[code] = {
                "industry": industry,
                "signal": classification,
                "multiplier": multiplier,
                "weight_before": before,
                "weight_after": after,
                "delta_weight": round(after - before, 6),
                "applied": multiplier != 1.0,
                "avg_impact": avg_impact,
            }
            if multiplier != 1.0:
                applied += 1
        prices_at_decision = {
            code: float(prices.loc[d, code])
            for code in SYNTHETIC_UNIVERSE
        }
        entries.append({
            "run_at": run_at,
            "quote_source": "synthetic",
            "adjusted_weights": adjusted,
            "target_weights": dict(base_weights),
            "score_breakdown": {
                code: {"policy_adjustment": meta}
                for code, meta in policy_meta.items()
            },
            "policy_signal_factor": {
                "enabled": True,
                "applied_count": applied,
                "boosted": [c for c, m in policy_meta.items() if m["multiplier"] > 1.0],
                "penalised": [c for c, m in policy_meta.items() if m["multiplier"] < 1.0],
            },
            "prices_at_decision": prices_at_decision,
        })
    return entries


def _materialise_synthetic(
    *,
    seed: int,
    period_days: int,
    audit_out: Path,
) -> tuple[pd.DataFrame, datetime]:
    """Write a synthetic audit JSONL + return the in-memory price matrix."""

    end = datetime.now(timezone.utc).replace(microsecond=0)
    # Generate slightly more price history than the window so the very first
    # rebalance has at least one bar of forward data.
    prices = _generate_synthetic_prices(
        end=end, n_days=period_days + 5, seed=seed,
    )
    entries = _generate_synthetic_audit(prices=prices, end=end)
    audit_out.parent.mkdir(parents=True, exist_ok=True)
    with audit_out.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True))
            fh.write("\n")
    return prices, end


# ---------------------------------------------------------------------------
# Price matrix loading (real path)
# ---------------------------------------------------------------------------


def _load_price_matrix(
    audit_path: Path, period_days: int,
) -> pd.DataFrame:
    """Look up close history for every ETF referenced in the window."""

    from scripts import daily_etf_signal  # late import; avoids cycles

    entries = daily_etf_signal.read_audit_log(audit_path)
    codes = set()
    for entry in entries:
        for code in (entry.get("adjusted_weights") or {}):
            if code != "CASH":
                codes.add(str(code))
        for code in (entry.get("target_weights") or {}):
            if code != "CASH":
                codes.add(str(code))
    if not codes:
        return pd.DataFrame()

    end = datetime.now()
    start = end - timedelta(days=max(period_days + 10, 60))
    try:
        from src.data.etf_price_history import fetch_etf_history
        matrix = fetch_etf_history(sorted(codes), start_date=start, end_date=end)
    except Exception as exc:
        logger.warning("Failed to fetch ETF history for attribution: %s", exc)
        matrix = pd.DataFrame()
    return matrix


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    audit_path = _resolve_audit_path(args.audit_log)

    if args.synthetic:
        synthetic_dir = Path("output").resolve() / "policy_factor_attribution"
        synthetic_dir.mkdir(parents=True, exist_ok=True)
        synthetic_audit = synthetic_dir / "synthetic_audit.jsonl"
        prices, now = _materialise_synthetic(
            seed=args.synthetic_seed,
            period_days=args.period_days,
            audit_out=synthetic_audit,
        )
        audit_path = synthetic_audit
        nav_history = prices
        anchor: Optional[datetime] = now
    else:
        nav_history = _load_price_matrix(audit_path, args.period_days)
        anchor = None
        if nav_history.empty:
            print(
                "WARNING: ETF price history empty (akshare offline or no audit codes). "
                "Attribution will report zero contribution but no exception.",
                file=sys.stderr,
            )

    report: AttributionReport = compute_attribution(
        audit_path, nav_history,
        period_days=args.period_days,
        now=anchor,
    )

    md = render_markdown(report)

    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(md, encoding="utf-8")
        print(f"Markdown written: {args.output_md}", file=sys.stderr)

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        print(f"JSON written: {args.output_json}", file=sys.stderr)

    if not args.output_md and not args.output_json:
        print(md)

    return 0


if __name__ == "__main__":
    sys.exit(main())
