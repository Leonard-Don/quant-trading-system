"""
另类数据 API 端点。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.data.alternative import AltDataManager

logger = logging.getLogger(__name__)
router = APIRouter()

_alt_data_manager: Optional[AltDataManager] = None


def _get_manager() -> AltDataManager:
    global _alt_data_manager
    if _alt_data_manager is None:
        _alt_data_manager = AltDataManager()
    return _alt_data_manager


@router.get("/snapshot", summary="另类数据作战快照")
async def get_alt_data_snapshot(refresh: bool = Query(default=False)):
    try:
        return _get_manager().get_dashboard_snapshot(refresh=refresh)
    except Exception as exc:
        logger.error("Failed to load alt-data snapshot: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/signals", summary="另类数据统一信号")
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


@router.get("/providers", summary="另类数据提供器状态")
async def get_alt_providers():
    try:
        manager = _get_manager()
        return {
            "providers": {
                name: provider.get_provider_info()
                for name, provider in manager.providers.items()
            }
        }
    except Exception as exc:
        logger.error("Failed to load alt-data providers: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
