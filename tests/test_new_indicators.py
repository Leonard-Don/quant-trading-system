import sys
import os
import unittest
import pandas as pd
import numpy as np

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.analytics.volume_price_analyzer import VolumePriceAnalyzer
from src.analytics.trend_analyzer import TrendAnalyzer

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

if __name__ == '__main__':
    unittest.main()
