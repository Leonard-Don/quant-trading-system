import sys
import os
import pandas as pd
import numpy as np
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.analytics.predictor import PricePredictor
from src.analytics.lstm_predictor import LSTMPredictor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_mock_data(days=100):
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days)
    data = pd.DataFrame({
        'close': np.linspace(100, 150, days) + np.random.normal(0, 1, days),
        'high': np.linspace(102, 152, days) + np.random.normal(0, 1, days),
        'low': np.linspace(98, 148, days) + np.random.normal(0, 1, days),
        'volume': np.random.randint(1000, 5000, days)
    }, index=dates)
    return data

def test_random_forest_recursive():
    print("Testing Random Forest Recursive Prediction...")
    predictor = PricePredictor()
    data = create_mock_data()
    
    # Train
    predictor.train(data, "TEST_SYM_RF")
    
    # Predict
    result = predictor.predict_next_days(data, days=5, symbol="TEST_SYM_RF")
    
    print("RF Prediction Result keys:", result.keys())
    print("RF Predicted Prices:", result['predicted_prices'])
    
    assert len(result['predicted_prices']) == 5
    assert len(result['dates']) == 5
    assert result['prediction_summary']['trend'] in ['bullish', 'bearish', 'neutral']
    print("✅ RF Recursive Prediction Passed")

def test_lstm_prediction():
    print("\nTesting LSTM Prediction...")
    predictor = LSTMPredictor(sequence_length=10)
    data = create_mock_data()
    
    # Train
    predictor.train(data, "TEST_SYM_LSTM")
    
    # Predict
    result = predictor.predict(data, "TEST_SYM_LSTM", days=5)
    
    print("LSTM Prediction Result keys:", result.keys())
    print("LSTM Predicted Prices:", result['predicted_prices'])
    
    assert len(result['predicted_prices']) == 5
    assert len(result['dates']) == 5
    print("✅ LSTM Prediction Passed")

if __name__ == "__main__":
    try:
        test_random_forest_recursive()
        test_lstm_prediction()
        print("\n🎉 All AI Prediction Tests Passed!")
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
