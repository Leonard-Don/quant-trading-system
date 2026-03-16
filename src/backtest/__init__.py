from .backtester import Backtester
from .batch_backtester import BatchBacktester, WalkForwardAnalyzer

# 别名以保持兼容
BacktestEngine = Backtester

__all__ = ["Backtester", "BacktestEngine", "BatchBacktester", "WalkForwardAnalyzer"]

