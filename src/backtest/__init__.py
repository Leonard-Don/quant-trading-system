from .base_backtester import BaseBacktester
from .backtester import Backtester
from .portfolio_backtester import PortfolioBacktester
from .batch_backtester import BatchBacktester, WalkForwardAnalyzer
from .cross_market_backtester import CrossMarketBacktester
from .execution_engine import PortfolioExecutionConfig, PortfolioExecutionEngine
from .signal_adapter import SignalAdapter, NormalizedSingleAssetSignals
from .risk_manager import RiskManager, RiskContext, RiskAction, RiskDecision
from .position_sizer import (
    BasePositionSizer,
    FixedFractionSizer,
    KellyCriterionSizer,
    VolatilityTargetSizer,
    EqualRiskSizer,
    SizingContext,
    SizingResult,
    create_position_sizer,
)

# 别名以保持兼容
BacktestEngine = Backtester

__all__ = [
    "BaseBacktester",
    "Backtester",
    "PortfolioBacktester",
    "BacktestEngine",
    "BatchBacktester",
    "WalkForwardAnalyzer",
    "CrossMarketBacktester",
    "PortfolioExecutionConfig",
    "PortfolioExecutionEngine",
    "SignalAdapter",
    "NormalizedSingleAssetSignals",
    "RiskManager",
    "RiskContext",
    "RiskAction",
    "RiskDecision",
    "BasePositionSizer",
    "FixedFractionSizer",
    "KellyCriterionSizer",
    "VolatilityTargetSizer",
    "EqualRiskSizer",
    "SizingContext",
    "SizingResult",
    "create_position_sizer",
]
