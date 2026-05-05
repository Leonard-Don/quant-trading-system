"""Pure numeric helpers for IndustryAnalyzer.

Lifted out of ``IndustryAnalyzer`` (formerly ``@staticmethod`` members):
``derive_size_source``, ``scale_rank_score``, ``weighted_std``,
``apply_historical_volatility``. Pure functions with no instance state.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def derive_size_source(market_cap_source: Any) -> str:
    """Collapse heterogeneous market-cap source labels to a small enum.

    Returns one of: ``snapshot`` / ``proxy`` / ``estimated`` / ``live``.
    """
    source = str(market_cap_source or "unknown").strip()
    if source.startswith("snapshot_"):
        return "snapshot"
    if source == "sina_proxy_stock_sum":
        return "proxy"
    if source == "unknown" or source.startswith("estimated") or source == "constant_fallback":
        return "estimated"
    return "live"


def scale_rank_score(series: pd.Series) -> pd.Series:
    """Compress raw cross-sectional scores into a 20-95 display band.

    The 20-95 range avoids bottom/top sticky values when sample variance is low.
    """
    clean = (
        pd.to_numeric(series, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )
    if clean.empty:
        return clean
    if len(clean) == 1:
        return pd.Series([50.0], index=clean.index, dtype=float)

    s_min = clean.min()
    s_max = clean.max()
    if s_max <= s_min:
        return pd.Series(50.0, index=clean.index, dtype=float)
    return 20 + 75 * (clean - s_min) / (s_max - s_min)


def weighted_std(values: np.ndarray, weights: np.ndarray) -> float:
    """Weighted standard deviation, falling back to plain std when weights vanish."""
    clean_values = np.asarray(values, dtype=float)
    clean_weights = np.asarray(weights, dtype=float)
    if clean_values.size == 0:
        return 0.0
    if clean_values.size == 1:
        return 0.0
    if clean_weights.size != clean_values.size or clean_weights.sum() <= 0:
        return float(np.std(clean_values))
    mean = np.average(clean_values, weights=clean_weights)
    variance = np.average((clean_values - mean) ** 2, weights=clean_weights)
    return float(np.sqrt(max(variance, 0.0)))


def apply_historical_volatility(
    df: pd.DataFrame, historical_vol_df: pd.DataFrame
) -> pd.DataFrame:
    """Overlay real historical-vol numbers on top of proxy industry_volatility."""
    if df.empty or historical_vol_df.empty:
        return df
    merged = df.merge(
        historical_vol_df[["industry_name", "industry_volatility"]],
        on="industry_name",
        how="left",
        suffixes=("", "_historical"),
    )
    if "industry_volatility_historical" in merged.columns:
        historical_mask = pd.to_numeric(
            merged["industry_volatility_historical"],
            errors="coerce",
        ).notna()
        merged["industry_volatility"] = pd.to_numeric(
            merged["industry_volatility_historical"],
            errors="coerce",
        ).fillna(
            pd.to_numeric(merged.get("industry_volatility", 0), errors="coerce").fillna(
                0.0
            )
        )
        if "industry_volatility_source" not in merged.columns:
            merged["industry_volatility_source"] = None
        merged.loc[historical_mask, "industry_volatility_source"] = "historical_index"
        merged = merged.drop(columns=["industry_volatility_historical"])
    return merged


__all__ = [
    "derive_size_source",
    "scale_rank_score",
    "weighted_std",
    "apply_historical_volatility",
]
