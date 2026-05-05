"""Smoke tests for the extracted industry helpers."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.analytics.industry.computations import (
    apply_historical_volatility,
    derive_size_source,
    scale_rank_score,
    weighted_std,
)


def test_derive_size_source_buckets():
    assert derive_size_source("snapshot_2026") == "snapshot"
    assert derive_size_source("sina_proxy_stock_sum") == "proxy"
    assert derive_size_source("unknown") == "estimated"
    assert derive_size_source("estimated_rough") == "estimated"
    assert derive_size_source("constant_fallback") == "estimated"
    assert derive_size_source("real_time_eastmoney") == "live"


def test_scale_rank_score_within_band():
    raw = pd.Series([1.0, 5.0, 10.0, 50.0, 100.0])
    out = scale_rank_score(raw)
    assert out.min() >= 20 and out.max() <= 95


def test_scale_rank_score_handles_constant_series():
    raw = pd.Series([7.0, 7.0, 7.0])
    out = scale_rank_score(raw)
    assert (out == 50.0).all()


def test_scale_rank_score_handles_empty():
    raw = pd.Series([], dtype=float)
    assert scale_rank_score(raw).empty


def test_weighted_std_falls_back_to_plain_std():
    values = np.array([1.0, 2.0, 3.0, 4.0])
    bad_weights = np.array([0.0, 0.0, 0.0, 0.0])
    assert weighted_std(values, bad_weights) == np.std(values)


def test_weighted_std_with_uniform_weights_matches_plain_std():
    values = np.array([1.0, 2.0, 3.0, 4.0])
    weights = np.ones_like(values)
    np.testing.assert_allclose(weighted_std(values, weights), np.std(values), atol=1e-9)


def test_weighted_std_handles_singleton():
    assert weighted_std(np.array([5.0]), np.array([1.0])) == 0.0


def test_apply_historical_volatility_overlays_real_values():
    df = pd.DataFrame(
        {
            "industry_name": ["A", "B"],
            "industry_volatility": [1.0, 2.0],
            "industry_volatility_source": ["proxy", "proxy"],
        }
    )
    history = pd.DataFrame(
        {"industry_name": ["A"], "industry_volatility": [9.9]}
    )
    out = apply_historical_volatility(df, history)
    assert out.loc[out["industry_name"] == "A", "industry_volatility"].iloc[0] == 9.9
    assert (
        out.loc[out["industry_name"] == "A", "industry_volatility_source"].iloc[0]
        == "historical_index"
    )
    # B should retain its proxy value
    assert out.loc[out["industry_name"] == "B", "industry_volatility"].iloc[0] == 2.0


def test_apply_historical_volatility_no_op_on_empty():
    df = pd.DataFrame({"industry_name": ["A"], "industry_volatility": [1.0]})
    out = apply_historical_volatility(df, pd.DataFrame())
    pd.testing.assert_frame_equal(out, df)
