"""Unit tests for src.analytics.pattern_recognizer.

The recognizer is pure numpy/pandas — it consumes OHLC DataFrames and returns
pattern dicts. Every input here is hand-constructed so the expected pattern can
be verified by reading the detection thresholds in the source. No network, no
external state.

Important argument-order note for the three-candle helpers: they are *called*
in the source as ``_check_...(current, prev1, prev2)`` but their signature is
``(candle3, candle2, candle1)``. So inside the helper ``candle1`` is the OLDEST
bar and ``candle3`` is the NEWEST. Tests call the helpers directly with that
``(newest, middle, oldest)`` ordering to match production usage.
"""

import numpy as np
import pandas as pd
import pytest

from src.analytics.pattern_recognizer import PatternRecognizer


def candle(open_, high, low, close, name="2024-01-01"):
    """Build a single OHLC bar as a named Series (mimics df.iloc[i])."""
    return pd.Series(
        {"open": open_, "high": high, "low": low, "close": close},
        name=pd.Timestamp(name),
    )


def ohlc_df(rows, start="2024-01-01"):
    """Build an OHLC DataFrame from a list of (open, high, low, close) tuples."""
    idx = pd.date_range(start=start, periods=len(rows), freq="D")
    return pd.DataFrame(
        rows, columns=["open", "high", "low", "close"], index=idx
    )


@pytest.fixture
def rec():
    return PatternRecognizer()


# --------------------------------------------------------------------------- #
# Configuration / construction
# --------------------------------------------------------------------------- #
class TestConfig:
    def test_defaults_applied(self, rec):
        assert rec.doji_threshold == 0.15
        assert rec.max_patterns == 5
        assert rec.candlestick_window == 30
        assert rec.chart_pattern_window == 60
        assert rec.price_tolerance == 0.05
        assert rec.engulfing_ratio == 1.2

    def test_scalar_override(self):
        r = PatternRecognizer({"max_patterns": 10, "doji_threshold": 0.2})
        assert r.max_patterns == 10
        assert r.doji_threshold == 0.2
        # untouched keys keep defaults
        assert r.candlestick_window == 30

    def test_nested_dict_override_merges(self):
        r = PatternRecognizer({"peak_detection_window": {"short": 3}})
        # 'short' overridden, 'long' preserved from default
        assert r.peak_detection_window == {"short": 3, "long": 10}

    def test_default_nested_dict_not_mutated_across_instances(self):
        r1 = PatternRecognizer({"peak_detection_window": {"short": 1}})
        r2 = PatternRecognizer()
        assert r1.peak_detection_window["short"] == 1
        # the second instance must still see the pristine default
        assert r2.peak_detection_window["short"] == 5


# --------------------------------------------------------------------------- #
# recognize_patterns top-level
# --------------------------------------------------------------------------- #
class TestRecognizeTopLevel:
    def test_empty_df_returns_zero(self, rec):
        out = rec.recognize_patterns(pd.DataFrame())
        assert out == {
            "candlestick_patterns": [],
            "chart_patterns": [],
            "total_patterns": 0,
        }

    def test_too_few_rows_returns_zero(self, rec):
        df = ohlc_df([(10, 11, 9, 10)] * 9)  # 9 < 10
        out = rec.recognize_patterns(df)
        assert out["total_patterns"] == 0

    def test_total_is_sum_of_both_lists(self, rec):
        # 15 flat-ish bars: enough rows to run candlestick path but no strong
        # chart pattern (chart path needs >= 20 rows, so it returns []).
        rows = [(10, 10.2, 9.8, 10.0) for _ in range(15)]
        df = ohlc_df(rows)
        out = rec.recognize_patterns(df)
        assert out["total_patterns"] == len(out["candlestick_patterns"]) + len(
            out["chart_patterns"]
        )
        # chart path short-circuits below 20 rows
        assert out["chart_patterns"] == []


