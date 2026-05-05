"""Smoke tests for src.analytics.technical_indicators."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analytics.technical_indicators import (
    calculate_bollinger,
    calculate_macd,
    calculate_rsi,
)


@pytest.fixture
def trending_up_df() -> pd.DataFrame:
    return pd.DataFrame({"close": np.linspace(100, 130, 60)})


@pytest.fixture
def trending_down_df() -> pd.DataFrame:
    return pd.DataFrame({"close": np.linspace(130, 100, 60)})


@pytest.fixture
def flat_df() -> pd.DataFrame:
    return pd.DataFrame({"close": np.full(60, 100.0)})


def test_rsi_returns_expected_keys(trending_up_df):
    result = calculate_rsi(trending_up_df)
    assert set(result.keys()) == {"value", "status", "signal"}
    assert 0 <= result["value"] <= 100
    assert result["status"] in {"overbought", "oversold", "neutral"}


def test_rsi_flags_overbought_on_strong_uptrend(trending_up_df):
    result = calculate_rsi(trending_up_df)
    assert result["status"] == "overbought"


def test_rsi_flags_oversold_on_strong_downtrend(trending_down_df):
    result = calculate_rsi(trending_down_df)
    assert result["status"] == "oversold"


def test_macd_returns_expected_keys(trending_up_df):
    result = calculate_macd(trending_up_df)
    assert set(result.keys()) == {"value", "signal_line", "histogram", "status", "trend"}
    assert result["status"] in {"bullish", "bearish", "neutral"}


def test_macd_bullish_on_uptrend(trending_up_df):
    result = calculate_macd(trending_up_df)
    assert result["status"] == "bullish"


def test_bollinger_returns_expected_keys(trending_up_df):
    result = calculate_bollinger(trending_up_df)
    assert set(result.keys()) == {
        "upper",
        "middle",
        "lower",
        "current_price",
        "position",
        "bandwidth",
        "signal",
    }
    assert result["upper"] >= result["middle"] >= result["lower"]


def test_bollinger_position_in_uptrend(trending_up_df):
    result = calculate_bollinger(trending_up_df)
    assert result["position"] in {"above_upper", "upper_half"}


def test_indicators_handle_flat_series(flat_df):
    rsi = calculate_rsi(flat_df)
    macd = calculate_macd(flat_df)
    bb = calculate_bollinger(flat_df)
    assert isinstance(rsi["value"], (int, float))
    assert isinstance(macd["value"], (int, float))
    assert bb["upper"] == bb["middle"] == bb["lower"]
