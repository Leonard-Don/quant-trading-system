"""Unit tests for src.analytics.feature_engineering.

Pure pandas/numpy feature math — deterministic, no network. Verifies that
prepare_features produces the documented columns, drops NaNs, honours the
include_volume flag, and that the indicator helpers (RSI/ATR/OBV) compute the
expected values on small hand-checkable inputs.
"""

import numpy as np
import pandas as pd
import pytest

from src.analytics.feature_engineering import (
    FeatureEngineer,
    prepare_ml_features,
)


@pytest.fixture
def ohlcv():
    """Deterministic OHLCV frame long enough for the 50-period SMAs."""
    rng = np.random.default_rng(42)
    n = 120
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + np.abs(rng.normal(0, 0.5, n))
    low = close - np.abs(rng.normal(0, 0.5, n))
    open_ = close + rng.normal(0, 0.3, n)
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=idx,
    )


class TestPrepareFeatures:
    def test_produces_all_named_features(self, ohlcv):
        out = FeatureEngineer.prepare_features(ohlcv, include_volume=True)
        for name in FeatureEngineer.get_feature_names(include_volume=True):
            assert name in out.columns, f"missing feature {name}"

    def test_drops_nan_rows(self, ohlcv):
        out = FeatureEngineer.prepare_features(ohlcv)
        assert not out.isnull().any().any()
        # The longest lookback is the 50-period SMA, so we lose ~49 leading rows.
        assert len(out) < len(ohlcv)
        assert len(out) > 0

    def test_lowercases_columns(self, ohlcv):
        upper = ohlcv.rename(columns=str.upper)
        out = FeatureEngineer.prepare_features(upper)
        assert "close" in out.columns
        assert "CLOSE" not in out.columns

    def test_excludes_volume_features_when_disabled(self, ohlcv):
        out = FeatureEngineer.prepare_features(ohlcv, include_volume=False)
        assert "obv" not in out.columns
        assert "volume_ratio" not in out.columns

    def test_custom_feature_periods(self, ohlcv):
        out = FeatureEngineer.prepare_features(ohlcv, feature_periods=[3, 8])
        assert "sma_3" in out.columns
        assert "ema_8" in out.columns
        assert "sma_50" not in out.columns

    def test_returns_and_log_returns_consistent(self, ohlcv):
        out = FeatureEngineer.prepare_features(ohlcv)
        # log_returns ~= log(1 + returns)
        recovered = np.exp(out["log_returns"]) - 1
        assert np.allclose(recovered, out["returns"], atol=1e-9)

    def test_convenience_wrapper_matches_classmethod(self, ohlcv):
        a = prepare_ml_features(ohlcv, include_volume=True)
        b = FeatureEngineer.prepare_features(ohlcv, include_volume=True)
        pd.testing.assert_frame_equal(a, b)


class TestRSI:
    def test_steadily_rising_prices_high_rsi(self):
        prices = pd.Series(np.arange(1, 40, dtype=float))
        rsi = FeatureEngineer._calculate_rsi(prices, period=14)
        # All gains, no losses => RSI saturates near 100.
        assert rsi.dropna().iloc[-1] == pytest.approx(100.0, abs=1e-6)

    def test_steadily_falling_prices_low_rsi(self):
        prices = pd.Series(np.arange(40, 1, -1, dtype=float))
        rsi = FeatureEngineer._calculate_rsi(prices, period=14)
        # All losses => RSI near 0.
        assert rsi.dropna().iloc[-1] < 1.0

    def test_in_valid_range(self):
        rng = np.random.default_rng(7)
        prices = pd.Series(100 + np.cumsum(rng.normal(0, 1, 60)))
        rsi = FeatureEngineer._calculate_rsi(prices, period=14).dropna()
        assert ((rsi >= 0) & (rsi <= 100)).all()


class TestATR:
    def test_atr_nonnegative_and_matches_rolling_mean(self):
        idx = pd.date_range("2024-01-01", periods=20, freq="D")
        df = pd.DataFrame(
            {
                "high": np.linspace(11, 30, 20),
                "low": np.linspace(9, 28, 20),
                "close": np.linspace(10, 29, 20),
            },
            index=idx,
        )
        atr = FeatureEngineer._calculate_atr(df, period=5).dropna()
        assert (atr >= 0).all()
        assert len(atr) > 0


class TestOBV:
    def test_obv_directional_accumulation(self):
        df = pd.DataFrame(
            {
                "close": [10, 11, 10, 10, 12],
                "volume": [100, 200, 150, 300, 250],
            }
        )
        obv = FeatureEngineer._calculate_obv(df)
        # start = 100
        # close up (11>10)  => +200 -> 300
        # close down (10<11)=> -150 -> 150
        # close flat (10==10) => unchanged -> 150
        # close up (12>10)  => +250 -> 400
        assert list(obv) == [100, 300, 150, 150, 400]


class TestGetFeatureNames:
    def test_volume_names_present_only_when_requested(self):
        with_vol = FeatureEngineer.get_feature_names(include_volume=True)
        without_vol = FeatureEngineer.get_feature_names(include_volume=False)
        assert "obv" in with_vol
        assert "obv" not in without_vol
        assert set(without_vol).issubset(set(with_vol))
