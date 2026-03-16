
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class StrategyInfo(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]

class MarketDataRequest(BaseModel):
    symbol: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    interval: str = "1d"
    period: Optional[str] = None
