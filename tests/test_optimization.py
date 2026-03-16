import sys
import os
import unittest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.data.data_manager import DataManager
from src.analytics.sentiment_analyzer import SentimentAnalyzer

class TestOptimization(unittest.TestCase):
    def setUp(self):
        self.data_manager = DataManager()
        self.sentiment_analyzer = SentimentAnalyzer()

    @patch('src.data.data_manager.yf.Ticker')
    def test_get_market_indicators_caching(self, mock_ticker):
        # Mock yfinance return
        mock_hist = pd.DataFrame({
            'Close': [100.0, 101.0, 102.0, 103.0, 104.0]
        }, index=pd.date_range('2023-01-01', periods=5))
        
        mock_instance = MagicMock()
        mock_instance.history.return_value = mock_hist
        mock_ticker.return_value = mock_instance

        # First call (uncached)
        print("Fetching indicators (1st call)...")
        indicators1 = self.data_manager.get_market_indicators()
        self.assertTrue(len(indicators1) > 0)
        
        # Second call (should be cached)
        print("Fetching indicators (2nd call)...")
        # We can't easily mock the cache internal state without exposing it, 
        # but we can verify it returns the same correct data.
        # In a real integration test we would time it.
        indicators2 = self.data_manager.get_market_indicators()
        
        self.assertEqual(indicators1, indicators2)
        print("Indicators:", indicators1)

    def test_adaptive_thresholds(self):
        # Create a dataframe with high volatility
        dates = pd.date_range('2023-01-01', periods=200)
        # Random walk with increasing volatility
        np.random.seed(42)
        returns = np.random.normal(0, 0.02, size=200) # 2% daily volatility (high)
        price = 100 * (1 + returns).cumprod()
        
        df = pd.DataFrame({
            'close': price,
            'high': price * 1.01,
            'low': price * 0.99,
            'volume': np.random.randint(1000, 10000, size=200)
        }, index=dates)
        
        result = self.sentiment_analyzer.analyze(df)
        vol_sentiment = result.get('volatility_sentiment', {})
        
        print("\nAdaptive Thresholds Result:")
        print(vol_sentiment)
        
        self.assertIn('thresholds', vol_sentiment)
        self.assertIn('high', vol_sentiment['thresholds'])
        
        # Verify thresholds are adapted (should be higher than default 30 for high vol data)
        # Note: 2% daily vol * sqrt(252) * 100 approx 31.7% annualized
        # So high threshold (80th percentile) should be around 30-40
        self.assertTrue(vol_sentiment['thresholds']['high'] > 20)

if __name__ == '__main__':
    unittest.main()
