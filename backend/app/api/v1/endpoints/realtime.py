from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.data.realtime_manager import realtime_manager


router = APIRouter()


class SubscriptionRequest(BaseModel):
    """兼容层订阅请求。"""

    symbol: Optional[str] = None
    symbols: List[str] = Field(default_factory=list)


def _normalize_request_symbols(payload: SubscriptionRequest) -> List[str]:
    symbols = list(payload.symbols)
    if payload.symbol:
        symbols.append(payload.symbol)
    return realtime_manager._normalize_symbols(symbols)


def _compat_subscription_response(action: str, symbols: List[str]) -> dict:
    return {
        "success": True,
        "action": action,
        "symbols": symbols,
        "deprecated": True,
        "websocket": "/ws/quotes",
    }


@router.get("/quote/{symbol}", summary="获取实时报价")
async def get_quote(symbol: str):
    """获取股票的统一实时报价信息。"""
    data = realtime_manager.get_quote_dict(symbol, use_cache=False)
    if not data:
        raise HTTPException(status_code=404, detail=f"No realtime quote available for {symbol}")
    return {"success": True, "data": data}


@router.get("/quotes", summary="批量获取实时报价")
async def get_quotes(symbols: str):
    """批量获取股票的统一实时报价信息。"""
    symbol_list = realtime_manager._normalize_symbols(
        [raw_symbol for raw_symbol in symbols.split(",") if raw_symbol.strip()]
    )
    if not symbol_list:
        return {"success": True, "data": {}}

    results = realtime_manager.get_quotes_dict(symbol_list, use_cache=False)
    return {"success": True, "data": results}


@router.post("/subscribe", summary="兼容层：确认订阅请求", deprecated=True)
async def subscribe(payload: SubscriptionRequest):
    """兼容旧客户端的订阅确认接口，不维护持久订阅态。"""
    symbols = _normalize_request_symbols(payload)
    return _compat_subscription_response("subscribed", symbols)


@router.post("/unsubscribe", summary="兼容层：确认取消订阅请求", deprecated=True)
async def unsubscribe(payload: SubscriptionRequest):
    """兼容旧客户端的取消订阅确认接口，不维护持久订阅态。"""
    symbols = _normalize_request_symbols(payload)
    return _compat_subscription_response("unsubscribed", symbols)
