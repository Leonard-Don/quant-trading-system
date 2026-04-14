from pydantic import BaseModel, Field
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
    fixed_commission: float = 0.0
    min_commission: float = 0.0
    market_impact_bps: float = 0.0
    market_impact_model: str = "constant"
    impact_reference_notional: float = 100000.0
    impact_coefficient: float = 1.0
    permanent_impact_bps: float = 0.0
    max_holding_days: Optional[int] = None

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
    fixed_commission: float = 0.0
    min_commission: float = 0.0
    market_impact_bps: float = 0.0
    market_impact_model: str = "constant"
    impact_reference_notional: float = 100000.0
    impact_coefficient: float = 1.0
    permanent_impact_bps: float = 0.0
    max_holding_days: Optional[int] = None


class BatchBacktestRequest(BaseModel):
    tasks: List[BatchBacktestTaskRequest] = Field(..., min_length=1, max_length=50)
    ranking_metric: str = "sharpe_ratio"
    ascending: bool = False
    top_n: Optional[int] = None
    max_workers: int = Field(default=4, ge=1, le=8)
    use_processes: bool = False
    timeout_seconds: float = Field(default=60.0, gt=0, le=600)


class WalkForwardRequest(BaseModel):
    symbol: str
    strategy: str
    parameters: Dict[str, Any] = {}
    parameter_grid: Optional[Dict[str, List[Any]]] = None
    parameter_candidates: Optional[List[Dict[str, Any]]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 10000
    commission: float = 0.001
    slippage: float = 0.001
    fixed_commission: float = 0.0
    min_commission: float = 0.0
    market_impact_bps: float = 0.0
    market_impact_model: str = "constant"
    impact_reference_notional: float = 100000.0
    impact_coefficient: float = 1.0
    permanent_impact_bps: float = 0.0
    max_holding_days: Optional[int] = None
    train_period: int = 252
    test_period: int = 63
    step_size: int = 21
    optimization_metric: str = "sharpe_ratio"
    optimization_method: str = "grid"
    optimization_budget: Optional[int] = None
    monte_carlo_simulations: int = Field(default=250, ge=10, le=10000)
    timeout_seconds: float = Field(default=60.0, gt=0, le=600)


class MarketRegimeRequest(BaseModel):
    symbol: str
    strategy: str
    parameters: Dict[str, Any] = {}
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 10000
    commission: float = 0.001
    slippage: float = 0.001
    fixed_commission: float = 0.0
    min_commission: float = 0.0
    market_impact_bps: float = 0.0
    market_impact_model: str = "constant"
    impact_reference_notional: float = 100000.0
    impact_coefficient: float = 1.0
    permanent_impact_bps: float = 0.0
    max_holding_days: Optional[int] = None
    lookback_days: int = 20
    trend_threshold: float = 0.03


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
    fixed_commission: float = 0.0
    min_commission: float = 0.0
    market_impact_bps: float = 0.0
    market_impact_model: str = "constant"
    impact_reference_notional: float = 100000.0
    impact_coefficient: float = 1.0
    permanent_impact_bps: float = 0.0
    min_trade_value: float = 0.0
    min_rebalance_weight_delta: float = 0.0
    max_turnover_per_rebalance: Optional[float] = None


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
