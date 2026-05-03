"""Pydantic models for paper trading endpoints (v0)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class PaperOrderRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=40)
    side: Literal["BUY", "SELL"]
    quantity: float = Field(..., gt=0)
    fill_price: float = Field(..., gt=0)
    commission: float = Field(default=0.0, ge=0)
    note: str = Field(default="", max_length=200)


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
