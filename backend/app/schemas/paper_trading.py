"""Pydantic models for paper trading endpoints (v0)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class PaperOrderRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=40)
    side: Literal["BUY", "SELL"]
    quantity: float = Field(..., gt=0)
    fill_price: float = Field(..., gt=0)
    # Execution slippage in basis points (1 bp = 0.01%).
    # Capped at 100 bp (1%) to prevent obviously-mistyped catastrophes
    # like 5000 ("user meant 5%" → silently fills 50% off).
    slippage_bps: float = Field(default=0.0, ge=0, le=100)
    commission: float = Field(default=0.0, ge=0)
    note: str = Field(default="", max_length=200)
    # Optional stop-loss as a fraction of avg_cost. Only meaningful on BUY;
    # SELL ignores it. Capped at 0.5 (50% drawdown) — anything wider is
    # almost certainly a typo.
    stop_loss_pct: Optional[float] = Field(default=None, ge=0, le=0.5)
    # Optional take-profit as a fraction of avg_cost. Symmetric mirror of
    # stop_loss_pct: triggers an auto-SELL when last_price ≥ avg_cost ×
    # (1 + pct). Capped at 5.0 (a 500% gain target — anything beyond
    # that is almost certainly a typo).
    take_profit_pct: Optional[float] = Field(default=None, ge=0, le=5.0)


class PaperResetRequest(BaseModel):
    initial_capital: Optional[float] = Field(default=None, gt=0)


class PaperPosition(BaseModel):
    symbol: str
    quantity: float
    avg_cost: float
    opened_at: str
    updated_at: str


class PaperOrderRecord(BaseModel):
    id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float
    fill_price: float
    commission: float
    submitted_at: str
    note: str = ""


class PaperAccountResponse(BaseModel):
    profile_id: str
    initial_capital: float
    cash: float
    positions: list[PaperPosition]
    orders_count: int
    created_at: str
    updated_at: str
