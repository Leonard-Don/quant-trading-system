"""Wilder-smoothing (RMA) correctness tests for TrendAnalyzer indicators.

The standard textbook definitions used by every charting platform
(同花顺 / TradingView / Tushare) compute RSI, ATR and ADX/+DI/-DI with
Wilder's smoothing (RMA = exponential moving average with alpha = 1/period,
adjust=False), NOT a simple rolling mean.

These tests pin the indicators in ``src/analytics/trend_analyzer.py`` to that
canonical definition by comparing against an independent reference
implementation written here from scratch.
"""

import numpy as np
import pandas as pd

from src.analytics.trend_analyzer import TrendAnalyzer

PERIOD = 14


def _make_ohlcv(close: np.ndarray) -> pd.DataFrame:
    """Build a deterministic OHLCV frame around a close series."""
    n = len(close)
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    high = close + 0.8
    low = close - 0.8
    return pd.DataFrame(
        {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.full(n, 1_000_000),
        },
        index=dates,
    )


def _rma(series: pd.Series, period: int = PERIOD) -> pd.Series:
    """Wilder's smoothing / running moving average."""
    return series.ewm(alpha=1.0 / period, adjust=False).mean()


def _reference_rsi(close: pd.Series, period: int = PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = _rma(gain, period)
    avg_loss = _rma(loss, period)
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    # all-gain window -> RSI 100
    rsi = rsi.where(avg_loss != 0, 100.0)
    return rsi


def _reference_atr(df: pd.DataFrame, period: int = PERIOD) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return _rma(tr, period)


def _reference_adx(df: pd.DataFrame, period: int = PERIOD):
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    high_diff = high.diff()
    low_diff = -low.diff()
    pos_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
    neg_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)

    atr = _rma(tr, period)
    pos_di = 100 * (_rma(pos_dm, period) / atr)
    neg_di = 100 * (_rma(neg_dm, period) / atr)
    dx = 100 * (pos_di - neg_di).abs() / (pos_di + neg_di)
    adx = _rma(dx, period)
    return adx, pos_di, neg_di


class TestWilderSmoothing:
    """Pin TrendAnalyzer indicators to Wilder's RMA definition."""

    def setup_method(self):
        self.analyzer = TrendAnalyzer()
        rng = np.random.default_rng(7)
        n = 120
        # random-walk close that exercises both gains and losses
        steps = rng.normal(0, 1.0, size=n)
        self.close = pd.Series(50 + np.cumsum(steps))
        self.df = _make_ohlcv(self.close.to_numpy())

    def test_rsi_matches_wilder(self):
        _, indicators = self.analyzer._calculate_technical_score(self.df)
        expected = float(_reference_rsi(self.df["close"]).iloc[-1])
        assert indicators["rsi"] == round(expected, 2)

    def test_atr_matches_wilder(self):
        result = self.analyzer._analyze_volatility(self.df)
        expected = float(_reference_atr(self.df).iloc[-1])
        assert result["atr"] == round(expected, 2)

    def test_adx_and_di_match_wilder(self):
        _, indicators = self.analyzer._calculate_technical_score(self.df)
        adx, pos_di, neg_di = _reference_adx(self.df)
        assert indicators["adx"] == round(float(adx.iloc[-1]), 2)
        assert indicators["plus_di"] == round(float(pos_di.iloc[-1]), 2)
        assert indicators["minus_di"] == round(float(neg_di.iloc[-1]), 2)

    def test_signal_strength_rsi_matches_wilder(self):
        # signal-strength path computes RSI independently; pin it too.
        # Build a strongly oversold series so RSI < 30 under Wilder.
        falling = pd.Series(np.linspace(100, 40, 80))
        df = _make_ohlcv(falling.to_numpy())
        expected_rsi = float(_reference_rsi(df["close"]).iloc[-1])
        # A monotonically falling series -> avg_gain ~ 0 -> RSI near 0.
        assert expected_rsi < 30
        result = self.analyzer._calculate_signal_strength(df, "bearish")
        # With RSI < 30 the RSI sub-signal must count as a buy (oversold).
        assert result["buy_indicators"] >= 1

    def test_rsi_all_gains_is_100(self):
        """A strictly rising series has no losses -> Wilder RSI saturates to 100."""
        rising = pd.Series(np.linspace(40, 100, 80))
        df = _make_ohlcv(rising.to_numpy())
        _, indicators = self.analyzer._calculate_technical_score(df)
        assert indicators["rsi"] == 100.0

    def test_wilder_differs_from_sma_on_known_series(self):
        """Guard against regression to simple-rolling-mean smoothing.

        On a non-stationary series, Wilder RMA and a 14-period SMA give
        materially different RSI values; assert the analyzer follows RMA.
        """
        close = self.df["close"]
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        sma_rs = gain.rolling(14).mean() / loss.rolling(14).mean()
        sma_rsi = float((100 - 100 / (1 + sma_rs)).iloc[-1])
        wilder_rsi = float(_reference_rsi(close).iloc[-1])
        assert abs(sma_rsi - wilder_rsi) > 0.5  # sanity: they really differ

        _, indicators = self.analyzer._calculate_technical_score(self.df)
        assert indicators["rsi"] == round(wilder_rsi, 2)
        assert indicators["rsi"] != round(sma_rsi, 2)
