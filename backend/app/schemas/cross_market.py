"""Schemas for cross-market backtesting."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class CrossMarketAsset(BaseModel):
    symbol: str = Field(..., description="Ticker symbol, e.g. XLU")
    asset_class: str
    side: str
    weight: Optional[float] = Field(default=None, gt=0)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("symbol is required")
        return value


class CrossMarketBacktestRequest(BaseModel):
    assets: List[CrossMarketAsset]
    strategy: str = "spread_zscore"
    construction_mode: str = "equal_weight"
    parameters: Dict[str, Any] = Field(
        default_factory=lambda: {
            "lookback": 20,
            "entry_threshold": 1.5,
            "exit_threshold": 0.5,
        }
    )
    min_history_days: int = 60
    min_overlap_ratio: float = 0.7
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = Field(default=100000, gt=0)
    commission: float = Field(default=0.001, ge=0)
    slippage: float = Field(default=0.001, ge=0)


class CrossMarketBacktestResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
