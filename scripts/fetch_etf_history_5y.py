#!/usr/bin/env python3
"""Fetch a 5-year ETF close-price matrix for backtest power analysis.

The committed ``data/etf_backtest/etf_prices_4y.csv`` covers
2022-05-18 → 2026-05-15 (~969 rows). That single 16-month live window
(2024-01 → 2025-04) is too small for the formal hypothesis tests in
``scripts/strategy_significance_test.py``: at α=0.05 / 80% power to
detect a +3pp/yr edge, the power analysis estimated ~5× more weekly
periods than we have. Hence: this script writes a 5-year matrix at
``data/etf_backtest/etf_prices_5y.csv`` over 2020-01-01 → 2024-12-31.

Why a separate file (and not extend in-place)?

* Keeps the existing path stable for any cached/golden test that
  references ``etf_prices_4y.csv``. The loader transparently prefers
  the 5y file when present.
* Lets us re-fetch / refresh the 5y series without touching the 4y
  golden CSV (which the dashboard / API endpoint defaults still pin
  to in OpenAPI docs).

Source: ``akshare.fund_etf_hist_sina`` — Sina serves the *entire*
history for an ETF in one HTTP call, with the broker-adjusted close
that matches the existing 4y CSV exactly (verified: 510300 on
2022-05-18 = 3.986 in both files). We fall back to
``fund_etf_hist_em(adjust='hfq')`` if Sina is unreachable for a code.

Usage::

    python scripts/fetch_etf_history_5y.py \\
        --start-date 2020-01-01 \\
        --end-date 2024-12-31 \\
        --output data/etf_backtest/etf_prices_5y.csv

Prints a summary on stdout. Re-running is safe (idempotent overwrite).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.etf_price_history import (  # noqa: E402
    _import_akshare,
    _normalize_etf_history,
    _proxy_blackout,
    _sina_symbol,
)
from src.data.etf_rotation import DEFAULT_UNIVERSE  # noqa: E402

logger = logging.getLogger("fetch_etf_history_5y")

DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data" / "etf_backtest" / "etf_prices_5y.csv"
)
# Same five-ETF universe used by ``EtfRotationStrategy``. Derive from the
# shared DEFAULT_UNIVERSE so the fetch script cannot drift from runtime
# rotation defaults when a code is added/removed.
DEFAULT_CODES: tuple[str, ...] = tuple(item.code for item in DEFAULT_UNIVERSE)


def _fetch_sina(ak, code: str) -> Optional[pd.Series]:
    """Best-effort Sina fetch. Returns ``None`` on any failure."""

    if not hasattr(ak, "fund_etf_hist_sina"):
        return None
    try:
        raw = ak.fund_etf_hist_sina(symbol=_sina_symbol(code))
    except Exception as exc:  # pragma: no cover — network failure path
        logger.warning("sina fetch failed for %s: %s", code, exc)
        return None
    if raw is None or raw.empty:
        return None
    return _normalize_etf_history(raw)


def _fetch_eastmoney(
    ak, code: str, start_date: datetime, end_date: datetime, adjust: str
) -> Optional[pd.Series]:
    """Fallback Eastmoney fetch (used only when Sina returns no data)."""

    if not hasattr(ak, "fund_etf_hist_em"):
        return None
    try:
        raw = ak.fund_etf_hist_em(
            symbol=code,
            period="daily",
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust=adjust,
        )
    except Exception as exc:  # pragma: no cover — network failure path
        logger.warning("eastmoney fetch failed for %s: %s", code, exc)
        return None
    if raw is None or raw.empty:
        return None
    return _normalize_etf_history(raw)


def fetch_history_matrix(
    codes: Iterable[str],
    *,
    start_date: datetime,
    end_date: datetime,
    sleep_between: float = 0.5,
    eastmoney_adjust: str = "hfq",
) -> tuple[pd.DataFrame, List[str]]:
    """Fetch a wide close-price matrix; return (matrix, list_of_failures)."""

    ak = _import_akshare()
    if ak is None:
        raise RuntimeError("akshare is not importable in this environment")

    frames: dict[str, pd.Series] = {}
    failures: List[str] = []

    with _proxy_blackout():
        for idx, code in enumerate(codes):
            if idx > 0 and sleep_between > 0:
                # Be polite to Sina/EM — they rate-limit aggressively.
                time.sleep(sleep_between)
            logger.info("fetching %s ...", code)
            series = _fetch_sina(ak, code)
            if series is None or series.empty:
                series = _fetch_eastmoney(
                    ak, code, start_date, end_date, eastmoney_adjust,
                )
            if series is None or series.empty:
                failures.append(code)
                logger.warning("no data for %s — skipping", code)
                continue
            series = series[
                (series.index >= pd.Timestamp(start_date))
                & (series.index <= pd.Timestamp(end_date))
            ]
            if series.empty:
                failures.append(code)
                logger.warning("empty series for %s within window", code)
                continue
            frames[code] = series.astype(float)

    if not frames:
        return pd.DataFrame(), failures

    matrix = pd.DataFrame(frames).sort_index()
    matrix = matrix.apply(pd.to_numeric, errors="coerce")
    return matrix, failures


def _print_summary(matrix: pd.DataFrame, failures: List[str], path: Path) -> None:
    """Render an info block describing what we just wrote to disk."""

    if matrix.empty:
        print(f"NO DATA WRITTEN (all {len(failures)} ETFs failed: {failures})")
        return
    n_rows, n_cols = matrix.shape
    coverage = {
        col: int(matrix[col].notna().sum()) for col in matrix.columns
    }
    print(f"Wrote {path} — {n_rows} rows × {n_cols} ETFs")
    print(f"  Date range:  {matrix.index.min().date()} → {matrix.index.max().date()}")
    print(f"  ETFs:        {list(matrix.columns)}")
    print(f"  Per-ETF non-null bars (out of {n_rows}):")
    for code, count in coverage.items():
        gap = n_rows - count
        flag = "" if gap == 0 else f"  [gaps: {gap}]"
        print(f"    {code}: {count}{flag}")
    if failures:
        print(f"  FAILED FETCHES: {failures}")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch a 5-year ETF close-price matrix (default 2020-01-01 → "
            "2024-12-31) for the rotation backtest power analysis."
        ),
    )
    parser.add_argument(
        "--start-date",
        default="2020-01-01",
        help="Inclusive start of the historical window (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        default="2024-12-31",
        help="Inclusive end of the historical window (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--codes",
        default=",".join(DEFAULT_CODES),
        help=(
            "Comma-separated ETF codes (no exchange prefix). Defaults to the "
            f"five-asset rotation universe: {','.join(DEFAULT_CODES)}."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination CSV path (wide format, date index, ETF columns).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Seconds to sleep between consecutive ETF fetches.",
    )
    parser.add_argument(
        "--eastmoney-adjust",
        default="hfq",
        choices=("qfq", "hfq", ""),
        help="Adjustment used only on the Eastmoney fallback.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _build_arg_parser().parse_args(argv)
    start = datetime.fromisoformat(args.start_date)
    end = datetime.fromisoformat(args.end_date)
    # Pad start by a few days so the rolling-warmup at window-start has
    # the lookback it needs. We trim back inside ``fetch_history_matrix``.
    pad_start = start - timedelta(days=10)
    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    if not codes:
        print("error: --codes resolved to an empty list", file=sys.stderr)
        return 2

    matrix, failures = fetch_history_matrix(
        codes,
        start_date=pad_start,
        end_date=end,
        sleep_between=args.sleep,
        eastmoney_adjust=args.eastmoney_adjust,
    )
    # Re-trim to exact window after collection (pad was only to absorb
    # the lookback warmup from upstream).
    if not matrix.empty:
        matrix = matrix[matrix.index >= pd.Timestamp(start)]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if matrix.empty:
        _print_summary(matrix, failures, args.output)
        return 1

    matrix.index.name = "date"
    matrix.to_csv(args.output, float_format="%.6g")
    _print_summary(matrix, failures, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
