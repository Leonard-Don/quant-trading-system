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
                "narrative": (
                    "When bureaucratic friction rises and physical grid demand keeps building, "
                    "regulated utilities can absorb capital while long-duration growth beta rerates lower."
                ),
                "strategy": "spread_zscore",
                "construction_mode": "equal_weight",
                "linked_factors": ["bureaucratic_friction", "baseload_mismatch"],
                "linked_dimensions": ["project_pipeline", "logistics"],
                "linked_tags": ["电网", "风电", "光伏"],
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
                "narrative": (
                    "When copper inventories tighten and trade frictions rise, upstream physical scarcity can "
                    "outperform semiconductor beta that already embeds optimistic AI demand."
                ),
                "strategy": "spread_zscore",
                "construction_mode": "equal_weight",
                "linked_factors": ["baseload_mismatch"],
                "linked_dimensions": ["inventory", "trade", "logistics"],
                "linked_tags": ["半导体", "AI算力"],
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
                "narrative": (
                    "When power bottlenecks and baseload mismatch worsen, the physical energy backbone can "
                    "outperform application-layer AI names whose demand assumptions are too smooth."
                ),
                "strategy": "spread_zscore",
                "construction_mode": "equal_weight",
                "linked_factors": ["baseload_mismatch", "tech_dilution"],
                "linked_dimensions": ["investment_activity", "project_pipeline", "inventory"],
                "linked_tags": ["AI算力", "核电", "电网", "风电", "光伏"],
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
                "narrative": (
                    "When tech leadership quality deteriorates or the market starts punishing weak execution, "
                    "a low-beta utility basket hedged against broad tech beta becomes a cleaner defensive expression."
                ),
                "strategy": "spread_zscore",
                "construction_mode": "ols_hedge",
                "linked_factors": ["bureaucratic_friction", "tech_dilution"],
                "linked_dimensions": ["talent_structure", "logistics"],
                "linked_tags": ["AI算力", "电网"],
                "preferred_signal": "mixed",
                "parameters": {"lookback": 30, "entry_threshold": 1.4, "exit_threshold": 0.5},
                "assets": [
                    {"symbol": "XLU", "asset_class": "ETF", "side": "long", "weight": 0.6},
                    {"symbol": "DUK", "asset_class": "US_STOCK", "side": "long", "weight": 0.4},
                    {"symbol": "QQQ", "asset_class": "ETF", "side": "short", "weight": 1.0},
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