# --------------------------------------------------------------------------- #
# Doji
# --------------------------------------------------------------------------- #
class TestDoji:
    def test_doji_detected_tiny_body(self, rec):
        # body=0.1, range=4.0 -> 0.025 < 0.15 => doji
        c = candle(100.0, 102.0, 98.0, 100.1)
        out = rec._check_doji(c)
        assert out is not None
        assert out["pattern"] == "doji"
        assert out["signal"] == "reversal"

    def test_not_doji_large_body(self, rec):
        # body=3.0, range=4.0 -> 0.75 not < 0.15
        c = candle(100.0, 102.0, 98.0, 103.0)
        # high must be >= close; fix range
        c = candle(98.0, 102.0, 98.0, 101.5)  # body 3.5 / range 4 = 0.875
        assert rec._check_doji(c) is None

    def test_zero_range_returns_none(self, rec):
        c = candle(100.0, 100.0, 100.0, 100.0)
        assert rec._check_doji(c) is None


# --------------------------------------------------------------------------- #
# Hammer / Hanging man
# --------------------------------------------------------------------------- #
class TestHammer:
    def test_hammer_after_downtrend_is_bullish(self, rec):
        # long lower shadow, tiny upper shadow, small body at top.
        # open=100, close=100.5 -> body=0.5; low=95 -> lower shadow ~ 5;
        # high=100.6 -> upper shadow ~0.1; range=5.6 body/range~0.089<0.3
        current = candle(100.0, 100.6, 95.0, 100.5)
        prev_down = candle(105.0, 105.0, 100.0, 101.0)  # prev close < open => down
        out = rec._check_hammer(current, prev_down)
        assert out is not None
        assert out["pattern"] == "hammer"
        assert out["signal"] == "bullish_reversal"

    def test_hanging_man_after_uptrend_is_bearish(self, rec):
        current = candle(100.0, 100.6, 95.0, 100.5)
        prev_up = candle(100.0, 106.0, 100.0, 105.0)  # prev close > open => up
        out = rec._check_hammer(current, prev_up)
        assert out is not None
        assert out["pattern"] == "hanging_man"
        assert out["signal"] == "bearish_reversal"

    def test_no_hammer_when_shadows_balanced(self, rec):
        current = candle(100.0, 103.0, 97.0, 101.0)  # symmetric-ish, big body
        prev = candle(100.0, 101.0, 99.0, 100.5)
        assert rec._check_hammer(current, prev) is None

    def test_zero_range_returns_none(self, rec):
        current = candle(100.0, 100.0, 100.0, 100.0)
        prev = candle(100.0, 101.0, 99.0, 99.5)
        assert rec._check_hammer(current, prev) is None


# --------------------------------------------------------------------------- #
# Engulfing
# --------------------------------------------------------------------------- #
class TestEngulfing:
    def test_bullish_engulfing(self, rec):
        prev = candle(100.0, 100.0, 97.0, 98.0)  # bearish, body=2
        curr = candle(97.5, 102.0, 97.0, 101.0)  # bullish, body=3.5 > 2*1.2
        # curr_open(97.5) < prev_close(98) and curr_close(101) > prev_open(100)
        out = rec._check_engulfing(curr, prev)
        assert out is not None
        assert out["pattern"] == "bullish_engulfing"

    def test_bearish_engulfing(self, rec):
        prev = candle(98.0, 101.0, 98.0, 100.0)  # bullish, body=2
        curr = candle(100.5, 101.0, 96.0, 97.0)  # bearish, body=3.5 > 2*1.2
        # curr_open(100.5) > prev_close(100) and curr_close(97) < prev_open(98)
        out = rec._check_engulfing(curr, prev)
        assert out is not None
        assert out["pattern"] == "bearish_engulfing"

    def test_no_engulf_when_body_not_big_enough(self, rec):
        prev = candle(100.0, 100.0, 97.0, 98.0)  # bearish body=2
        curr = candle(97.9, 100.2, 97.5, 100.1)  # bullish body=2.2 < 2*1.2=2.4
        assert rec._check_engulfing(curr, prev) is None

    def test_no_engulf_same_direction(self, rec):
        prev = candle(98.0, 101.0, 98.0, 100.0)  # bullish
        curr = candle(99.0, 103.0, 99.0, 102.0)  # bullish too
        assert rec._check_engulfing(curr, prev) is None


