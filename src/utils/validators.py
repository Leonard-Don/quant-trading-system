"""
验证工具模块
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime
import re

from .exceptions import ValidationError


def validate_symbol(symbol: str) -> str:
    """验证股票代码"""
    if not symbol or not isinstance(symbol, str):
        raise ValidationError("股票代码不能为空")

    symbol = symbol.upper().strip()

    # 基本格式验证
    if not re.match(r"^[A-Z]{1,5}$", symbol):
        raise ValidationError(f"股票代码格式无效: {symbol}")

    return symbol


def validate_date_range(
    start_date: Optional[datetime], end_date: Optional[datetime]
) -> None:
    """验证日期范围"""
    if start_date and end_date:
        if start_date >= end_date:
            raise ValidationError("开始日期必须早于结束日期")

        if end_date > datetime.now():
            raise ValidationError("结束日期不能晚于当前日期")

        # 检查日期范围是否合理（不超过10年）
        if (end_date - start_date).days > 3650:
            raise ValidationError("日期范围不能超过10年")


def validate_strategy_parameters(
    strategy: str, parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """验证策略参数"""
    validated_params = {}

    if strategy == "moving_average":
        fast_period = parameters.get("fast_period", 20)
        slow_period = parameters.get("slow_period", 50)

        if not isinstance(fast_period, int) or fast_period < 1:
            raise ValidationError("快速均线周期必须是正整数")
        if not isinstance(slow_period, int) or slow_period < 1:
            raise ValidationError("慢速均线周期必须是正整数")
        if fast_period >= slow_period:
            raise ValidationError("快速均线周期必须小于慢速均线周期")

        validated_params = {"fast_period": fast_period, "slow_period": slow_period}

    elif strategy == "rsi":
        period = parameters.get("period", 14)
        oversold = parameters.get("oversold", 30)
        overbought = parameters.get("overbought", 70)

        if not isinstance(period, int) or period < 1:
            raise ValidationError("RSI周期必须是正整数")
        if not (0 < oversold < 100):
            raise ValidationError("超卖阈值必须在0-100之间")
        if not (0 < overbought < 100):
            raise ValidationError("超买阈值必须在0-100之间")
        if oversold >= overbought:
            raise ValidationError("超卖阈值必须小于超买阈值")

        validated_params = {
            "period": period,
            "oversold": oversold,
            "overbought": overbought,
        }

    elif strategy == "bollinger_bands":
        period = parameters.get("period", 20)
        num_std = parameters.get("num_std", 2.0)

        if not isinstance(period, int) or period < 1:
            raise ValidationError("布林带周期必须是正整数")
        if not isinstance(num_std, (int, float)) or num_std <= 0:
            raise ValidationError("标准差倍数必须是正数")

        validated_params = {"period": period, "num_std": float(num_std)}

    elif strategy == "macd":
        fast_period = parameters.get("fast_period", 12)
        slow_period = parameters.get("slow_period", 26)
        signal_period = parameters.get("signal_period", 9)

        if not isinstance(fast_period, int) or fast_period < 1:
            raise ValidationError("MACD快线周期必须是正整数")
        if not isinstance(slow_period, int) or slow_period < 1:
            raise ValidationError("MACD慢线周期必须是正整数")
        if not isinstance(signal_period, int) or signal_period < 1:
            raise ValidationError("MACD信号线周期必须是正整数")
        if fast_period >= slow_period:
            raise ValidationError("MACD快线周期必须小于慢线周期")

        validated_params = {
            "fast_period": fast_period,
            "slow_period": slow_period,
            "signal_period": signal_period,
        }

    return validated_params


def validate_backtest_params(
    initial_capital: float, commission: float, slippage: float
) -> None:
    """验证回测参数"""
    if not isinstance(initial_capital, (int, float)) or initial_capital <= 0:
        raise ValidationError("初始资金必须是正数")

    if not isinstance(commission, (int, float)) or commission < 0:
        raise ValidationError("手续费率不能为负数")

    if not isinstance(slippage, (int, float)) or slippage < 0:
        raise ValidationError("滑点不能为负数")

    if commission > 0.1:  # 10%
        raise ValidationError("手续费率过高（超过10%）")

    if slippage > 0.1:  # 10%
        raise ValidationError("滑点过高（超过10%）")


def validate_dataframe(df: pd.DataFrame, required_columns: List[str] = None) -> None:
    """验证DataFrame"""
    if df is None or df.empty:
        raise ValidationError("数据不能为空")

    if required_columns:
        missing_columns = set(required_columns) - set(df.columns)
        if missing_columns:
            raise ValidationError(f"缺少必要的列: {missing_columns}")

    # 检查是否有NaN值
    if df.isnull().any().any():
        raise ValidationError("数据包含空值")

    # 检查数值列是否为数值类型
    numeric_columns = ["open", "high", "low", "close", "volume"]
    for col in numeric_columns:
        if col in df.columns and not pd.api.types.is_numeric_dtype(df[col]):
            raise ValidationError(f"列 {col} 必须是数值类型")


def validate_signals(signals: pd.Series, data_length: int) -> None:
    """验证交易信号"""
    if signals is None or signals.empty:
        raise ValidationError("交易信号不能为空")

    if len(signals) != data_length:
        raise ValidationError("信号长度与数据长度不匹配")

    # 检查信号值是否有效（应该是-1, 0, 1）
    valid_signals = signals.dropna().isin([-1, 0, 1])
    if not valid_signals.all():
        raise ValidationError("交易信号必须是-1、0或1")
