"""
Backtest Metrics Calculation Module

This module provides common functions for calculating financial performance metrics
used in various backtesting engines.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Union, Optional

def calculate_returns(equity_curve: Union[pd.Series, np.ndarray]) -> float:
    """
    Calculate total return from equity curve.
    
    Args:
        equity_curve: Series or array of portfolio values
        
    Returns:
        Total return as a decimal (e.g., 0.1 for 10%)
    """
    if len(equity_curve) < 1:
        return 0.0
    
    if isinstance(equity_curve, pd.Series):
        start_value = equity_curve.iloc[0]
        end_value = equity_curve.iloc[-1]
    else:
        start_value = equity_curve[0]
        end_value = equity_curve[-1]
        
    if start_value == 0:
        return 0.0
        
    return (end_value - start_value) / start_value

def calculate_annualized_return(
    total_return: float, 
    n_days: int, 
    trading_days_per_year: int = 252
) -> float:
    """
    Calculate annualized return.
    
    Args:
        total_return: Total return as decimal
        n_days: Number of days (or periods) in the backtest
        trading_days_per_year: Number of trading days in a year
        
    Returns:
        Annualized return as decimal
    """
    if n_days <= 0:
        return 0.0
        
    years = n_days / trading_days_per_year
    if years == 0:
        return 0.0
        
    # Using geometric mean
    return (1 + total_return) ** (1 / years) - 1

def calculate_max_drawdown(equity_curve: Union[pd.Series, np.ndarray]) -> float:
    """
    Calculate maximum drawdown.
    
    Args:
        equity_curve: Series or array of portfolio values
        
    Returns:
        Maximum drawdown as a positive decimal (e.g., 0.2 for 20% drawdown)
    """
    if len(equity_curve) < 1:
        return 0.0
        
    if isinstance(equity_curve, pd.Series):
        values = equity_curve.values
    else:
        values = equity_curve
        
    peak = values[0]
    max_dd = 0.0
    
    # Calculate running max
    running_max = np.maximum.accumulate(values)
    
    # Calculate drawdown
    # Avoid division by zero
    with np.errstate(divide='ignore', invalid='ignore'):
        drawdown = (running_max - values) / running_max
        # Handle cases where running_max is 0
        drawdown[running_max == 0] = 0
        
    return np.max(drawdown) if len(drawdown) > 0 else 0.0

def calculate_sharpe_ratio(
    returns: Union[pd.Series, np.ndarray], 
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """
    Calculate Sharpe Ratio.
    
    Args:
        returns: Series or array of periodic returns
        risk_free_rate: Annual risk free rate
        periods_per_year: Number of periods per year (default 252 for daily)
        
    Returns:
        Sharpe Ratio
    """
    if len(returns) < 2:
        return 0.0
        
    # Convert annual risk free rate to periodic
    rf_per_period = (1 + risk_free_rate) ** (1 / periods_per_year) - 1
    
    excess_returns = returns - rf_per_period
    mean_excess_return = np.mean(excess_returns)
    std_dev = np.std(returns)
    
    if std_dev == 0:
        return 0.0
        
    return (mean_excess_return / std_dev) * np.sqrt(periods_per_year)

def calculate_sortino_ratio(
    returns: Union[pd.Series, np.ndarray],
    target_return: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """
    Calculate Sortino Ratio.
    
    Args:
        returns: Series or array of periodic returns
        target_return: Target periodic return (often 0)
        periods_per_year: Number of periods per year
        
    Returns:
        Sortino Ratio
    """
    if len(returns) < 2:
        return 0.0
        
    mean_return = np.mean(returns)
    
    # Calculate downside deviation
    downside_returns = returns[returns < target_return]
    if len(downside_returns) == 0:
        return 0.0 # No downside risk
        
    # Standard deviation of downside returns only
    # Note: Sortino typically uses a specific formula for Semi-Deviation
    # Root Mean Square of the underperformance
    underperformance = returns - target_return
    underperformance[underperformance > 0] = 0
    downside_deviation = np.sqrt(np.mean(underperformance ** 2))
    
    if downside_deviation == 0:
        return 0.0
        
    return (mean_return - target_return) / downside_deviation * np.sqrt(periods_per_year)

def calculate_volatility(
    returns: Union[pd.Series, np.ndarray],
    periods_per_year: int = 252
) -> float:
    """
    Calculate Annualized Volatility.
    
    Args:
        returns: periodic returns
        periods_per_year: (default 252)
        
    Returns:
        Annualized standard deviation
    """
    if len(returns) < 2:
        return 0.0
        
    return np.std(returns) * np.sqrt(periods_per_year)

def calculate_var(
    returns: Union[pd.Series, np.ndarray],
    confidence_level: float = 0.95
) -> float:
    """
    Calculate Value at Risk (VaR).
    
    Args:
        returns: periodic returns
        confidence_level: (default 0.95)
        
    Returns:
        VaR as a positive decimal (e.g. 0.02 means 2% potential loss)
        Note: Returned value is usually negative in raw percentile, 
        but commonly expressed as a positive "Risk" value or negative return threshold.
        Here we return the negative return threshold (e.g. -0.02).
    """
    if len(returns) < 1:
        return 0.0
        
    # Calculate percentile
    # For 95% confidence, we look at the 5th percentile of worst returns
    percentile = (1 - confidence_level) * 100
    return np.percentile(returns, percentile)

def calculate_calmar_ratio(
    annualized_return: float,
    max_drawdown: float
) -> float:
    """
    Calculate Calmar Ratio.
    
    Args:
        annualized_return: Annualized return
        max_drawdown: Maximum drawdown (positive value)
        
    Returns:
        Calmar Ratio
    """
    if max_drawdown == 0:
        return 0.0 if annualized_return <= 0 else float('inf') # Or large number
        
    return annualized_return / max_drawdown
