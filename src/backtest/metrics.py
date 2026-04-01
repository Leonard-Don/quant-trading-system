"""
Backtest Metrics Calculation Module

This module provides common functions for calculating financial performance metrics
used in various backtesting engines.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Union, Optional, Tuple

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


def calculate_max_drawdown_duration(
    equity_curve: Union[pd.Series, np.ndarray],
) -> Tuple[int, int]:
    """
    Calculate maximum drawdown duration (periods to recover) and the
    longest underwater period (periods from peak to next peak).

    Args:
        equity_curve: Series or array of portfolio values

    Returns:
        Tuple of (max_drawdown_duration, max_underwater_period) in number of
        periods (bars). max_drawdown_duration is the length of the single
        deepest drawdown episode.  max_underwater_period is the longest
        stretch the equity spent below a prior peak (which may still be
        ongoing at end of data).
    """
    if len(equity_curve) < 2:
        return 0, 0

    if isinstance(equity_curve, pd.Series):
        values = equity_curve.values.astype(float)
    else:
        values = np.asarray(equity_curve, dtype=float)

    running_max = np.maximum.accumulate(values)

    # --- max drawdown duration (bars inside the deepest drawdown) ---
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown_pct = (running_max - values) / running_max
        drawdown_pct[running_max == 0] = 0.0

    max_dd = float(np.max(drawdown_pct))
    if max_dd == 0:
        return 0, 0

    # Find the peak-to-trough-to-recovery of the deepest drawdown
    trough_idx = int(np.argmax(drawdown_pct))
    peak_idx = int(np.argmax(values[:trough_idx + 1])) if trough_idx > 0 else 0

    # Look for recovery after trough
    recovery_idx = len(values) - 1  # default: not recovered
    for i in range(trough_idx + 1, len(values)):
        if values[i] >= running_max[trough_idx]:
            recovery_idx = i
            break

    max_dd_duration = recovery_idx - peak_idx

    # --- longest underwater period ---
    max_underwater = 0
    current_underwater = 0
    for i in range(len(values)):
        if values[i] < running_max[i]:
            current_underwater += 1
            max_underwater = max(max_underwater, current_underwater)
        else:
            current_underwater = 0

    return max_dd_duration, max_underwater


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
    # Use sample standard deviation (ddof=1) — the finance-industry convention
    std_dev = np.std(returns, ddof=1)
    
    if std_dev < 1e-15:
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
        
    # Root Mean Square of the underperformance
    underperformance = np.minimum(returns - target_return, 0.0)
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
    
    # Use sample standard deviation (ddof=1) for consistency with Sharpe
    return np.std(returns, ddof=1) * np.sqrt(periods_per_year)

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


def calculate_cvar(
    returns: Union[pd.Series, np.ndarray],
    confidence_level: float = 0.95,
) -> float:
    """
    Calculate Conditional Value at Risk (CVaR), also known as Expected
    Shortfall (ES).

    CVaR is the expected loss in the worst (1 - confidence_level) fraction
    of outcomes.  It is always <= VaR and provides a more conservative risk
    estimate because it accounts for the *shape* of the tail.

    Args:
        returns: periodic returns
        confidence_level: (default 0.95)

    Returns:
        CVaR as a float (typically negative, representing the average loss
        in the tail).  Returns 0.0 when insufficient data.
    """
    if len(returns) < 1:
        return 0.0

    if isinstance(returns, pd.Series):
        values = returns.values.astype(float)
    else:
        values = np.asarray(returns, dtype=float)

    var_threshold = float(np.percentile(values, (1 - confidence_level) * 100))
    tail = values[values <= var_threshold]

    if len(tail) == 0:
        return var_threshold

    return float(np.mean(tail))


def calculate_omega_ratio(
    returns: Union[pd.Series, np.ndarray],
    threshold: float = 0.0,
) -> float:
    """
    Calculate the Omega Ratio.

    Omega = (sum of gains above threshold) / (sum of losses below threshold).
    Unlike the Sharpe ratio, it considers the *entire* return distribution,
    not just mean and variance.

    Args:
        returns: periodic returns
        threshold: minimum acceptable return per period (default 0)

    Returns:
        Omega Ratio (>1 is good, <1 means losing).
        Returns 0.0 when there are no losses or insufficient data.
    """
    if len(returns) < 1:
        return 0.0

    if isinstance(returns, pd.Series):
        values = returns.values.astype(float)
    else:
        values = np.asarray(returns, dtype=float)

    excess = values - threshold
    gains = float(np.sum(excess[excess > 0]))
    losses = float(np.abs(np.sum(excess[excess < 0])))

    if losses == 0:
        return float("inf") if gains > 0 else 0.0

    return gains / losses


def calculate_information_ratio(
    strategy_returns: Union[pd.Series, np.ndarray],
    benchmark_returns: Union[pd.Series, np.ndarray],
    periods_per_year: int = 252,
) -> float:
    """
    Calculate the Information Ratio (IR).

    IR = annualised mean(active returns) / annualised std(active returns)
    where active return = strategy return - benchmark return.

    Args:
        strategy_returns: periodic returns of the strategy
        benchmark_returns: periodic returns of the benchmark
        periods_per_year: (default 252)

    Returns:
        Information Ratio.  Returns 0.0 when data is insufficient or
        tracking error is zero.
    """
    if len(strategy_returns) < 2 or len(benchmark_returns) < 2:
        return 0.0

    if isinstance(strategy_returns, pd.Series):
        strat = strategy_returns.values.astype(float)
    else:
        strat = np.asarray(strategy_returns, dtype=float)

    if isinstance(benchmark_returns, pd.Series):
        bench = benchmark_returns.values.astype(float)
    else:
        bench = np.asarray(benchmark_returns, dtype=float)

    min_len = min(len(strat), len(bench))
    active_returns = strat[:min_len] - bench[:min_len]

    tracking_error = float(np.std(active_returns, ddof=1))
    if tracking_error == 0:
        return 0.0

    mean_active = float(np.mean(active_returns))
    return (mean_active / tracking_error) * np.sqrt(periods_per_year)


def calculate_treynor_ratio(
    annualized_return: float,
    beta: float,
    risk_free_rate: float = 0.0,
) -> float:
    """
    Calculate the Treynor Ratio.

    Treynor = (annualized_return - risk_free_rate) / beta

    Args:
        annualized_return: Annualized strategy return
        beta: Market beta of the strategy
        risk_free_rate: Annual risk-free rate

    Returns:
        Treynor ratio, or 0 when beta is too close to zero.
    """
    if abs(beta) < 1e-12:
        return 0.0
    return (annualized_return - risk_free_rate) / beta


def calculate_recovery_factor(
    net_profit: float,
    max_drawdown: float,
) -> float:
    """
    Calculate Recovery Factor.

    Recovery Factor = net_profit / max_drawdown

    Args:
        net_profit: Strategy net profit in currency terms
        max_drawdown: Maximum drawdown as a positive decimal

    Returns:
        Recovery factor.  Returns inf for profitable zero-drawdown curves and
        0 for non-profitable zero-drawdown curves.
    """
    if max_drawdown == 0:
        return float("inf") if net_profit > 0 else 0.0
    return net_profit / max_drawdown


def calculate_expectancy(
    trade_pnls: Union[pd.Series, np.ndarray, list[float]],
) -> float:
    """
    Calculate trade expectancy (average profit per trade).

    Args:
        trade_pnls: Per-trade profit and loss values

    Returns:
        Average PnL per trade, or 0.0 when no trades are supplied.
    """
    if len(trade_pnls) < 1:
        return 0.0

    if isinstance(trade_pnls, pd.Series):
        values = trade_pnls.values.astype(float)
    else:
        values = np.asarray(trade_pnls, dtype=float)

    if len(values) == 0:
        return 0.0
    return float(np.mean(values))


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
