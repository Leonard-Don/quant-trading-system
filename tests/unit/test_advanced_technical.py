"""Unit tests for advanced technical-indicator strategies.

These tests pin two correctness properties:

1. A strategy fed unambiguous data MUST emit the expected signal — a
   strategy that silently never trades is a bug, not a pass.
2. When signal generation hits a real internal error, the strategy must
   surface that error (re-raise) instead of swallowing it and returning an
   all-flat ``pd.Series(0, ...)``. A swallowed error looks identical to "the
   strategy decided not to trade", which masks defects. The old code also
   referenced ``self.logger`` inside the handler — an attribute
   ``BaseStrategy`` never sets — so the handler itself raised
   ``AttributeError``; the surfaced error must be the *original* one.
"""

import numpy as np
import pandas as pd
import pytest

from src.strategy.advanced_technical import (
    AdvancedTechnicalIndicators,
    CCIStrategy,
    IchimokuStrategy,
    MultiIndicatorStrategy,
    ParabolicSARStrategy,
    StochasticStrategy,
)


def _ohlcv(close, *, high=None, low=None, volume=None):
    """Build an OHLCV frame from a close series."""
    close = pd.Series(close, dtype=float)
    index = pd.date_range("2024-01-01", periods=len(close), freq="D")
    close.index = index
    high = close * 1.01 if high is None else pd.Series(high, index=index, dtype=float)
    low = close * 0.99 if low is None else pd.Series(low, index=index, dtype=float)
    volume = (
        pd.Series(1_000_000, index=index, dtype=float)
        if volume is None
        else pd.Series(volume, index=index, dtype=float)
    )
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume}
    )


class TestIchimokuStrategyBehaviour:
    def test_strong_uptrend_produces_a_buy_signal(self):
        """A long, clean uptrend pushes price above the cloud with tenkan
        over kijun and a lagging span above the 26-bar-ago price — every
        bullish condition met — so the strategy must emit at least one buy."""
        # 120 bars of monotonically rising price.
        close = np.linspace(100.0, 220.0, 120)
        data = _ohlcv(close)

        signals = IchimokuStrategy(name="Ichimoku").generate_signals(data)

        assert len(signals) == len(data)
        assert set(signals.dropna().unique()).issubset({-1, 0, 1})
        # The defining assertion: the strategy actually trades on this data.
        assert (signals == 1).any(), "clean uptrend must produce a buy signal"
        assert not (signals == -1).any(), "no short signals expected in an uptrend"

    def test_strong_downtrend_produces_a_sell_signal(self):
        close = np.linspace(220.0, 100.0, 120)
        data = _ohlcv(close)

        signals = IchimokuStrategy(name="Ichimoku").generate_signals(data)

        assert (signals == -1).any(), "clean downtrend must produce a sell signal"
        assert not (signals == 1).any()

    def test_internal_error_is_surfaced_not_swallowed(self):
        """A missing 'close' column is a real defect. The strategy must
        re-raise it (KeyError) — not return a silent all-zero series, and
        not raise AttributeError from a bogus self.logger reference."""
        index = pd.date_range("2024-01-01", periods=60, freq="D")
        broken = pd.DataFrame({"open": np.arange(60.0)}, index=index)

        with pytest.raises(KeyError):
            IchimokuStrategy(name="Ichimoku").generate_signals(broken)


class TestStochasticStrategyBehaviour:
    def test_oversold_golden_cross_produces_a_buy_signal(self):
        """Price collapses (driving %K deep into oversold) then snaps up,
        forcing a %K-over-%D golden cross below the oversold line."""
        down = np.linspace(100.0, 60.0, 40)
        up = np.linspace(60.5, 95.0, 20)
        data = _ohlcv(np.concatenate([down, up]))

        signals = StochasticStrategy(
            name="Stochastic", k_period=14, d_period=3, oversold=20, overbought=80
        ).generate_signals(data)

        assert len(signals) == len(data)
        assert (signals == 1).any(), "oversold golden cross must produce a buy"

    def test_internal_error_is_surfaced_not_swallowed(self):
        index = pd.date_range("2024-01-01", periods=60, freq="D")
        broken = pd.DataFrame({"open": np.arange(60.0)}, index=index)

        with pytest.raises(KeyError):
            StochasticStrategy(name="Stochastic").generate_signals(broken)


class TestCCIStrategyBehaviour:
    def test_recovery_from_oversold_produces_a_buy_signal(self):
        down = np.linspace(100.0, 70.0, 40)
        up = np.linspace(70.5, 110.0, 30)
        data = _ohlcv(np.concatenate([down, up]))

        signals = CCIStrategy(
            name="CCI", period=20, oversold=-100, overbought=100
        ).generate_signals(data)

        assert len(signals) == len(data)
        assert (signals == 1).any(), "CCI breakout up from oversold must buy"

    def test_internal_error_is_surfaced_not_swallowed(self):
        index = pd.date_range("2024-01-01", periods=60, freq="D")
        broken = pd.DataFrame({"open": np.arange(60.0)}, index=index)

        with pytest.raises(KeyError):
            CCIStrategy(name="CCI").generate_signals(broken)


class TestParabolicSARStrategyBehaviour:
    def test_trend_reversal_produces_signals(self):
        """A V-shaped price path forces SAR flips in both directions."""
        down = np.linspace(150.0, 90.0, 35)
        up = np.linspace(91.0, 160.0, 35)
        data = _ohlcv(np.concatenate([down, up]))

        signals = ParabolicSARStrategy(name="SAR").generate_signals(data)

        assert len(signals) == len(data)
        assert (signals != 0).any(), "a V-shaped path must trigger a SAR flip"

    def test_internal_error_is_surfaced_not_swallowed(self):
        index = pd.date_range("2024-01-01", periods=60, freq="D")
        broken = pd.DataFrame({"open": np.arange(60.0)}, index=index)

        with pytest.raises(KeyError):
            ParabolicSARStrategy(name="SAR").generate_signals(broken)


class TestMultiIndicatorStrategyBehaviour:
    def test_signals_stay_in_valid_range(self):
        np.random.seed(7)
        close = 100 * (1 + np.random.normal(0.0, 0.02, 120)).cumprod()
        data = _ohlcv(close)

        signals = MultiIndicatorStrategy(name="MultiIndicator").generate_signals(data)

        assert len(signals) == len(data)
        assert set(signals.dropna().unique()).issubset({-1, 0, 1})

    def test_internal_error_is_surfaced_not_swallowed(self):
        """generate_signals reads data['volume']; dropping it is a real
        defect and must raise, not silently return a flat series."""
        index = pd.date_range("2024-01-01", periods=60, freq="D")
        broken = pd.DataFrame({"close": np.arange(100.0, 160.0)}, index=index)

        with pytest.raises(KeyError):
            MultiIndicatorStrategy(name="MultiIndicator").generate_signals(broken)

    def test_signal_strength_error_is_surfaced_not_swallowed(self):
        index = pd.date_range("2024-01-01", periods=60, freq="D")
        broken = pd.DataFrame({"open": np.arange(60.0)}, index=index)

        with pytest.raises(KeyError):
            MultiIndicatorStrategy(name="MultiIndicator").get_signal_strength(broken)


class TestAdvancedTechnicalIndicators:
    def test_williams_r_is_bounded(self):
        data = _ohlcv(np.linspace(100.0, 130.0, 40))
        wr = AdvancedTechnicalIndicators.williams_r(
            data["high"], data["low"], data["close"], period=14
        )
        bounded = wr.dropna()
        assert (bounded >= -100.0).all()
        assert (bounded <= 0.0).all()
