import numpy as np
import pandas as pd

from src.analytics.factors.base import (
    cross_sectional_rank,
    cross_sectional_zscore,
    winsorize,
)


def test_winsorize_clips_tails():
    s = pd.Series([-100.0, 1, 2, 3, 4, 5, 100.0], index=list("abcdefg"))
    w = winsorize(s, lower=0.1, upper=0.9)
    assert w.max() < 100.0 and w.min() > -100.0
    # middle values unchanged
    assert w["c"] == 2.0


def test_zscore_mean0_std1():
    s = pd.Series([1.0, 2, 3, 4, 5])
    z = cross_sectional_zscore(s)
    assert abs(z.mean()) < 1e-9
    assert abs(z.std(ddof=0) - 1.0) < 1e-9


def test_zscore_constant_series_returns_zeros():
    s = pd.Series([3.0, 3, 3])
    z = cross_sectional_zscore(s)
    assert (z == 0).all()  # no divide-by-zero


def test_rank_in_unit_interval_and_monotone():
    s = pd.Series([10.0, 30, 20], index=["x", "y", "z"])
    r = cross_sectional_rank(s)
    assert r["x"] < r["z"] < r["y"]
    assert r.min() >= 0.0 and r.max() <= 1.0


def test_nan_handled_not_propagated():
    s = pd.Series([1.0, np.nan, 3.0])
    assert not cross_sectional_zscore(s).isna().all()
