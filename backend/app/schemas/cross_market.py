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


class CrossMarketTemplateAsset(CrossMarketAsset):
    pass


class CrossMarketTemplateContext(BaseModel):
    template_id: Optional[str] = None
    template_name: Optional[str] = None
    theme: Optional[str] = None
    allocation_mode: Optional[str] = None
    bias_summary: Optional[str] = None
    bias_strength_raw: Optional[float] = None
    bias_strength: Optional[float] = None
    bias_scale: Optional[float] = None
    bias_quality_label: Optional[str] = None
    bias_quality_reason: Optional[str] = None
    base_recommendation_score: Optional[float] = None
    recommendation_score: Optional[float] = None
    base_recommendation_tier: Optional[str] = None
    recommendation_tier: Optional[str] = None
    ranking_penalty: Optional[float] = None
    ranking_penalty_reason: Optional[str] = None
    input_reliability_label: Optional[str] = None
    input_reliability_score: Optional[float] = None
    input_reliability_lead: Optional[str] = None
    input_reliability_posture: Optional[str] = None
    input_reliability_reason: Optional[str] = None
    input_reliability_action_hint: Optional[str] = None
    department_chaos_label: Optional[str] = None
    department_chaos_score: Optional[float] = None
    department_chaos_top_department: Optional[str] = None
    department_chaos_reason: Optional[str] = None
    department_chaos_risk_budget_scale: Optional[float] = None
    policy_execution_label: Optional[str] = None
    policy_execution_score: Optional[float] = None
    policy_execution_top_department: Optional[str] = None
    policy_execution_reason: Optional[str] = None
    policy_execution_risk_budget_scale: Optional[float] = None
    people_fragility_label: Optional[str] = None
    people_fragility_score: Optional[float] = None
    people_fragility_focus: Optional[str] = None
    people_fragility_reason: Optional[str] = None
    people_fragility_risk_budget_scale: Optional[float] = None
    source_mode_label: Optional[str] = None
    source_mode_dominant: Optional[str] = None
    source_mode_reason: Optional[str] = None
    source_mode_risk_budget_scale: Optional[float] = None
    structural_decay_radar_label: Optional[str] = None
    structural_decay_radar_display_label: Optional[str] = None
    structural_decay_radar_score: Optional[float] = None
    structural_decay_radar_action_hint: Optional[str] = None
    structural_decay_radar_risk_budget_scale: Optional[float] = None
    structural_decay_radar_top_signals: List[Dict[str, Any]] = Field(default_factory=list)
    bias_highlights_raw: List[str] = Field(default_factory=list)
    bias_highlights: List[str] = Field(default_factory=list)
    bias_actions: List[Dict[str, Any]] = Field(default_factory=list)
    signal_attribution: List[Dict[str, Any]] = Field(default_factory=list)
    driver_summary: List[Dict[str, Any]] = Field(default_factory=list)
    dominant_drivers: List[Dict[str, Any]] = Field(default_factory=list)
    core_legs: List[Dict[str, Any]] = Field(default_factory=list)
    support_legs: List[Dict[str, Any]] = Field(default_factory=list)
    theme_core: Optional[str] = None
    theme_support: Optional[str] = None
    execution_posture: Optional[str] = None
    base_assets: List[CrossMarketTemplateAsset] = Field(default_factory=list)
    raw_bias_assets: List[CrossMarketTemplateAsset] = Field(default_factory=list)


class CrossMarketAllocationConstraints(BaseModel):
    max_single_weight: Optional[float] = Field(default=None, gt=0, le=1)
    min_single_weight: Optional[float] = Field(default=None, gt=0, le=1)

    @field_validator("min_single_weight")
    @classmethod
    def validate_bounds(cls, value: Optional[float], info):
        max_single_weight = info.data.get("max_single_weight")
        if value is not None and max_single_weight is not None and value > max_single_weight:
            raise ValueError("min_single_weight cannot be greater than max_single_weight")
        return value


class CrossMarketBacktestRequest(BaseModel):
    assets: List[CrossMarketAsset] = Field(..., min_length=1, max_length=50)
    template_context: Optional[CrossMarketTemplateContext] = None
    allocation_constraints: Optional[CrossMarketAllocationConstraints] = None
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
