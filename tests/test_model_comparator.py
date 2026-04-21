import pandas as pd
import numpy as np
from src.analytics.lstm_predictor import LSTMPredictor
from src.analytics.model_comparator import ModelComparator
from src.analytics.predictor import PricePredictor

def create_mock_data(days=100):
    dates = pd.date_range(end=pd.Timestamp.now(), periods=days)
    data = pd.DataFrame({
        'close': np.linspace(100, 150, days) + np.random.normal(0, 1, days),
        'high': np.linspace(102, 152, days) + np.random.normal(0, 1, days),
        'low': np.linspace(98, 148, days) + np.random.normal(0, 1, days),
        'volume': np.random.randint(1000, 5000, days)
    }, index=dates)
    return data

def test_comparator(tmp_path):
    data = create_mock_data()

    comparator = ModelComparator(
        rf_predictor=PricePredictor(model_path=str(tmp_path / "rf_model_data")),
        lstm_predictor_instance=LSTMPredictor(
            sequence_length=10,
            model_dir=str(tmp_path / "lstm_models"),
        ),
    )

    comparator.rf_predictor.train(data, "TEST_SYM_COMP")
    result = comparator.compare_predictions(data, "TEST_SYM_COMP", days=5)

    assert 'predictions' in result
    assert 'random_forest' in result['predictions']
    assert 'lstm' in result['predictions']
    assert 'dates' in result, "❌ Top-level 'dates' field is missing!"
