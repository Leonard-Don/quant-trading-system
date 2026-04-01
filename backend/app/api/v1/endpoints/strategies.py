
from fastapi import APIRouter
from typing import List
from functools import lru_cache

from backend.app.schemas.base import StrategyInfo
from src.strategy.strategies import (
    MovingAverageCrossover,
    RSIStrategy,
    BollingerBands,
    BuyAndHold,
    TurtleTradingStrategy,
    MultiFactorStrategy,
)
from src.strategy.advanced_strategies import (
    MACDStrategy,
    MeanReversionStrategy,
    VWAPStrategy,
    MomentumStrategy,
)

router = APIRouter()


@lru_cache(maxsize=1)
def _get_strategies_list():
    """获取策略列表（带内存缓存）"""
    return [
        {
            "name": "moving_average",
            "description": "移动均线交叉策略",
            "parameters": {
                "fast_period": {"type": "int", "default": 20, "min": 5, "max": 50},
                "slow_period": {"type": "int", "default": 50, "min": 20, "max": 200},
            },
        },
        {
            "name": "rsi",
            "description": "RSI相对强弱指标策略",
            "parameters": {
                "period": {"type": "int", "default": 14, "min": 5, "max": 30},
                "oversold": {"type": "int", "default": 30, "min": 10, "max": 40},
                "overbought": {"type": "int", "default": 70, "min": 60, "max": 90},
            },
        },
        {
            "name": "bollinger_bands",
            "description": "布林带策略",
            "parameters": {
                "period": {"type": "int", "default": 20, "min": 10, "max": 50},
                "num_std": {"type": "float", "default": 2.0, "min": 1.0, "max": 3.0},
            },
        },
        {"name": "buy_and_hold", "description": "买入持有策略", "parameters": {}},
        {
            "name": "macd",
            "description": "MACD策略",
            "parameters": {
                "fast_period": {"type": "int", "default": 12, "min": 5, "max": 20},
                "slow_period": {"type": "int", "default": 26, "min": 20, "max": 50},
                "signal_period": {"type": "int", "default": 9, "min": 5, "max": 15},
            },
        },
        {
            "name": "mean_reversion",
            "description": "均值回归策略",
            "parameters": {
                "lookback_period": {"type": "int", "default": 20, "min": 10, "max": 50},
                "entry_threshold": {
                    "type": "float",
                    "default": 2.0,
                    "min": 1.0,
                    "max": 3.0,
                },
            },
        },
        {
            "name": "vwap",
            "description": "VWAP策略",
            "parameters": {
                "period": {"type": "int", "default": 20, "min": 10, "max": 50}
            },
        },
        {
            "name": "momentum",
            "description": "动量策略",
            "parameters": {
                "fast_window": {"type": "int", "default": 10, "min": 5, "max": 30},
                "slow_window": {"type": "int", "default": 30, "min": 20, "max": 100},
            },
        },
        {
            "name": "stochastic",
            "description": "随机指标策略",
            "parameters": {
                "k_period": {"type": "int", "default": 14, "min": 5, "max": 30},
                "d_period": {"type": "int", "default": 3, "min": 1, "max": 10},
                "oversold": {"type": "int", "default": 20, "min": 10, "max": 40},
                "overbought": {"type": "int", "default": 80, "min": 60, "max": 90},
            },
        },
        {
            "name": "atr_trailing_stop",
            "description": "ATR移动止损策略",
            "parameters": {
                "atr_period": {"type": "int", "default": 14, "min": 5, "max": 30},
                "atr_multiplier": {"type": "float", "default": 2.0, "min": 1.0, "max": 5.0},
            },
        },
        {
            "name": "turtle_trading",
            "description": "海龟交易 / Donchian 通道突破策略",
            "parameters": {
                "entry_period": {"type": "int", "default": 20, "min": 5, "max": 120},
                "exit_period": {"type": "int", "default": 10, "min": 3, "max": 60},
            },
        },
        {
            "name": "multi_factor",
            "description": "多因子复合择时策略",
            "parameters": {
                "momentum_window": {"type": "int", "default": 20, "min": 5, "max": 120},
                "mean_reversion_window": {"type": "int", "default": 5, "min": 2, "max": 30},
                "volume_window": {"type": "int", "default": 20, "min": 5, "max": 120},
                "volatility_window": {"type": "int", "default": 20, "min": 5, "max": 120},
                "entry_threshold": {"type": "float", "default": 0.4, "min": 0.05, "max": 3.0},
                "exit_threshold": {"type": "float", "default": 0.1, "min": 0.0, "max": 1.5},
            },
        },
    ]


@router.get(
    "/",
    response_model=List[StrategyInfo],
    summary="获取所有可用策略",
)
async def get_strategies():
    """
    获取系统中所有可用的交易策略
    使用 lru_cache 缓存策略列表以提高性能
    """
    return _get_strategies_list()
