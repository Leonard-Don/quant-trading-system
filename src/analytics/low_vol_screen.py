"""Pure, network-free low-volatility ranking core.

`low_volatility @ 20d` is the first factor in this project with genuine,
pre-registered out-of-sample support (CSI500 survivorship-free OOS IC +0.1135;
see ``docs/research/lowvol-confirmation.md``). It is a CROSS-SECTIONAL signal:
among a universe, the lower-trailing-realized-volatility names tend to outperform
over ~20 trading days.

The realized-vol definition here MUST match the validated factor EXACTLY
(``src/analytics/factors/price.py::LowVolatilityFactor``)::

    vol = close.pct_change().dropna().iloc[-window:].std(ddof=0)

Lower vol ranks higher. This module is the testable heart of the screen — it
takes already-fetched price frames and returns a deterministic ranking. It does
NOT fetch anything; the API layer is responsible for resolving the universe and
fetching prices (reusing the provider's caching/throttling).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def _realized_vol(close: pd.Series, window: int) -> float | None:
    """Trailing realized vol, identical to ``LowVolatilityFactor``.

    Returns ``None`` when there is not enough history (``< window + 1`` bars) or
    the resulting std is non-finite (e.g. a NaN inside the trailing window).
    """
    rets = close.pct_change().dropna()
    if len(rets) < window:
        return None
    vol = rets.iloc[-window:].std(ddof=0)
    if vol is None or not np.isfinite(vol):
        return None
    return float(vol)


def _recent_return(close: pd.Series, days: int) -> float | None:
    """Close-to-close percent return over the last ``days`` bars, as a percent.

    Needs ``days + 1`` closes (start bar + ``days`` steps). Returns ``None`` when
    there is insufficient history or the anchor close is non-positive / non-finite.
    """
    if days <= 0 or len(close) < days + 1:
        return None
    last = close.iloc[-1]
    prev = close.iloc[-days - 1]
    if not (np.isfinite(last) and np.isfinite(prev)) or prev == 0:
        return None
    return float((last / prev - 1.0) * 100.0)


def rank_low_volatility(
    prices_by_symbol: dict[str, pd.DataFrame],
    window: int = 60,
    top: int = 30,
    recent_return_days: int = 20,
) -> list[dict[str, Any]]:
    """Rank a universe ascending by trailing realized volatility (calmest first).

    Args:
        prices_by_symbol: ``{symbol -> OHLCV DataFrame}``. Each frame must have a
            ``close`` column and be time-ordered (oldest first). Frames with
            ``< window + 1`` bars or a non-finite vol are skipped.
        window: realized-vol lookback in trading days (validated default 60).
        top: keep at most this many names (after sorting). ``top <= 0`` keeps all.
        recent_return_days: lookback for the reported recent close-to-close return
            (the validated *holding* horizon is 20d).

    Returns:
        A list of dicts sorted ascending by ``realized_vol`` (ties broken by
        ``symbol`` for determinism), each::

            {
              "symbol": str,
              "realized_vol": float,          # the std (ddof=0)
              "annualized_vol": float,        # realized_vol * sqrt(252)
              "recent_return": float | None,  # last N-day close-to-close %, or None
              "n_bars": int,
              "rank": int,                    # 1-based, after sorting
            }
    """
    rows: list[dict[str, Any]] = []
    for symbol, frame in prices_by_symbol.items():
        if frame is None or getattr(frame, "empty", True) or "close" not in frame.columns:
            continue
        close = pd.to_numeric(frame["close"], errors="coerce")
        vol = _realized_vol(close, window)
        if vol is None:
            continue
        rows.append(
            {
                "symbol": str(symbol),
                "realized_vol": vol,
                "annualized_vol": vol * math.sqrt(TRADING_DAYS_PER_YEAR),
                "recent_return": _recent_return(close, recent_return_days),
                "n_bars": len(frame),
            }
        )

    # Ascending by vol; deterministic tie-break by symbol.
    rows.sort(key=lambda r: (r["realized_vol"], r["symbol"]))
    if top and top > 0:
        rows = rows[:top]
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
    return rows
