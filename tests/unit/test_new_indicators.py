import os
import sys
import unittest

import numpy as np
import pandas as pd

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.analytics.trend_analyzer import TrendAnalyzer
from src.analytics.volume_price_analyzer import VolumePriceAnalyzer


class TestNewIndicators(unittest.TestCase):
    def setUp(self):
        self.vp_analyzer = VolumePriceAnalyzer()
        self.trend_analyzer = TrendAnalyzer()

        # Create mock data
        dates = pd.date_range('2023-01-01', periods=100)
        np.random.seed(42)
        price = np.cumsum(np.random.randn(100)) + 100

        self.df = pd.DataFrame({
            'close': price,
            'high': price + 1,
            'low': price - 1,
            'volume': np.random.randint(100, 1000, size=100)
        }, index=dates)

    def test_vpvr_calculation(self):
        print("\nTesting VPVR Calculation...")
        result = self.vp_analyzer._calculate_vpvr(self.df, bins=10)

        print(f"POC: {result.get('poc')}")
        print(f"VAH: {result.get('vah')}")
        print(f"VAL: {result.get('val')}")

        self.assertIn('poc', result)
        self.assertIn('profile', result)
        self.assertTrue(len(result['profile']) > 0)

        # Verify total volume roughly matches
        total_vol_calc = result['total_volume']
        total_vol_actual = self.df['volume'].sum()
        # Approx check due to binning logic
        self.assertTrue(abs(total_vol_calc - total_vol_actual) / total_vol_actual < 0.1)

    def test_fibonacci_calculation(self):
        print("\nTesting Fibonacci Calculation...")
        # Make a clear trend 100 -> 200
        df_trend = pd.DataFrame({
            'high': [200],
            'low': [100],
            'close': [150] # 50% retrace
        })

        result = self.trend_analyzer._calculate_fibonacci_levels(df_trend)
        levels = result['levels']

        print("Levels:", levels)

        self.assertEqual(levels['0.0'], 200.0)
        self.assertEqual(levels['1.0'], 100.0)
        self.assertEqual(levels['0.5'], 150.0)

        # Check current position description
        self.assertIn("Fib 0.5", result['current_position'] or result['nearest_level'])


class TestMoneyFlowEdgeCases(unittest.TestCase):
    def setUp(self):
        self.vp_analyzer = VolumePriceAnalyzer()

    def test_all_up_days_mfi_is_overbought(self):
        """When every day in the window is an up-day there is no negative money
        flow, so MFI must saturate toward 100 (overbought), not be masked to a
        neutral 50."""
        n = 30
        dates = pd.date_range('2023-01-01', periods=n)
        price = np.arange(100, 100 + n, dtype=float)  # strictly rising
        df = pd.DataFrame({
            'close': price,
            'high': price + 1,
            'low': price - 1,
            'volume': np.full(n, 500),
        }, index=dates)

        result = self.vp_analyzer._analyze_money_flow(df)
        self.assertGreaterEqual(result['mfi'], 99.0)
        self.assertEqual(result['status'], 'overbought')

    def test_all_down_days_mfi_is_oversold(self):
        """Symmetric case: no positive money flow -> MFI saturates toward 0."""
        n = 30
        dates = pd.date_range('2023-01-01', periods=n)
        price = np.arange(100 + n, 100, -1, dtype=float)  # strictly falling
        df = pd.DataFrame({
            'close': price,
            'high': price + 1,
            'low': price - 1,
            'volume': np.full(n, 500),
        }, index=dates)

        result = self.vp_analyzer._analyze_money_flow(df)
        self.assertLessEqual(result['mfi'], 1.0)
        self.assertEqual(result['status'], 'oversold')


class TestObvEdgeCases(unittest.TestCase):
    def setUp(self):
        self.vp_analyzer = VolumePriceAnalyzer()

    def test_obv_change_with_zero_baseline_not_silently_zeroed(self):
        """When obv[-20] == 0 the 20-day change must still reflect the real
        move instead of being masked to 0 by an inf->nan->0 chain.

        Construction (n=25, so obv[-20] == obv[5]); volume is a flat 100:
          idx 0: close=100        -> obv = vol[0]      = 100
          idx 1: close=99  (down) -> obv = 100 - 100   = 0
          idx 2..5: flat          -> obv stays         = 0   (obv[-20] == 0)
          idx 6..24: up-days      -> obv grows by 100 each   (obv[-1] == 1900)
        """
        n = 25
        dates = pd.date_range('2023-01-01', periods=n)
        close = np.empty(n)
        close[0] = 100.0
        close[1] = 99.0          # down-day -> obv hits 0
        close[2:6] = 99.0        # flat -> obv stays 0 through index 5 (== -20)
        for i in range(6, n):    # strictly rising -> obv accumulates
            close[i] = close[i - 1] + 1.0
        volume = np.full(n, 100.0)

        df_close = pd.Series(close, index=dates)
        df_volume = pd.Series(volume, index=dates)
        result = self.vp_analyzer._analyze_obv(df_close, df_volume)

        # obv[-20] is 0; latest obv is positive -> change must be a real,
        # finite, non-zero number, not silently flattened to 0.
        self.assertTrue(np.isfinite(result['obv_change_20d']))
        self.assertGreater(result['obv_change_20d'], 0.0)


if __name__ == '__main__':
    unittest.main()
