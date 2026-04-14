"""Cross-market backtesting API endpoints."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import List

from fastapi import APIRouter, HTTPException

from backend.app.schemas.cross_market import (
    CrossMarketBacktestRequest,
    CrossMarketBacktestResponse,
)
from src.backtest.cross_market_backtester import CrossMarketBacktester
from src.data.data_manager import DataManager

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_data_manager() -> DataManager:
    return DataManager()


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))


@router.get("/templates", summary="Get cross-market demo templates")
async def get_cross_market_templates():
    return {
        "templates": [
            {
                "id": "utilities_vs_growth",
                "name": "US utilities vs NASDAQ growth",
                "description": "Defensive regulated utilities against growth-heavy tech beta.",
                "theme": "Policy-fragile defensives vs growth beta",
                "theme_core": "policy_fragility_defensive",
                "theme_support": ["baseload_capacity", "department_chaos"],
                "execution_posture": "defensive_spread",
                "narrative": (
                    "When bureaucratic friction rises and physical grid demand keeps building, "
                    "regulated utilities can absorb capital while long-duration growth beta rerates lower."
                ),
                "strategy": "spread_zscore",
                "construction_mode": "equal_weight",
                "linked_factors": ["bureaucratic_friction", "policy_execution_disorder", "baseload_mismatch"],
                "linked_dimensions": ["project_pipeline", "logistics", "policy_execution"],
                "linked_tags": ["电网", "风电", "光伏", "政策治理"],
                "preferred_signal": "positive",
                "parameters": {"lookback": 20, "entry_threshold": 1.5, "exit_threshold": 0.5},
                "assets": [
                    {"symbol": "XLU", "asset_class": "ETF", "side": "long", "weight": 0.5},
                    {"symbol": "DUK", "asset_class": "US_STOCK", "side": "long", "weight": 0.5},
                    {"symbol": "QQQ", "asset_class": "ETF", "side": "short", "weight": 0.6},
                    {"symbol": "ARKK", "asset_class": "ETF", "side": "short", "weight": 0.4},
                ],
            },
            {
                "id": "copper_vs_semis",
                "name": "Copper futures vs semis ETF",
                "description": "Commodity tightness against semiconductor beta.",
                "theme": "Physical bottlenecks vs semiconductor beta",
                "theme_core": "physical_world_vs_ai_beta",
                "theme_support": ["inventory_tightness", "trade_flow"],
                "execution_posture": "commodity_vs_growth",
                "narrative": (
                    "When copper inventories tighten and trade frictions rise, upstream physical scarcity can "
                    "outperform semiconductor beta that already embeds optimistic AI demand."
                ),
                "strategy": "spread_zscore",
                "construction_mode": "equal_weight",
                "linked_factors": ["baseload_mismatch", "fx_mismatch"],
                "linked_dimensions": ["inventory", "trade", "logistics", "customs"],
                "linked_tags": ["半导体", "AI算力", "铜"],
                "preferred_signal": "positive",
                "parameters": {"lookback": 30, "entry_threshold": 1.6, "exit_threshold": 0.6},
                "assets": [
                    {"symbol": "HG=F", "asset_class": "COMMODITY_FUTURES", "side": "long", "weight": 1.0},
                    {"symbol": "SOXX", "asset_class": "ETF", "side": "short", "weight": 1.0},
                ],
            },
            {
                "id": "energy_vs_ai_apps",
                "name": "Energy infrastructure vs AI application ETF",
                "description": "Physical energy backbone against application-layer AI enthusiasm.",
                "theme": "Baseload scarcity vs AI application enthusiasm",
                "theme_core": "energy_backbone_vs_ai_apps",
                "theme_support": ["baseload_mismatch", "people_fragility"],
                "execution_posture": "physical_vs_narrative",
                "narrative": (
                    "When power bottlenecks and baseload mismatch worsen, the physical energy backbone can "
                    "outperform application-layer AI names whose demand assumptions are too smooth."
                ),
                "strategy": "spread_zscore",
                "construction_mode": "equal_weight",
                "linked_factors": ["baseload_mismatch", "tech_dilution", "people_fragility"],
                "linked_dimensions": ["investment_activity", "project_pipeline", "inventory", "people_layer"],
                "linked_tags": ["AI算力", "核电", "电网", "风电", "光伏", "人的维度"],
                "preferred_signal": "positive",
                "parameters": {"lookback": 25, "entry_threshold": 1.4, "exit_threshold": 0.5},
                "assets": [
                    {"symbol": "XLE", "asset_class": "ETF", "side": "long", "weight": 0.5},
                    {"symbol": "VDE", "asset_class": "ETF", "side": "long", "weight": 0.5},
                    {"symbol": "IGV", "asset_class": "ETF", "side": "short", "weight": 0.6},
                    {"symbol": "CLOU", "asset_class": "ETF", "side": "short", "weight": 0.4},
                ],
            },
            {
                "id": "defensive_beta_hedge",
                "name": "Defensive beta hedge (OLS)",
                "description": "Low-beta utility basket hedged against broad tech beta with rolling OLS.",
                "theme": "Talent dilution and defensive beta hedge",
                "theme_core": "defensive_beta_repricing",
                "theme_support": ["people_fragility", "tech_dilution"],
                "execution_posture": "ols_hedged_defensive",
                "narrative": (
                    "When tech leadership quality deteriorates or the market starts punishing weak execution, "
                    "a low-beta utility basket hedged against broad tech beta becomes a cleaner defensive expression."
                ),
                "strategy": "spread_zscore",
                "construction_mode": "ols_hedge",
                "linked_factors": ["bureaucratic_friction", "tech_dilution", "people_fragility"],
                "linked_dimensions": ["talent_structure", "logistics", "people_layer"],
                "linked_tags": ["AI算力", "电网", "人的维度"],
                "preferred_signal": "mixed",
                "parameters": {"lookback": 30, "entry_threshold": 1.4, "exit_threshold": 0.5},
                "assets": [
                    {"symbol": "XLU", "asset_class": "ETF", "side": "long", "weight": 0.6},
                    {"symbol": "DUK", "asset_class": "US_STOCK", "side": "long", "weight": 0.4},
                    {"symbol": "QQQ", "asset_class": "ETF", "side": "short", "weight": 1.0},
                ],
            },
            {
                "id": "rates_pressure_vs_duration_tech",
                "name": "Rates pressure vs duration tech",
                "description": "Treasury pressure proxy against long-duration software beta.",
                "theme": "Higher real-rate pressure vs duration-heavy tech",
                "theme_core": "rates_vs_duration",
                "theme_support": ["rate_curve_pressure", "credit_spread_stress"],
                "execution_posture": "macro_rate_spread",
                "narrative": (
                    "When rate-curve pressure and credit stress reprice duration, long-duration software beta "
                    "tends to be more fragile than listed rate/short-duration proxies."
                ),
                "strategy": "spread_zscore",
                "construction_mode": "equal_weight",
                "linked_factors": ["rate_curve_pressure", "credit_spread_stress"],
                "linked_dimensions": ["rates", "credit", "market_indicators"],
                "linked_tags": ["利率", "信用", "长久期科技"],
                "preferred_signal": "negative",
                "parameters": {"lookback": 25, "entry_threshold": 1.45, "exit_threshold": 0.55},
                "assets": [
                    {"symbol": "SHY", "asset_class": "ETF", "side": "long", "weight": 0.45},
                    {"symbol": "TIP", "asset_class": "ETF", "side": "long", "weight": 0.55},
                    {"symbol": "ARKK", "asset_class": "ETF", "side": "short", "weight": 0.5},
                    {"symbol": "IGV", "asset_class": "ETF", "side": "short", "weight": 0.5},
                ],
            },
            {
                "id": "dollar_squeeze_vs_china_beta",
                "name": "Dollar squeeze vs China beta",
                "description": "Dollar funding squeeze proxy against China beta ETFs/ADRs.",
                "theme": "Dollar mismatch vs China beta",
                "theme_core": "dollar_strength_vs_china_beta",
                "theme_support": ["fx_mismatch", "policy_execution_disorder"],
                "execution_posture": "fx_macro_spread",
                "narrative": (
                    "When dollar mismatch and policy execution noise rise together, China-beta assets can "
                    "underperform defensive dollar-linked proxies."
                ),
                "strategy": "spread_zscore",
                "construction_mode": "equal_weight",
                "linked_factors": ["fx_mismatch", "policy_execution_disorder"],
                "linked_dimensions": ["fx", "policy_execution", "trade"],
                "linked_tags": ["美元", "中概", "中国beta"],
                "preferred_signal": "negative",
                "parameters": {"lookback": 30, "entry_threshold": 1.55, "exit_threshold": 0.6},
                "assets": [
                    {"symbol": "UUP", "asset_class": "ETF", "side": "long", "weight": 1.0},
                    {"symbol": "FXI", "asset_class": "ETF", "side": "short", "weight": 0.55},
                    {"symbol": "KWEB", "asset_class": "ETF", "side": "short", "weight": 0.45},
                ],
            },
            {
                "id": "credit_stress_defensive_hedge",
                "name": "Credit stress defensive hedge",
                "description": "Defensive cashflow proxies against high-beta credit-sensitive equity.",
                "theme": "Credit spread stress vs fragile beta",
                "theme_core": "credit_stress_defensive",
                "theme_support": ["credit_spread_stress", "people_fragility"],
                "execution_posture": "defensive_credit_hedge",
                "narrative": (
                    "When credit spreads widen and leadership quality weakens, stable cashflow defensives can "
                    "outperform high-beta, financing-sensitive risk assets."
                ),
                "strategy": "spread_zscore",
                "construction_mode": "equal_weight",
                "linked_factors": ["credit_spread_stress", "people_fragility"],
                "linked_dimensions": ["credit", "people_layer", "source_health"],
                "linked_tags": ["信用压力", "防御现金流", "人的维度"],
                "preferred_signal": "positive",
                "parameters": {"lookback": 25, "entry_threshold": 1.35, "exit_threshold": 0.45},
                "assets": [
                    {"symbol": "USMV", "asset_class": "ETF", "side": "long", "weight": 0.5},
                    {"symbol": "VIG", "asset_class": "ETF", "side": "long", "weight": 0.5},
                    {"symbol": "HYG", "asset_class": "ETF", "side": "short", "weight": 0.45},
                    {"symbol": "IWM", "asset_class": "ETF", "side": "short", "weight": 0.55},
                ],
            },
            {
                "id": "people_decay_short_vs_cashflow_defensive",
                "name": "People decay short vs cashflow defensive",
                "description": "Short fragile-people-layer tech beta against stable cashflow defensives.",
                "theme": "People-layer decay vs resilient cashflow",
                "theme_core": "people_decay_short",
                "theme_support": ["people_fragility", "tech_dilution", "source_mode_summary"],
                "execution_posture": "people_fragility_pair",
                "narrative": (
                    "When people's-layer fragility, executive dilution and source degradation rise together, "
                    "the cleaner expression is to short fragile growth beta against resilient cashflow defensives."
                ),
                "strategy": "spread_zscore",
                "construction_mode": "equal_weight",
                "linked_factors": ["people_fragility", "tech_dilution", "policy_execution_disorder"],
                "linked_dimensions": ["people_layer", "policy_execution", "source_mode_summary"],
                "linked_tags": ["组织衰败", "技术稀释", "现金流防御"],
                "preferred_signal": "negative",
                "parameters": {"lookback": 20, "entry_threshold": 1.3, "exit_threshold": 0.45},
                "assets": [
                    {"symbol": "VIG", "asset_class": "ETF", "side": "long", "weight": 0.45},
                    {"symbol": "XLU", "asset_class": "ETF", "side": "long", "weight": 0.55},
                    {"symbol": "ARKK", "asset_class": "ETF", "side": "short", "weight": 0.5},
                    {"symbol": "QQQ", "asset_class": "ETF", "side": "short", "weight": 0.5},
                ],
            },
        ]
    }


@router.post(
    "/backtest",
    response_model=CrossMarketBacktestResponse,
    summary="Run cross-market backtest",
)
async def run_cross_market_backtest(request: CrossMarketBacktestRequest):
    try:
        if len(request.assets) < 2:
            raise HTTPException(status_code=400, detail="At least two assets are required")

        start_date = _parse_date(request.start_date)
        end_date = _parse_date(request.end_date)
        if start_date and end_date and start_date >= end_date:
            raise HTTPException(status_code=400, detail="Start date must be before end date")

        backtester = CrossMarketBacktester(
            data_manager=_get_data_manager(),
            initial_capital=request.initial_capital,
            commission=request.commission,
            slippage=request.slippage,
        )
        results = backtester.run(
            assets=[asset.model_dump() for asset in request.assets],
            template_context=request.template_context.model_dump() if request.template_context else None,
            allocation_constraints=(
                request.allocation_constraints.model_dump(exclude_none=True)
                if request.allocation_constraints
                else None
            ),
            strategy_name=request.strategy,
            parameters=request.parameters,
            start_date=start_date,
            end_date=end_date,
            construction_mode=request.construction_mode,
            min_history_days=request.min_history_days,
            min_overlap_ratio=request.min_overlap_ratio,
        )
        return {"success": True, "data": results, "error": None}
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning("Cross-market validation failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Cross-market backtest failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
