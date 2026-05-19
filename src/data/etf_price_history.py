"""Lightweight ETF historical price loader for the rotation strategy.

The rotation script's default ``synthesize_price_matrix`` produces a
deterministic noise walk so the strategy is hermetic in tests and demos.
For *real* signal generation we need real history. This module wraps two
akshare endpoints and returns a wide-form close-price matrix suitable
for ``EtfRotationStrategy``:

1. ``fund_etf_hist_sina`` — primary. Sina serves the full history in one
   shot, no date range needed. Tolerant of CN broker networks and the
   most reliable endpoint in practice.
2. ``fund_etf_hist_em`` — fallback for codes Sina doesn't recognise.
   Eastmoney requires explicit start/end dates and ``qfq`` adjustment.

Design choices:

* **Offline-safe**: ``akshare`` is imported lazily; a missing or broken
  install yields an empty DataFrame plus a logged warning. Callers fall
  back to ``synthesize_price_matrix`` automatically.
* **Proxy-safe**: macOS in particular injects system proxies into Python
  via scutil. We clear them before calling akshare and restore them on
  exit, so the rest of the process isn't affected.
* **No persistent state**: each call is independent. Pair with a local
  CSV cache if you need re-use across runs.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence

import pandas as pd

logger = logging.getLogger(__name__)

_PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)


@contextmanager
def _proxy_blackout() -> Iterator[None]:
    """Temporarily clear proxy env vars + urllib.getproxies for one call.

    Restores prior state on exit so the rest of the application isn't
    affected by the akshare-specific bypass.
    """

    import urllib.request

    original_env: Dict[str, Optional[str]] = {
        var: os.environ.get(var) for var in _PROXY_ENV_VARS
    }
    original_no_proxy = os.environ.get("NO_PROXY"), os.environ.get("no_proxy")
    original_getproxies = urllib.request.getproxies

    for var in _PROXY_ENV_VARS:
        os.environ[var] = ""
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    urllib.request.getproxies = lambda: {}

    try:
        yield
    finally:
        for var, value in original_env.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value
        np1, np2 = original_no_proxy
        if np1 is None:
            os.environ.pop("NO_PROXY", None)
        else:
            os.environ["NO_PROXY"] = np1
        if np2 is None:
            os.environ.pop("no_proxy", None)
        else:
            os.environ["no_proxy"] = np2
        urllib.request.getproxies = original_getproxies


def _import_akshare():
    try:
        import akshare as ak  # type: ignore[import-not-found]
    except ImportError as exc:
        logger.warning("akshare unavailable; ETF history fetch disabled: %s", exc)
        return None
    return ak


# Sina uses ``shXXXXXX`` / ``szXXXXXX`` prefixed symbols.
def _sina_symbol(code: str) -> str:
    code = code.strip()
    if code.startswith(("sh", "sz", "bj")):
        return code
    # SH: 5* (510/511/512/...) and 6*; SZ: 0*/1*/3*. ETFs in CN follow this.
    prefix = "sh" if code[:1] in {"5", "6"} or code.startswith("11") else "sz"
    return f"{prefix}{code}"


def _fetch_one_sina(ak, code: str) -> Optional[pd.Series]:
    raw = ak.fund_etf_hist_sina(symbol=_sina_symbol(code))
    if raw is None or raw.empty:
        return None
    return _normalize_etf_history(raw)


def _fetch_one_eastmoney(
    ak, code: str, start_str: str, end_str: str, adjust: str
) -> Optional[pd.Series]:
    raw = ak.fund_etf_hist_em(
        symbol=code,
        period="daily",
        start_date=start_str,
        end_date=end_str,
        adjust=adjust,
    )
    if raw is None or raw.empty:
        return None
    return _normalize_etf_history(raw)


def fetch_etf_history(
    codes: Sequence[str],
    *,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    adjust: str = "qfq",
) -> pd.DataFrame:
    """Return a wide close-price DataFrame keyed by ETF code.

    Args:
        codes: 6-digit ETF codes (no exchange prefix).
        start_date: Inclusive history start. Defaults to ``end_date - 18mo``
            (enough margin past the 60-day warmup for stable scoring).
        end_date: Inclusive end. Defaults to today.
        adjust: ``"qfq"`` (forward-adjusted, default), ``"hfq"``
            (backward-adjusted), or ``""`` (raw). Only honored on the
            Eastmoney fallback — Sina returns unadjusted close.

    Returns an empty DataFrame when akshare is unavailable or every
    request fails — callers should fall back to a synthetic matrix and
    surface that via the source-health registry.
    """

    if not codes:
        return pd.DataFrame()

    ak = _import_akshare()
    if ak is None:
        return pd.DataFrame()

    if end_date is None:
        end_date = datetime.now()
    if start_date is None:
        start_date = end_date - timedelta(days=540)  # ~18 months

    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    frames: Dict[str, pd.Series] = {}
    failures: List[str] = []

    with _proxy_blackout():
        for code in codes:
            series: Optional[pd.Series] = None
            sina_err: Optional[str] = None
            eastmoney_err: Optional[str] = None

            if hasattr(ak, "fund_etf_hist_sina"):
                try:
                    series = _fetch_one_sina(ak, code)
                except Exception as exc:
                    sina_err = repr(exc)
                    logger.debug("Sina history failed for %s: %s", code, exc)

            if series is None and hasattr(ak, "fund_etf_hist_em"):
                try:
                    series = _fetch_one_eastmoney(ak, code, start_str, end_str, adjust)
                except Exception as exc:
                    eastmoney_err = repr(exc)
                    logger.debug("Eastmoney history failed for %s: %s", code, exc)

            if series is None or series.empty:
                logger.warning(
                    "akshare returned no usable history for %s (sina=%s, eastmoney=%s)",
                    code, sina_err or "skipped", eastmoney_err or "skipped",
                )
                failures.append(code)
                continue

            # Trim to the requested window so the strategy isn't fed pre-2010 data.
            if start_date is not None:
                series = series[series.index >= pd.Timestamp(start_date)]
            if end_date is not None:
                series = series[series.index <= pd.Timestamp(end_date)]

            frames[code] = series

    if not frames:
        logger.warning("ETF history fetch returned no data (failures=%s)", failures)
        return pd.DataFrame()

    matrix = pd.DataFrame(frames).sort_index()
    matrix = matrix.apply(pd.to_numeric, errors="coerce").ffill().dropna(how="all")
    return matrix


def _normalize_etf_history(raw: pd.DataFrame) -> pd.Series:
    """Project an akshare history frame to a date-indexed close-price series.

    Handles both Sina (English column names) and Eastmoney (Chinese
    column names) shapes. Raises ``KeyError`` if neither convention is
    present.
    """

    aliases = {
        "日期": "date",
        "收盘": "close",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
    }
    df = raw.rename(columns={k: v for k, v in aliases.items() if k in raw.columns})

    if "date" not in df.columns or "close" not in df.columns:
        raise KeyError(f"Expected date/close columns, got {list(df.columns)}")

    df = df[["date", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df["close"].astype(float)


# ---------------------------------------------------------------------------
# CSV path resolution — 5y > 4y preference
# ---------------------------------------------------------------------------


# Canonical CSV locations relative to the project root. The 5-year file
# was added for power-analysis reasons (the 4y window had ~63 weekly
# rebalances, too few for the formal DM/Sharpe/bootstrap tests); when
# the 5y artefact is on disk we prefer it transparently so callers don't
# have to special-case the bigger sample.
_DEFAULT_5Y_RELPATH = Path("data") / "etf_backtest" / "etf_prices_5y.csv"
_DEFAULT_4Y_RELPATH = Path("data") / "etf_backtest" / "etf_prices_4y.csv"


def resolve_default_price_csv(project_root: Path) -> Path:
    """Return the preferred default price-history CSV under ``project_root``.

    Resolution rule, in order:

    1. ``data/etf_backtest/etf_prices_5y.csv`` — if it exists, return it.
       The 5-year window is what the post-power-analysis runs depend on.
    2. ``data/etf_backtest/etf_prices_4y.csv`` — fallback (always
       returned as-is, even if it does not exist, so the original
       hard-coded path semantics are preserved for legacy callers that
       still expect to see this string in error messages).

    The function is pure and does no I/O beyond ``Path.exists()``.
    """

    candidate_5y = project_root / _DEFAULT_5Y_RELPATH
    if candidate_5y.exists():
        return candidate_5y
    return project_root / _DEFAULT_4Y_RELPATH


__all__ = ["fetch_etf_history", "resolve_default_price_csv"]