# --------------------------------------------------------------------------- #
# Morning / Evening star (3-candle). Helper sig is (candle3, candle2, candle1)
# with candle1 oldest, candle3 newest.
# --------------------------------------------------------------------------- #
class TestStar:
    def test_morning_star(self, rec):
        c1_old = candle(110.0, 110.0, 99.0, 100.0)  # bearish, body=10
        c2_mid = candle(99.0, 100.0, 98.0, 99.5)  # small body=0.5 < 10*0.3
        c3_new = candle(100.0, 112.0, 100.0, 111.0)  # bullish, close>mid(105)
        out = rec._check_morning_evening_star(c3_new, c2_mid, c1_old)
        assert out is not None
        assert out["pattern"] == "morning_star"
        assert out["signal"] == "bullish_reversal"

    def test_evening_star(self, rec):
        c1_old = candle(100.0, 110.0, 100.0, 110.0)  # bullish, body=10
        c2_mid = candle(110.0, 111.0, 109.5, 110.3)  # small body=0.3
        c3_new = candle(110.0, 110.0, 98.0, 99.0)  # bearish, close<mid(105)
        out = rec._check_morning_evening_star(c3_new, c2_mid, c1_old)
        assert out is not None
        assert out["pattern"] == "evening_star"
        assert out["signal"] == "bearish_reversal"

    def test_no_star_when_middle_body_large(self, rec):
        c1_old = candle(110.0, 110.0, 99.0, 100.0)  # bearish body=10
        c2_mid = candle(99.0, 106.0, 98.0, 105.0)  # body=6 > 10*0.3=3
        c3_new = candle(100.0, 112.0, 100.0, 111.0)
        assert rec._check_morning_evening_star(c3_new, c2_mid, c1_old) is None


# --------------------------------------------------------------------------- #
# Three soldiers / three crows
# --------------------------------------------------------------------------- #
class TestThreeBar:
    def test_three_white_soldiers(self, rec):
        c1 = candle(100.0, 103.0, 99.0, 102.0)  # bullish
        c2 = candle(102.0, 105.0, 101.0, 104.0)  # bullish, higher close
        c3 = candle(104.0, 107.0, 103.0, 106.0)  # bullish, higher close
        out = rec._check_three_soldiers_crows(c3, c2, c1)
        assert out is not None
        assert out["pattern"] == "three_white_soldiers"
        assert out["signal"] == "bullish_continuation"

    def test_three_black_crows(self, rec):
        c1 = candle(106.0, 107.0, 103.0, 104.0)  # bearish
        c2 = candle(104.0, 105.0, 101.0, 102.0)  # bearish, lower close
        c3 = candle(102.0, 103.0, 99.0, 100.0)  # bearish, lower close
        out = rec._check_three_soldiers_crows(c3, c2, c1)
        assert out is not None
        assert out["pattern"] == "three_black_crows"
        assert out["signal"] == "bearish_continuation"

    def test_mixed_returns_none(self, rec):
        c1 = candle(100.0, 103.0, 99.0, 102.0)  # bullish
        c2 = candle(102.0, 103.0, 99.0, 100.0)  # bearish
        c3 = candle(100.0, 103.0, 99.0, 101.0)  # bullish but not ascending
        assert rec._check_three_soldiers_crows(c3, c2, c1) is None


