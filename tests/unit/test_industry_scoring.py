"""Tests for industry.scoring — pure rank-score helpers extracted from IndustryAnalyzer."""

import pandas as pd
import pytest

from src.analytics.industry.scoring import (
    build_rank_score_breakdown,
    calculate_rank_score_series,
)

DEFAULT_WEIGHTS = {
    "momentum": 0.35,
    "money_flow": 0.35,
    "volume_change": 0.15,
    "volatility": -0.15,
}


def test_calculate_rank_score_series_empty_df_returns_empty():
    result = calculate_rank_score_series(pd.DataFrame(), DEFAULT_WEIGHTS)
    assert result.empty


def test_calculate_rank_score_series_no_recognized_columns_is_neutral():
    df = pd.DataFrame({"unrelated_column": [1.0, 2.0, 3.0]})
    result = calculate_rank_score_series(df, DEFAULT_WEIGHTS)
    assert list(result) == [50.0, 50.0, 50.0]


def test_calculate_rank_score_series_scales_into_20_95_band():
    df = pd.DataFrame({"change_pct": [-3.0, 0.0, 5.0]})
    result = calculate_rank_score_series(df, DEFAULT_WEIGHTS)
    assert len(result) == 3
    assert result.min() == pytest.approx(20.0)
    assert result.max() == pytest.approx(95.0)


def test_build_rank_score_breakdown_empty_record_returns_empty():
    assert build_rank_score_breakdown({}, DEFAULT_WEIGHTS) == []


def test_build_rank_score_breakdown_has_six_dimensions():
    record = {
        "change_pct": 3.0,
        "flow_strength": 1.5,
        "turnover_rate": 8.0,
        "industry_volatility": 2.5,
        "total_market_cap": 5e10,
        "score": 72.0,
    }
    breakdown = build_rank_score_breakdown(record, DEFAULT_WEIGHTS)
    assert [d["key"] for d in breakdown] == [
        "momentum",
        "money_flow",
        "volume_change",
        "volatility",
        "scale",
        "total_score",
    ]
    for dim in breakdown:
        assert 0 <= dim["value"] <= 100
        assert set(dim) == {"dimension", "key", "value", "weight", "metric", "metric_label"}


def test_build_rank_score_breakdown_weights_passthrough():
    weights = {"momentum": 0.5, "money_flow": 0.3, "volume_change": 0.1, "volatility": -0.2}
    by_key = {d["key"]: d for d in build_rank_score_breakdown({"change_pct": 1.0}, weights)}
    assert by_key["momentum"]["weight"] == 0.5
    assert by_key["volatility"]["weight"] == 0.2  # abs() applied to the negative weight
