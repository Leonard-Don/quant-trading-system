"""
另类数据 API 端点。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.data.alternative import get_alt_data_manager, get_alt_data_scheduler

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_manager():
    return get_alt_data_manager()


def _get_scheduler():
    return get_alt_data_scheduler()


@router.get("/snapshot", summary="另类数据作战快照")
async def get_alt_data_snapshot(refresh: bool = Query(default=False)):
    try:
        return _get_manager().get_dashboard_snapshot(refresh=refresh)
    except Exception as exc:
        logger.error("Failed to load alt-data snapshot: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/signals", summary="另类数据统一信号", deprecated=True)
async def get_alt_signals(
    category: Optional[str] = Query(default=None),
    timeframe: str = Query(default="7d"),
    refresh: bool = Query(default=False),
):
    try:
        manager = _get_manager()
        if refresh:
            manager.refresh_all(force=True)
        return manager.get_alt_signals(
            category=category,
            timeframe=timeframe,
            refresh_if_empty=True,
        )
    except Exception as exc:
        logger.error("Failed to load alt-data signals: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/providers", summary="另类数据提供器状态", deprecated=True)
async def get_alt_providers():
    try:
        manager = _get_manager()
        return {
            "providers": manager.get_provider_status(),
            "refresh_status": manager.get_refresh_status_dict(),
            "provider_health": manager._build_provider_health(),
        }
    except Exception as exc:
        logger.error("Failed to load alt-data providers: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status", summary="另类数据治理状态")
async def get_alt_data_status():
    try:
        manager = _get_manager()
        return manager.get_status(scheduler_status=_get_scheduler().get_status())
    except Exception as exc:
        logger.error("Failed to load alt-data status: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/refresh", summary="手动刷新另类数据")
async def refresh_alt_data(provider: str = Query(default="all")):
    try:
        manager = _get_manager()
        if provider == "all":
            return manager.refresh_all(force=True)
        if provider not in manager.providers:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
        signal = manager.refresh_provider(provider, force=True)
        status = manager.refresh_status[provider].to_dict()
        snapshot = manager.get_dashboard_snapshot(refresh=False)
        return {
            "requested_provider": provider,
            "status": "success" if status["status"] == "success" else "partial",
            "ok": status["status"] == "success",
            "signals": {provider: signal},
            "refresh_status": {provider: status},
            "snapshot_timestamp": snapshot.get("snapshot_timestamp"),
            "completed_at": snapshot.get("snapshot_timestamp"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to refresh alt-data: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history", summary="另类数据历史记录")
async def get_alt_data_history(
    category: Optional[str] = Query(default=None),
    timeframe: str = Query(default="30d"),
    limit: int = Query(default=50, ge=1, le=500),
):
    try:
        manager = _get_manager()
        records = manager.get_records(category=category, timeframe=timeframe, limit=limit)
        history_analysis = manager.analyze_history(records)
        snapshot = manager.get_dashboard_snapshot(refresh=False)
        return {
            "records": [record.to_dict() for record in records],
            "count": len(records),
            "category": category,
            "timeframe": timeframe,
            "snapshot_timestamp": snapshot.get("snapshot_timestamp"),
            "category_series": history_analysis.get("category_series", {}),
            "category_trends": history_analysis.get("category_trends", {}),
            "overall_trend": history_analysis.get("overall_trend", {}),
            "evidence_summary": manager.build_evidence_summary(records, limit=8),
        }
    except Exception as exc:
        logger.error("Failed to load alt-data history: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
