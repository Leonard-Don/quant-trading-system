from pydantic import BaseModel
from typing import Optional, Dict, Any, List

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


class BatchBacktestTaskRequest(BaseModel):
    task_id: Optional[str] = None
    research_label: Optional[str] = None
    symbol: str
    strategy: str
    parameters: Dict[str, Any] = {}
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 10000
    commission: float = 0.001
    slippage: float = 0.001


class BatchBacktestRequest(BaseModel):
    tasks: List[BatchBacktestTaskRequest]
    ranking_metric: str = "sharpe_ratio"
    ascending: bool = False
    top_n: Optional[int] = None
    max_workers: int = 4


class WalkForwardRequest(BaseModel):
    symbol: str
    strategy: str
    parameters: Dict[str, Any] = {}
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 10000
    commission: float = 0.001
    slippage: float = 0.001
    train_period: int = 252
    test_period: int = 63
    step_size: int = 21


class PortfolioStrategyRequest(BaseModel):
    symbols: List[str]
    strategy: str
    parameters: Dict[str, Any] = {}
    weights: Optional[List[float]] = None
    objective: str = "equal_weight"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 10000
    commission: float = 0.001
    slippage: float = 0.001


class AdvancedHistorySaveRequest(BaseModel):
    record_type: str
    title: Optional[str] = None
    symbol: str
    strategy: str
    parameters: Dict[str, Any] = {}
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    metrics: Dict[str, Any] = {}
    result: Dict[str, Any]
