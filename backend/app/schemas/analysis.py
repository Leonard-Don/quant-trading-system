
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class TrendAnalysisRequest(BaseModel):
    symbol: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    interval: str = "1d"

class TrendAnalysisResponse(BaseModel):
    symbol: str
    trend: str
    score: float
    support_levels: List[float]
    resistance_levels: List[float]
    indicators: Dict[str, float]
    trend_details: Dict[str, Any]
    timestamp: str
    # 新增字段
    multi_timeframe: Optional[Dict[str, Any]] = None
    trend_strength: Optional[float] = None
    signal_strength: Optional[Dict[str, Any]] = None
    momentum: Optional[Dict[str, Any]] = None
    volatility: Optional[Dict[str, Any]] = None
    fibonacci_levels: Optional[Dict[str, Any]] = None
