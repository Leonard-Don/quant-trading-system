
from pydantic import BaseModel
from typing import Optional, Dict, Any

class BacktestRequest(BaseModel):
    symbol: str
    strategy: str
    parameters: Dict[str, Any] = {}
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 10000
    commission: float = 0.001
    slippage: float = 0.001

class BacktestResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
