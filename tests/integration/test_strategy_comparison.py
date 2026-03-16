import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pandas as pd
import numpy as np
from datetime import datetime

# Adjust path to import from backend
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.main import app

client = TestClient(app)

@pytest.fixture
def mock_market_data():
    dates = pd.date_range(start="2023-01-01", end="2023-12-31", freq="D")
    data = pd.DataFrame({
        "open": np.random.rand(len(dates)) * 100,
        "high": np.random.rand(len(dates)) * 110,
        "low": np.random.rand(len(dates)) * 90,
        "close": np.random.rand(len(dates)) * 100,
        "volume": np.random.randint(1000, 10000, len(dates))
    }, index=dates)
    return data

@patch("backend.app.api.v1.endpoints.backtest.data_manager")
@patch("backend.app.api.v1.endpoints.backtest.Backtester")
def test_compare_strategies(mock_backtester_class, mock_data_manager, mock_market_data):
    # Setup mocks
    mock_data_manager.get_historical_data.return_value = mock_market_data
    
    # Mock Backtester instance and run method
    mock_instance = MagicMock()
    mock_backtester_class.return_value = mock_instance
    
    # Define side effect to return different results for different strategies
    def run_side_effect(strategy, data):
        # Identify strategy by class name or some property if possible, 
        # but here we can just return random valid metrics since we mock the result
        # For more checking, we can inspect strategy.__class__.__name__
        
        strat_name = strategy.__class__.__name__
        if strat_name == 'MovingAverageCrossover':
            return {
                "total_return": 0.5, # 50%
                "annualized_return": 0.5,
                "sharpe_ratio": 2.0,
                "max_drawdown": -0.1,
                "num_trades": 10
            }
        elif strat_name == 'RSIStrategy':
            return {
                "total_return": 0.2, # 20%
                "annualized_return": 0.2,
                "sharpe_ratio": 1.0,
                "max_drawdown": -0.2,
                "num_trades": 5
            }
        else:
             return {
                "total_return": 0.1, 
                "annualized_return": 0.1,
                "sharpe_ratio": 0.5,
                "max_drawdown": -0.3,
                "num_trades": 2
            }

    mock_instance.run.side_effect = run_side_effect

    # Call API
    response = client.get(
        "/backtest/compare",
        params={
            "symbol": "AAPL",
            "strategies": "moving_average,rsi",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "initial_capital": 50000
        }
    )

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    results = data["data"]
    
    # Verify we got results for both
    assert "moving_average" in results
    assert "rsi" in results
    
    ma_res = results["moving_average"]
    rsi_res = results["rsi"]
    
    # Verify scores exist
    assert "scores" in ma_res
    assert "scores" in rsi_res
    
    # Verify ranking logic: MA has higher return (0.5 vs 0.2) -> Higher return_score
    assert ma_res["scores"]["return_score"] > rsi_res["scores"]["return_score"]
    
    # Verify ranking
    assert ma_res["rank"] == 1
    assert rsi_res["rank"] == 2
