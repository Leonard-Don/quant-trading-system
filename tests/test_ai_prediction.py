import pandas as pd
import numpy as np

from src.analytics.predictor import PricePredictor
from src.analytics.lstm_predictor import LSTMPredictor, TF_AVAILABLE

def create_mock_data(days=100):
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days)
    data = pd.DataFrame({
        'close': np.linspace(100, 150, days) + np.random.normal(0, 1, days),
        'high': np.linspace(102, 152, days) + np.random.normal(0, 1, days),
        'low': np.linspace(98, 148, days) + np.random.normal(0, 1, days),
        'volume': np.random.randint(1000, 5000, days)
    }, index=dates)
    return data

def test_random_forest_recursive(tmp_path):
    predictor = PricePredictor(model_path=str(tmp_path / "rf_model_data"))
    data = create_mock_data()
    predictor.train(data, "TEST_SYM_RF")
    result = predictor.predict_next_days(data, days=5, symbol="TEST_SYM_RF")

    assert len(result['predicted_prices']) == 5
    assert len(result['dates']) == 5
    assert result['prediction_summary']['trend'] in ['bullish', 'bearish', 'neutral']
    assert list((tmp_path / "rf_model_data").glob("*.joblib"))


def test_lstm_prediction(tmp_path):
    predictor = LSTMPredictor(sequence_length=10, model_dir=str(tmp_path / "lstm_models"))
    data = create_mock_data()
    predictor.train(data, "TEST_SYM_LSTM")
    result = predictor.predict(data, "TEST_SYM_LSTM", days=5)

    assert len(result['predicted_prices']) == 5
    assert len(result['dates']) == 5
    if TF_AVAILABLE:
        assert (tmp_path / "lstm_models" / "TEST_SYM_LSTM_lstm.keras").exists()
        assert (tmp_path / "lstm_models" / "TEST_SYM_LSTM_scaler.pkl").exists()
