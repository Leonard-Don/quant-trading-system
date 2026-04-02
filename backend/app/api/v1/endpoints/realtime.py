from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.services.realtime_alerts import realtime_alerts_store
from backend.app.services.realtime_journal import realtime_journal_store
from backend.app.services.realtime_preferences import realtime_preferences_store
from src.data.realtime_manager import realtime_manager


router = APIRouter()


class SubscriptionRequest(BaseModel):
    """兼容层订阅请求。"""

    symbol: Optional[str] = None
    symbols: List[str] = Field(default_factory=list)


class RealtimePreferencesRequest(BaseModel):
    symbols: List[str] = Field(default_factory=list)
    active_tab: str = "index"
    symbol_categories: dict[str, str] = Field(default_factory=dict)


class RealtimeAlertsRequest(BaseModel):
    alerts: List[dict] = Field(default_factory=list)
    alert_hit_history: List[dict] = Field(default_factory=list)


class RealtimeJournalRequest(BaseModel):
    review_snapshots: List[dict] = Field(default_factory=list)
    timeline_events: List[dict] = Field(default_factory=list)


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


def _infer_symbol_category(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return "other"
    if normalized.startswith("^"):
        return "index"
    if normalized.endswith((".SS", ".SZ")):
        return "cn"
    if normalized.endswith("-USD"):
        return "crypto"
    if normalized.endswith("=F"):
        return "future"
    if normalized in {"SPY", "QQQ", "IWM", "DIA", "UVXY", "VXX", "FXI", "EEM", "HYG"}:
        return "option"
    if normalized in {"TLT", "IEF", "SHY", "AGG", "BND", "LQD"} or normalized.startswith("^T"):
        return "bond"
    if normalized.isalpha() and len(normalized) <= 5:
        return "us"
    return "other"


def _build_symbol_metadata(symbol: str) -> dict:
    normalized = realtime_manager._normalize_symbol(symbol)
    display_name = normalized
    source = "fallback"

    quote = realtime_manager.get_quote_dict(normalized, use_cache=True) or {}
    for field in ("short_name", "long_name", "display_name", "name"):
        value = quote.get(field)
        if isinstance(value, str) and value.strip():
            display_name = value.strip()
            source = quote.get("source") or "quote"
            break

    if display_name == normalized:
        try:
            fundamental = realtime_manager.provider_factory.get_fundamental_data(normalized) or {}
            company_name = (
                fundamental.get("company_name")
                or fundamental.get("name")
                or fundamental.get("short_name")
            )
            if isinstance(company_name, str) and company_name.strip():
                display_name = company_name.strip()
                source = fundamental.get("source") or "fundamental"
        except Exception:
            pass

    return {
        "symbol": normalized,
        "en": display_name,
        "cn": display_name,
        "type": _infer_symbol_category(normalized),
        "source": source,
    }


@router.get("/quote/{symbol}", summary="获取实时报价")
async def get_quote(symbol: str):
    """获取股票的统一实时报价信息。"""
    data = realtime_manager.get_quote_dict(symbol, use_cache=True)
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

    results = realtime_manager.get_quotes_dict(symbol_list, use_cache=True)
    return {"success": True, "data": results}


@router.get("/summary", summary="获取实时行情运行摘要")
async def get_realtime_summary():
    from backend.app.websocket.connection_manager import manager

    summary = realtime_manager.get_market_summary()
    summary["websocket"] = {
        "connections": len(manager.subscriptions),
        "active_symbols": len(manager.active_connections),
    }
    return {"success": True, "data": summary}


@router.get("/metadata", summary="获取实时标的元数据")
async def get_realtime_metadata(symbols: str):
    symbol_list = realtime_manager._normalize_symbols(
        [raw_symbol for raw_symbol in symbols.split(",") if raw_symbol.strip()]
    )
    data = {
        symbol: _build_symbol_metadata(symbol)
        for symbol in symbol_list
    }
    return {"success": True, "data": data}


def _resolve_realtime_profile(request: Request) -> str:
    return request.headers.get("X-Realtime-Profile", "default")


@router.get("/preferences", summary="获取实时行情偏好配置")
async def get_preferences(request: Request):
    profile_id = _resolve_realtime_profile(request)
    return {"success": True, "data": realtime_preferences_store.get_preferences(profile_id=profile_id)}


@router.put("/preferences", summary="更新实时行情偏好配置")
async def update_preferences(payload: RealtimePreferencesRequest, request: Request):
    profile_id = _resolve_realtime_profile(request)
    data = realtime_preferences_store.update_preferences(payload.model_dump(), profile_id=profile_id)
    return {"success": True, "data": data}


@router.get("/alerts", summary="获取实时提醒规则")
async def get_alerts(request: Request):
    profile_id = _resolve_realtime_profile(request)
    return {"success": True, "data": realtime_alerts_store.get_alerts(profile_id=profile_id)}


@router.put("/alerts", summary="更新实时提醒规则")
async def update_alerts(payload: RealtimeAlertsRequest, request: Request):
    profile_id = _resolve_realtime_profile(request)
    data = realtime_alerts_store.update_alerts(payload.model_dump(), profile_id=profile_id)
    return {"success": True, "data": data}


@router.get("/journal", summary="获取实时行情复盘与时间线")
async def get_journal(request: Request):
    profile_id = _resolve_realtime_profile(request)
    return {"success": True, "data": realtime_journal_store.get_journal(profile_id=profile_id)}


@router.put("/journal", summary="更新实时行情复盘与时间线")
async def update_journal(payload: RealtimeJournalRequest, request: Request):
    profile_id = _resolve_realtime_profile(request)
    data = realtime_journal_store.update_journal(payload.model_dump(), profile_id=profile_id)
    return {"success": True, "data": data}


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
