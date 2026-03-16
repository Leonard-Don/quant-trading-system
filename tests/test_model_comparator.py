import sys
import os
import pandas as pd
import numpy as np
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.analytics.model_comparator import model_comparator

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

def test_comparator():
    print("Testing Model Comparator...")
    data = create_mock_data()
    
    # Train first to ensure models are ready (though comparator uses pre-instantiated singleton)
    # We might need to ensure RF is trained.
    print("Training RF model explicitly...")
    model_comparator.rf_predictor.train(data, "TEST_SYM_COMP")
    
    # Compare
    print("Running comparison...")
    result = model_comparator.compare_predictions(data, "TEST_SYM_COMP", days=5)
    
    print("Result keys:", result.keys())
    if 'predictions' in result:
        print("Predictions keys:", result['predictions'].keys())
        if 'random_forest' in result['predictions']:
            print("RF Status:", result['predictions']['random_forest'].get('status'))
            if result['predictions']['random_forest'].get('status') == 'error':
                 print("RF Error:", result['predictions']['random_forest'].get('error'))

        if 'lstm' in result['predictions']:
            print("LSTM Status:", result['predictions']['lstm'].get('status'))
    
    if 'comparison' in result:
        print("Comparison keys:", result['comparison'].keys())
    
    assert 'predictions' in result
    assert 'random_forest' in result['predictions']
    assert 'lstm' in result['predictions']
    
    # Verify fix for frontend compatibility
    assert 'dates' in result, "❌ Top-level 'dates' field is missing!"
    print("✅ Top-level 'dates' field confirmed.")
    
    print("✅ Model Comparator Test Passed")

if __name__ == "__main__":
    try:
        test_comparator()
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()
