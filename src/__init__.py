"""
量化交易系统 - 前后端分离版本
"""

from .utils.version import APP_VERSION as __version__

from .data.data_manager import DataManager
from .strategy.strategies import (
    BaseStrategy,
    MovingAverageCrossover,
    RSIStrategy,
    BollingerBands,
    BuyAndHold,
)
from .strategy.advanced_strategies import (
    MeanReversionStrategy,
    MomentumStrategy,
    VWAPStrategy,
    StochasticOscillator,
    MACDStrategy,
    ATRTrailingStop,
    CombinedStrategy,
)
from .backtest.backtester import Backtester
from .analytics.dashboard import PerformanceAnalyzer

__all__ = [
    "DataManager",
    "BaseStrategy",
    "MovingAverageCrossover",
    "RSIStrategy",
    "BollingerBands",
    "BuyAndHold",
    "MeanReversionStrategy",
    "MomentumStrategy",
    "VWAPStrategy",
    "StochasticOscillator",
    "MACDStrategy",
    "ATRTrailingStop",
    "CombinedStrategy",
    "Backtester",
    "PerformanceAnalyzer",
]
