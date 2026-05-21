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
    "ATRTrailingStop",
    "Backtester",
    "BaseStrategy",
    "BollingerBands",
    "BuyAndHold",
    "CombinedStrategy",
    "DataManager",
    "MACDStrategy",
    "MeanReversionStrategy",
    "MomentumStrategy",
    "MovingAverageCrossover",
    "PerformanceAnalyzer",
    "RSIStrategy",
    "StochasticOscillator",
    "VWAPStrategy",
    "__version__",
]
