"""
辅助工具函数
"""

import logging
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """计算夏普比率"""
    if returns.empty or returns.std() == 0:
        return 0.0

    excess_returns = returns.mean() - risk_free_rate
    return excess_returns / returns.std() * np.sqrt(252)  # 年化


def calculate_max_drawdown(
    portfolio_value: pd.Series,
) -> tuple[float, datetime, datetime]:
    """
    计算最大回撤

    Returns:
        tuple: (最大回撤值, 开始日期, 结束日期)
    """
    if portfolio_value.empty:
        return 0.0, None, None

    # 计算累计最高值
    rolling_max = portfolio_value.expanding().max()

    # 计算回撤
    drawdown = (portfolio_value - rolling_max) / rolling_max

    # 找到最大回撤
    max_drawdown = drawdown.min()

    # 找到最大回撤的日期
    max_dd_date = drawdown.idxmin()

    # 找到最大回撤开始的日期（之前的峰值）
    peak_date = rolling_max.loc[:max_dd_date].idxmax()

    return abs(max_drawdown), peak_date, max_dd_date


def calculate_win_rate(trades: pd.Series) -> float:
    """计算胜率"""
    if trades.empty:
        return 0.0

    winning_trades = trades[trades > 0]
    return len(winning_trades) / len(trades)


def calculate_calmar_ratio(returns: pd.Series, portfolio_value: pd.Series) -> float:
    """计算卡玛比率"""
    annual_return = returns.mean() * 252
    max_dd, _, _ = calculate_max_drawdown(portfolio_value)

    return annual_return / max_dd if max_dd != 0 else 0


def calculate_sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """计算索提诺比率"""
    if returns.empty:
        return 0.0

    excess_returns = returns - risk_free_rate
    downside_returns = excess_returns[excess_returns < 0]

    if len(downside_returns) == 0:
        return float("inf")

    downside_deviation = downside_returns.std()
    return (
        excess_returns.mean() / downside_deviation * np.sqrt(252)
        if downside_deviation != 0
        else 0
    )


def resample_data(data: pd.DataFrame, frequency: str = "D") -> pd.DataFrame:
    """
    重采样数据到指定频率

    Args:
        data: OHLCV数据
        frequency: 频率 ('D', 'W', 'M', 'H', '30min'等)

    Returns:
        重采样后的数据
    """
    if data.empty:
        return data

    # 定义聚合规则
    agg_rules = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }

    # 只聚合存在的列
    available_rules = {k: v for k, v in agg_rules.items() if k in data.columns}

    return data.resample(frequency).agg(available_rules).dropna()


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """设置日志配置 - 已弃用，请使用 src.utils.config.setup_logging"""
    import warnings

    warnings.warn(
        "helpers.setup_logging is deprecated, "
        "use src.utils.config.setup_logging instead",
        DeprecationWarning,
        stacklevel=2,
    )

    # 导入统一的日志配置
    from .config import setup_logging as config_setup_logging

    config_setup_logging(level)
