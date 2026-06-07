from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd


def winsorize(s: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    if s.dropna().empty:
        return s
    lo, hi = s.quantile(lower), s.quantile(upper)
    return s.clip(lower=lo, upper=hi)


def cross_sectional_zscore(s: pd.Series) -> pd.Series:
    x = s.astype(float)
    mu = x.mean(skipna=True)
    sd = x.std(skipna=True, ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return ((x - mu) / sd).fillna(0.0)


def cross_sectional_rank(s: pd.Series) -> pd.Series:
    # average-rank -> [0,1]; NaNs -> 0.5 (neutral)
    r = s.rank(method="average", na_option="keep")
    n = r.notna().sum()
    if n <= 1:
        return pd.Series(0.5, index=s.index)
    return ((r - 1) / (n - 1)).fillna(0.5)


@runtime_checkable
class Factor(Protocol):
    name: str
    direction: int  # +1: higher value = more bullish; -1: lower = more bullish

    def compute(self, panel, as_of: pd.Timestamp) -> pd.Series:
        """Return cross-sectional raw factor values {symbol: value}, using only data <= as_of."""
        ...
