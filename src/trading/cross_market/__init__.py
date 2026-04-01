"""Cross-market trading primitives."""

from .asset_universe import AssetClass, AssetSide, AssetSpec, AssetUniverse
from .cross_market_strategy import (
    CrossMarketStrategy,
    SpreadZScoreStrategy,
    CointegrationReversionStrategy,
)
from .execution_router import ExecutionRouter
from .hedge_portfolio import HedgePortfolioBuilder

__all__ = [
    "AssetClass",
    "AssetSide",
    "AssetSpec",
    "AssetUniverse",
    "CrossMarketStrategy",
    "SpreadZScoreStrategy",
    "CointegrationReversionStrategy",
    "ExecutionRouter",
    "HedgePortfolioBuilder",
]
