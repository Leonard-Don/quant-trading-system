
from typing import Any, Optional

from pydantic import BaseModel


class TrendAnalysisRequest(BaseModel):
    symbol: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    interval: str = "1d"

class TrendAnalysisResponse(BaseModel):
    symbol: str
    trend: str
    score: float
    support_levels: list[float]
    resistance_levels: list[float]
    indicators: dict[str, float]
    trend_details: dict[str, Any]
    timestamp: str
    # 新增字段
    multi_timeframe: Optional[dict[str, Any]] = None
    trend_strength: Optional[float] = None
    signal_strength: Optional[dict[str, Any]] = None
    momentum: Optional[dict[str, Any]] = None
    volatility: Optional[dict[str, Any]] = None
    fibonacci_levels: Optional[dict[str, Any]] = None


class LowVolatilityScreenItem(BaseModel):
    """A single ranked name in the low-volatility screen."""

    rank: int
    symbol: str
    name: Optional[str] = None
    realized_vol: float
    annualized_vol: float
    recent_return: Optional[float] = None
    n_bars: int


class LowVolatilityScreenResponse(BaseModel):
    """Point-in-time low-volatility ranking of an index universe.

    A SCREEN (cross-sectional ranking), not a portfolio backtest. ``count`` is
    the number of names actually ranked — it can be below the universe size when
    some constituents' prices could not be fetched.
    """

    as_of: str
    universe: str
    window: int
    count: int
    items: list[LowVolatilityScreenItem]
    disclaimer: str
