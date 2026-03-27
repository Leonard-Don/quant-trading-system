import pytest
from unittest.mock import patch
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
@patch("backend.app.api.v1.endpoints.backtest.run_backtest_pipeline")
def test_compare_strategies(mock_run_backtest_pipeline, mock_data_manager, mock_market_data):
    # Setup mocks
    mock_data_manager.get_historical_data.return_value = mock_market_data

    def pipeline_side_effect(**kwargs):
        strat_name = kwargs["strategy_name"]
        if strat_name == 'moving_average':
            return ({
                "total_return": 0.5, # 50%
                "annualized_return": 0.5,
                "sharpe_ratio": 2.0,
                "max_drawdown": -0.1,
                "num_trades": 10,
                "total_trades": 10,
                "profit_factor": 1.8,
                "win_rate": 0.6,
                "final_value": 75000,
            }, {})
        elif strat_name == 'rsi':
            return ({
                "total_return": 0.2, # 20%
                "annualized_return": 0.2,
                "sharpe_ratio": 1.0,
                "max_drawdown": -0.2,
                "num_trades": 5,
                "total_trades": 5,
                "profit_factor": 1.2,
                "win_rate": 0.5,
                "final_value": 60000,
            }, {})
        return ({
                "total_return": 0.1, 
                "annualized_return": 0.1,
                "sharpe_ratio": 0.5,
                "max_drawdown": -0.3,
                "num_trades": 2,
                "total_trades": 2,
                "profit_factor": 1.0,
                "win_rate": 0.4,
                "final_value": 55000,
            }, {})

    mock_run_backtest_pipeline.side_effect = pipeline_side_effect

    # Call API
    response = client.post(
        "/backtest/compare",
        json={
            "symbol": "AAPL",
            "strategies": ["moving_average", "rsi"],
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "initial_capital": 50000,
            "commission": 0.002,
            "slippage": 0.0015,
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

    first_call = mock_run_backtest_pipeline.call_args_list[0].kwargs
    assert first_call["initial_capital"] == 50000
    assert first_call["commission"] == pytest.approx(0.002)
    assert first_call["slippage"] == pytest.approx(0.0015)


@patch("backend.app.api.v1.endpoints.backtest.data_manager")
@patch("backend.app.api.v1.endpoints.backtest.run_backtest_pipeline")
def test_compare_strategies_supports_strategy_specific_parameters(
    mock_run_backtest_pipeline,
    mock_data_manager,
    mock_market_data,
):
    mock_data_manager.get_historical_data.return_value = mock_market_data
    mock_run_backtest_pipeline.return_value = ({
        "total_return": 0.1,
        "annualized_return": 0.1,
        "sharpe_ratio": 0.8,
        "max_drawdown": -0.15,
        "num_trades": 3,
        "total_trades": 3,
        "profit_factor": 1.1,
        "win_rate": 0.5,
        "final_value": 11000,
        "parameters": {},
    }, {})

    response = client.post(
        "/backtest/compare",
        json={
            "symbol": "AAPL",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "initial_capital": 20000,
            "commission": 0.001,
            "slippage": 0.0005,
            "strategy_configs": [
                {
                    "name": "moving_average",
                    "parameters": {"fast_period": 8, "slow_period": 21},
                },
                {
                    "name": "rsi",
                    "parameters": {"period": 10, "oversold": 25, "overbought": 75},
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    moving_average_call = mock_run_backtest_pipeline.call_args_list[0].kwargs
    rsi_call = mock_run_backtest_pipeline.call_args_list[1].kwargs

    assert moving_average_call["parameters"] == {"fast_period": 8, "slow_period": 21}
    assert rsi_call["parameters"] == {"period": 10, "oversold": 25, "overbought": 75}
