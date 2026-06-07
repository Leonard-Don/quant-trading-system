"""Pure trend-series helpers for IndustryAnalyzer.

Lifted out of ``IndustryAnalyzer`` — the cumulative-change → relative-points
transform (formerly ``_build_relative_trend_points_from_cumulative_changes``)
and the OHLC frame → list-of-dicts builder used by ``_load_industry_trend_series``.
Both are pure: they take frames/sequences and return plain Python data, with no
instance or provider state.
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd


def build_relative_trend_points_from_cumulative_changes(
    cumulative_changes: list[float],
) -> list[float]:
    """Rebase a sequence of cumulative changes (%) onto a 100-anchored trend."""
    if not cumulative_changes:
        return []

    points = []
    ordered_changes = list(cumulative_changes)
    for change in reversed(ordered_changes):
        try:
            denominator = 1 + (float(change) / 100.0)
        except (TypeError, ValueError):
            return []
        if denominator <= 0:
            return []
        points.append(round(100.0 / denominator, 3))
    points.append(100.0)
    return points


def build_industry_ohlc_trend(normalized_hist: pd.DataFrame) -> list[dict[str, Any]]:
    """Turn a sorted/trimmed industry-index OHLC frame into trend-series rows.

    Each row carries ``date``, OHLC, ``volume``/``amount`` (when present) and a
    ``change_pct`` derived from the prior valid close. Rows with an unparseable
    close are skipped.
    """
    result: list[dict[str, Any]] = []
    prev_close: Optional[float] = None
    for idx, row in normalized_hist.iterrows():
        close_value = pd.to_numeric(pd.Series([row.get("close")]), errors="coerce").iloc[0]
        if pd.isna(close_value):
            continue

        open_value = (
            pd.to_numeric(pd.Series([row.get("open")]), errors="coerce").iloc[0]
            if "open" in normalized_hist.columns
            else np.nan
        )
        high_value = (
            pd.to_numeric(pd.Series([row.get("high")]), errors="coerce").iloc[0]
            if "high" in normalized_hist.columns
            else np.nan
        )
        low_value = (
            pd.to_numeric(pd.Series([row.get("low")]), errors="coerce").iloc[0]
            if "low" in normalized_hist.columns
            else np.nan
        )
        volume_value = (
            pd.to_numeric(pd.Series([row.get("volume")]), errors="coerce").iloc[0]
            if "volume" in normalized_hist.columns
            else np.nan
        )
        amount_value = (
            pd.to_numeric(pd.Series([row.get("amount")]), errors="coerce").iloc[0]
            if "amount" in normalized_hist.columns
            else np.nan
        )
        change_pct = (
            ((float(close_value) / prev_close - 1) * 100)
            if prev_close is not None and prev_close != 0
            else None
        )

        result.append(
            {
                "date": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
                "open": None if pd.isna(open_value) else round(float(open_value), 2),
                "high": None if pd.isna(high_value) else round(float(high_value), 2),
                "low": None if pd.isna(low_value) else round(float(low_value), 2),
                "close": round(float(close_value), 2),
                "volume": None if pd.isna(volume_value) else float(volume_value),
                "amount": None if pd.isna(amount_value) else float(amount_value),
                "change_pct": None if change_pct is None else round(float(change_pct), 2),
            }
        )
        prev_close = float(close_value)

    return result


__all__ = [
    "build_industry_ohlc_trend",
    "build_relative_trend_points_from_cumulative_changes",
]
