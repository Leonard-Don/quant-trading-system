"""
量化交易系统 - 前后端分离版本
"""

from .analytics.dashboard import PerformanceAnalyzer
from .backtest.backtester import Backtester
from .data.data_manager import DataManager
from .strategy.advanced_strategies import (
    ATRTrailingStop,
    CombinedStrategy,
    MACDStrategy,
    MeanReversionStrategy,
    MomentumStrategy,
    StochasticOscillator,
    VWAPStrategy,
)
from .strategy.strategies import (
    BaseStrategy,
    BollingerBands,
    BuyAndHold,
    MovingAverageCrossover,
    RSIStrategy,
)
from .utils.version import APP_VERSION as __version__

__all__ = [
    "__version__",
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
