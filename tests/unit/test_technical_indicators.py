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


def test_rsi_falls_back_to_neutral_when_data_too_short_for_window():
    short = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
    result = calculate_rsi(short)
    assert result["value"] == 50
    assert result["status"] == "neutral"


def test_rsi_pinned_to_zero_with_only_losses(trending_down_df):
    result = calculate_rsi(trending_down_df)
    assert result["value"] == 0.0
    assert result["status"] == "oversold"


def test_rsi_pinned_to_one_hundred_with_only_gains(trending_up_df):
    result = calculate_rsi(trending_up_df)
    assert result["value"] == 100.0


def test_rsi_status_neutral_for_bounded_choppy_series():
    rng = np.random.default_rng(7)
    closes = 100 + np.cumsum(rng.uniform(-0.5, 0.5, 50))
    result = calculate_rsi(pd.DataFrame({"close": closes}))
    assert result["status"] == "neutral"
    assert 30 <= result["value"] <= 70


def test_rsi_respects_custom_periods():
    short = pd.DataFrame({"close": [100.0, 101.0, 102.0, 103.0, 104.0]})
    fallback = calculate_rsi(short)
    custom = calculate_rsi(short, periods=2)
    assert fallback["value"] == 50
    assert custom["value"] == 100.0


def test_macd_bearish_on_downtrend(trending_down_df):
    result = calculate_macd(trending_down_df)
    assert result["status"] == "bearish"
    assert result["histogram"] < 0
    assert result["value"] < result["signal_line"]
    assert result["trend"] in {"加速下跌", "下跌减速"}


def test_macd_neutral_status_on_flat_series(flat_df):
    result = calculate_macd(flat_df)
    assert result["status"] == "neutral"
    assert result["trend"] == "横盘整理"
    assert result["value"] == 0
    assert result["histogram"] == 0


def test_macd_handles_single_row_input():
    single = pd.DataFrame({"close": [100.0]})
    result = calculate_macd(single)
    assert result == {
        "value": 0.0,
        "signal_line": 0.0,
        "histogram": 0.0,
        "status": "neutral",
        "trend": "横盘整理",
    }


def test_bollinger_above_upper_on_sudden_spike():
    closes = np.concatenate([np.full(50, 100.0), [200.0]])
    result = calculate_bollinger(pd.DataFrame({"close": closes}))
    assert result["position"] == "above_upper"
    assert result["current_price"] >= result["upper"]


def test_bollinger_below_lower_on_sudden_drop():
    closes = np.concatenate([np.full(50, 100.0), [50.0]])
    result = calculate_bollinger(pd.DataFrame({"close": closes}))
    assert result["position"] == "below_lower"
    assert result["current_price"] <= result["lower"]


def test_bollinger_lower_half_on_downtrend(trending_down_df):
    result = calculate_bollinger(trending_down_df)
    assert result["position"] == "lower_half"
    assert result["lower"] < result["current_price"] <= result["middle"]


def test_bollinger_respects_custom_periods():
    closes = pd.DataFrame({"close": [100.0, 101.0, 102.0, 103.0, 104.0]})
    custom = calculate_bollinger(closes, periods=3)
    assert custom["middle"] == round((102 + 103 + 104) / 3, 2)
    assert custom["upper"] > custom["middle"] > custom["lower"]