# --------------------------------------------------------------------------- #
# Chart patterns: double top / double bottom
# --------------------------------------------------------------------------- #
class TestDoubleTopBottom:
    def test_short_series_returns_none(self, rec):
        s = pd.Series(range(40), index=pd.date_range("2024-01-01", periods=40))
        assert rec._check_double_top_bottom(s, s, s) is None

    def test_double_top_detected(self, rec):
        # Construct 70 bars with two near-equal peaks separated by a trough.
        n = 70
        base = np.full(n, 100.0)
        # peak around index 20 and 50, both ~ 120, trough ~ 100 between.
        for i in range(n):
            # a smooth-ish double hump
            base[i] = 100.0
        base[20] = 120.0
        base[50] = 120.5  # within 5% of 120
        # make these the local maxima of their +-5 window by depressing nbrs
        idx = pd.date_range("2024-01-01", periods=n)
        high = pd.Series(base, index=idx)
        low = pd.Series(np.full(n, 95.0), index=idx)
        close = high.copy()
        out = rec._check_double_top_bottom(close, high, low)
        assert out is not None
        assert out["pattern"] == "double_top"
        assert out["signal"] == "bearish_reversal"
        # three labelled points
        kinds = {p["type"] for p in out["points"]}
        assert kinds == {"peak1", "neckline", "peak2"}

    def test_double_bottom_detected(self, rec):
        n = 70
        idx = pd.date_range("2024-01-01", periods=n)
        # Gently *rising* highs so no two near-equal local-max peaks form -> the
        # double-top branch finds nothing and we fall through to double-bottom.
        high = pd.Series(np.linspace(108.0, 112.0, n), index=idx)
        low_arr = np.full(n, 100.0)
        low_arr[20] = 90.0
        low_arr[50] = 90.3  # within 5%
        low = pd.Series(low_arr, index=idx)
        close = low.copy()
        out = rec._check_double_top_bottom(close, high, low)
        assert out is not None
        assert out["pattern"] == "double_bottom"
        assert out["signal"] == "bullish_reversal"


# --------------------------------------------------------------------------- #
# Triangle
# --------------------------------------------------------------------------- #
class TestTriangle:
    def test_ascending_triangle(self, rec):
        n = 30
        idx = pd.date_range("2024-01-01", periods=n)
        # flat highs, rising lows
        high = pd.Series(np.full(n, 120.0), index=idx)
        low = pd.Series(np.linspace(100.0, 110.0, n), index=idx)  # slope ~0.34
        close = (high + low) / 2
        out = rec._check_triangle(close, high, low)
        assert out is not None
        assert out["pattern"] == "ascending_triangle"

    def test_descending_triangle(self, rec):
        n = 30
        idx = pd.date_range("2024-01-01", periods=n)
        # flat lows, falling highs
        low = pd.Series(np.full(n, 100.0), index=idx)
        high = pd.Series(np.linspace(120.0, 110.0, n), index=idx)  # slope ~ -0.34
        close = (high + low) / 2
        out = rec._check_triangle(close, high, low)
        assert out is not None
        assert out["pattern"] == "descending_triangle"

    def test_symmetrical_triangle(self, rec):
        n = 30
        idx = pd.date_range("2024-01-01", periods=n)
        high = pd.Series(np.linspace(120.0, 112.0, n), index=idx)  # falling
        low = pd.Series(np.linspace(100.0, 108.0, n), index=idx)  # rising
        close = (high + low) / 2
        out = rec._check_triangle(close, high, low)
        assert out is not None
        assert out["pattern"] == "symmetrical_triangle"

    def test_no_triangle_flat(self, rec):
        n = 30
        idx = pd.date_range("2024-01-01", periods=n)
        high = pd.Series(np.full(n, 120.0), index=idx)
        low = pd.Series(np.full(n, 100.0), index=idx)
        close = (high + low) / 2
        assert rec._check_triangle(close, high, low) is None

    def test_short_series_returns_none(self, rec):
        s = pd.Series(range(20), index=pd.date_range("2024-01-01", periods=20))
        assert rec._check_triangle(s, s, s) is None


