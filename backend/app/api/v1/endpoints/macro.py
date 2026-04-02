"""
宏观错误定价因子 API。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from src.analytics.macro_factors import FactorCombiner, MacroHistoryStore, build_default_registry
from src.data.alternative import get_alt_data_manager
from src.data.data_manager import DataManager
from .macro_evidence import build_factor_evidence, build_overall_evidence
from .macro_quality import (
    apply_conflict_penalty,
    build_input_reliability_summary,
)
from .macro_support import (
    FACTOR_WEIGHTS,
    build_macro_trend,
    build_resonance_summary,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_registry = build_default_registry()
_combiner = FactorCombiner()
_history_store = MacroHistoryStore()
_market_data_manager = DataManager()


def _build_context(refresh: bool = False):
    manager = get_alt_data_manager()
    snapshot = manager.get_dashboard_snapshot(refresh=refresh)
    return {
        "snapshot_timestamp": snapshot.get("snapshot_timestamp"),
        "signals": snapshot.get("signals", {}),
        "records": manager.get_records(timeframe="45d", limit=200),
        "market_indicators": _market_data_manager.get_market_indicators(),
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
            weights=FACTOR_WEIGHTS,
        )
        overview = {
            "snapshot_timestamp": context["snapshot_timestamp"],
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
            "evidence_summary": build_overall_evidence(context),
        }
        for factor in overview["factors"]:
            factor.setdefault("metadata", {})
            factor["metadata"]["evidence_summary"] = build_factor_evidence(factor.get("name", ""), context)
        overview = apply_conflict_penalty(overview)
        overview["input_reliability_summary"] = build_input_reliability_summary(overview)
        previous = _history_store.get_previous_snapshot(context["snapshot_timestamp"])
        overview["trend"] = build_macro_trend(overview, previous)
        overview["resonance_summary"] = build_resonance_summary(overview)
        _history_store.append_snapshot(overview)
        overview["history_length"] = len(_history_store.list_snapshots(limit=1000))
        return overview
    except Exception as exc:
        logger.error("Failed to build macro overview: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history", summary="宏观错误定价历史", deprecated=True)
async def get_macro_history(limit: int = Query(default=30, ge=1, le=200)):
    try:
        records = _history_store.list_snapshots(limit=limit)
        return {
            "records": records,
            "count": len(records),
        }
    except Exception as exc:
        logger.error("Failed to fetch macro history: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
