"""
宏观错误定价因子 API。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from src.analytics.macro_factors import FactorCombiner, build_default_registry
from src.data.alternative import get_alt_data_manager

logger = logging.getLogger(__name__)
router = APIRouter()

_registry = build_default_registry()
_combiner = FactorCombiner()


def _build_context(refresh: bool = False):
    manager = get_alt_data_manager()
    snapshot = manager.get_dashboard_snapshot(refresh=refresh)
    return {
        "signals": snapshot.get("signals", {}),
        "records": manager.get_records(timeframe="30d", limit=200),
        "provider_status": snapshot.get("providers", {}),
        "refresh_status": snapshot.get("refresh_status", {}),
        "data_freshness": snapshot.get("staleness", {}),
        "provider_health": snapshot.get("provider_health", {}),
    }


@router.get("/overview", summary="宏观错误定价总览")
async def get_macro_overview(refresh: bool = Query(default=False)):
    try:
        context = _build_context(refresh=refresh)
        factor_results = _registry.compute_all(context)
        combined = _combiner.combine(
            factor_results,
            weights={
                "bureaucratic_friction": 1.0,
                "tech_dilution": 0.9,
                "baseload_mismatch": 1.1,
            },
        )
        return {
            "macro_score": combined["score"],
            "macro_signal": combined["signal"],
            "confidence": combined["confidence"],
            "factors": combined["factors"],
            "providers": context["provider_status"],
            "provider_status": context["provider_status"],
            "refresh_status": context["refresh_status"],
            "data_freshness": context["data_freshness"],
            "provider_health": context["provider_health"],
            "signals": context["signals"],
        }
    except Exception as exc:
        logger.error("Failed to build macro overview: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