# --------------------------------------------------------------------------- #
# Flag
# --------------------------------------------------------------------------- #
class TestFlag:
    def test_bull_flag(self, rec):
        # A genuine bull flag: a strong prior RISE (the flagpole, from ~30 bars
        # ago into the consolidation) followed by a tight recent range.
        # early_trend measures the flagpole and must be POSITIVE for a bull flag.
        n = 30
        idx = pd.date_range("2024-01-01", periods=n)
        close = np.empty(n)
        # Flagpole: rise from 100 -> 120 over the first 20 bars.
        close[:20] = np.linspace(100.0, 120.0, 20)
        # Consolidation: last 10 bars hold tightly near 120 (range/close < 0.05).
        close[20:] = 120.0
        close_s = pd.Series(close, index=idx)
        high = close_s + 0.5
        low = close_s - 0.5
        out = rec._check_flag(close_s, high, low)
        assert out is not None
        assert out["pattern"] == "bull_flag"

    def test_bear_flag(self, rec):
        # A genuine bear flag: a strong prior DECLINE (flagpole down) followed by
        # a tight recent range. early_trend must be NEGATIVE for a bear flag.
        n = 30
        idx = pd.date_range("2024-01-01", periods=n)
        close = np.empty(n)
        # Flagpole: drop from 100 -> 80 over the first 20 bars.
        close[:20] = np.linspace(100.0, 80.0, 20)
        # Consolidation: last 10 bars hold tightly near 80.
        close[20:] = 80.0
        close_s = pd.Series(close, index=idx)
        high = close_s + 0.5
        low = close_s - 0.5
        out = rec._check_flag(close_s, high, low)
        assert out is not None
        assert out["pattern"] == "bear_flag"

    def test_no_flag_when_recent_range_wide(self, rec):
        n = 30
        idx = pd.date_range("2024-01-01", periods=n)
        close = np.empty(n)
        close[:20] = np.linspace(100.0, 120.0, 20)  # strong prior rise
        close[20:] = 120.0
        close_s = pd.Series(close, index=idx)
        high = close_s + 5.0  # wide recent range
        low = close_s - 5.0
        assert rec._check_flag(close_s, high, low) is None


# --------------------------------------------------------------------------- #
# Head & shoulders (exercise the short-circuit + a constructed top)
# --------------------------------------------------------------------------- #
class TestHeadShoulders:
    def test_short_series_returns_none(self, rec):
        s = pd.Series(range(40), index=pd.date_range("2024-01-01", periods=40))
        assert rec._check_head_shoulders(s, s, s) is None

    def test_head_shoulders_top(self, rec):
        n = 70
        idx = pd.date_range("2024-01-01", periods=n)
        high_arr = np.full(n, 100.0)
        # three peaks: left & right equal-ish (lower), head higher, spaced >10
        high_arr[25] = 110.0  # left shoulder (tail-60 idx 15)
        high_arr[40] = 120.0  # head, highest (tail-60 idx 30)
        high_arr[55] = 110.2  # right shoulder, within 5% of left (tail-60 idx 45)
        high = pd.Series(high_arr, index=idx)
        low = pd.Series(np.full(n, 90.0), index=idx)
        close = high.copy()
        out = rec._check_head_shoulders(close, high, low)
        assert out is not None
        assert out["pattern"] == "head_shoulders_top"
        assert out["signal"] == "bearish_reversal"


# --------------------------------------------------------------------------- #
# End-to-end on a realistic frame
# --------------------------------------------------------------------------- #
class TestEndToEnd:
    def test_recognize_runs_and_caps_candles_at_five(self, rec):
        # Build 40 ascending bullish bars -> red-three-soldiers fires on many
        # windows but the candlestick list is capped at 5.
        rows = []
        price = 100.0
        for _ in range(40):
            o = price
            c = price + 1.0
            rows.append((o, c + 0.5, o - 0.5, c))
            price = c
        df = ohlc_df(rows)
        out = rec.recognize_patterns(df)
        assert len(out["candlestick_patterns"]) <= 5
        assert isinstance(out["chart_patterns"], list)
        assert out["total_patterns"] == len(out["candlestick_patterns"]) + len(
            out["chart_patterns"]
        )
