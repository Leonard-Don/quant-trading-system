
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


class LowVolPortfolioEquityPoint(BaseModel):
    """One rebalance-dated point on the growth-of-1 equity curve."""

    date: str
    basket_gross: float
    basket_net: float
    benchmark: float


class LowVolPortfolioLegMetrics(BaseModel):
    """Risk/return metrics for one leg (gross / net / benchmark).

    Fields are Optional because a too-short or empty series yields an empty
    metrics dict in the pure core (CAGR/Sharpe undefined for <2 periods).
    """

    total_return: Optional[float] = None
    cagr: Optional[float] = None
    ann_vol: Optional[float] = None
    sharpe: Optional[float] = None
    max_drawdown: Optional[float] = None
    n_periods: Optional[int] = None


class LowVolPortfolioMetrics(BaseModel):
    gross: LowVolPortfolioLegMetrics
    net: LowVolPortfolioLegMetrics
    benchmark: LowVolPortfolioLegMetrics


class LowVolPortfolioBacktestResponse(BaseModel):
    """Net-of-cost low-volatility long-only basket backtest vs equal-weight.

    Monthly rebalance, bottom-``basket_n`` lowest-realized-vol names, total-
    return prices, A-share frictions on turnover. ``benchmark`` is equal-weight
    of the same eligible universe (gross). ``disclaimer`` is shown prominently
    in the UI and is honest about the CSI500 marginality.
    """

    universe: str
    index_code: str
    span: str
    window: int
    basket_n: int
    n_periods: int
    avg_annual_turnover: Optional[float] = None
    cost_rates: dict[str, float]
    equity_curve: list[LowVolPortfolioEquityPoint]
    metrics: LowVolPortfolioMetrics
    as_of: str
    disclaimer: str
