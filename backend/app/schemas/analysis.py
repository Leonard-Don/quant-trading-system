
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
