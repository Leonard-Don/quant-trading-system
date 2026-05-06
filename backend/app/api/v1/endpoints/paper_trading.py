"""Paper trading HTTP endpoints (v0).

A read/write surface over PaperTradingStore. Profile is resolved the same
way as research_journal so the workspace shares the per-browser identity.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from backend.app.schemas.paper_trading import (
    PaperOrderRequest,
    PaperResetRequest,
)
from backend.app.services.paper_trading import (
    PaperTradingError,
    paper_trading_store,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _resolve_profile(request: Request) -> str:
    header_profile = request.headers.get("X-Research-Profile")
    if header_profile:
        return header_profile
    realtime_profile = request.headers.get("X-Realtime-Profile")
    if realtime_profile:
        return realtime_profile
    query_profile = request.query_params.get("profile_id")
    if query_profile:
        return query_profile
    return "default"


@router.get("/account", summary="获取纸面账户当前状态")
async def get_paper_account(request: Request) -> dict:
    profile_id = _resolve_profile(request)
    return {"success": True, "data": paper_trading_store.get_account(profile_id=profile_id)}


@router.post("/orders", summary="提交一笔纸面订单（立即成交）")
async def submit_paper_order(payload: PaperOrderRequest, request: Request) -> dict:
    profile_id = _resolve_profile(request)
    try:
        result = paper_trading_store.submit_order(
            payload.model_dump(), profile_id=profile_id
        )
    except PaperTradingError as exc:
        # Business-rule rejection — distinguish from schema errors (400) with 422
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "data": result}


@router.get("/orders", summary="获取纸面订单历史")
async def list_paper_orders(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    profile_id = _resolve_profile(request)
    orders = paper_trading_store.list_orders(profile_id=profile_id, limit=limit)
    return {"success": True, "data": {"orders": orders, "limit": limit}}


@router.post("/reset", summary="重置纸面账户至初始资金")
async def reset_paper_account(payload: PaperResetRequest, request: Request) -> dict:
    profile_id = _resolve_profile(request)
    account = paper_trading_store.reset(
        initial_capital=payload.initial_capital, profile_id=profile_id
    )
    return {"success": True, "data": account}


@router.delete("/orders/{order_id}", summary="取消一笔挂单（仅 LIMIT pending）")
async def cancel_paper_order(order_id: str, request: Request) -> dict:
    profile_id = _resolve_profile(request)
    try:
        account = paper_trading_store.cancel_order(order_id, profile_id=profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"order {order_id} not found") from exc
    except PaperTradingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"success": True, "data": account}
