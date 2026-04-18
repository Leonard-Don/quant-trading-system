from datetime import datetime, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from backend.app.services.realtime_alerts import realtime_alerts_store
from backend.app.services.realtime_journal import realtime_journal_store
from backend.app.services.realtime_preferences import realtime_preferences_store
from src.data.data_manager import DataManager
from src.data.realtime_manager import realtime_manager


router = APIRouter()
data_manager = DataManager()

MAX_SYMBOLS_PER_REQUEST = 100
MAX_SYMBOLS_PER_WATCH_GROUP = 200
MAX_WATCH_GROUPS = 20


class SubscriptionRequest(BaseModel):
    """兼容层订阅请求。"""

    symbol: Optional[str] = None
    symbols: List[str] = Field(default_factory=list)


class RealtimePreferencesRequest(BaseModel):
    symbols: List[str] = Field(default_factory=list)
    active_tab: str = "index"
    symbol_categories: dict[str, str] = Field(default_factory=dict)
    watch_groups: List[dict] = Field(default_factory=list)


class RealtimeAlertsRequest(BaseModel):
    alerts: List[dict] = Field(default_factory=list)
    alert_hit_history: List[dict] = Field(default_factory=list)


class RealtimeAlertHitRequest(BaseModel):
    entry: dict = Field(default_factory=dict)
    notify_channels: List[str] = Field(default_factory=list)
    create_workbench_task: bool = Field(
        default=False,
        description="兼容旧客户端的保留字段。公开仓会忽略该值，不再创建研究工作台任务。",
    )
    persist_event_record: bool = True
    severity: str = "warning"


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
    if normalized in {"SPY", "QQQ", "IWM", "DIA", "UVXY", "VXX", "FXI", "EEM"}:
        return "us"
    if normalized in {"TLT", "IEF", "SHY", "AGG", "BND", "LQD", "HYG"} or normalized.startswith("^T"):
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


def _number_or_none(value: Any) -> Optional[float]:
    try:
        numeric = float(value)
        if numeric != numeric:
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _load_replay_frame(
    symbol: str,
    *,
    period: str = "3mo",
    interval: str = "1d",
    limit: int = 240,
) -> pd.DataFrame:
    normalized = realtime_manager._normalize_symbol(symbol)
    safe_limit = max(30, min(int(limit or 240), 2000))
    allowed_intervals = {"1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"}
    if interval not in allowed_intervals:
        raise HTTPException(status_code=400, detail=f"Unsupported interval: {interval}")

    if period:
        data = data_manager.get_historical_data(
            symbol=normalized,
            interval=interval,
            period=period,
        )
    else:
        end_date = datetime.now()
        data = data_manager.get_historical_data(
            symbol=normalized,
            start_date=end_date - timedelta(days=120),
            end_date=end_date,
            interval=interval,
        )

    if data is None or data.empty:
        raise HTTPException(status_code=404, detail=f"No replay data available for {normalized}")

    frame = data.tail(safe_limit).copy()
    frame.columns = [str(column).lower().replace(" ", "_") for column in frame.columns]
    close_series = frame["close"] if "close" in frame.columns else frame.get("adj_close")
    frame["close"] = pd.to_numeric(close_series, errors="coerce")
    if "volume" in frame.columns:
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)
    else:
        frame["volume"] = 0.0
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=["close"])
    return frame


def _compute_realtime_anomaly_diagnostics(
    frame: pd.DataFrame,
    *,
    z_window: int = 20,
    return_z_threshold: float = 2.0,
    volume_z_threshold: float = 2.0,
    cusum_threshold_sigma: float = 2.5,
    pattern_lookback: int = 5,
    pattern_matches: int = 5,
) -> dict:
    if frame.empty or len(frame) < 30:
        return {
            "status": "insufficient_data",
            "sample_size": int(len(frame)),
            "recent_anomalies": [],
            "pattern_matches": [],
        }

    data = frame.copy()
    data.index = pd.to_datetime(data.index, utc=True, errors="coerce")
    data = data[~data.index.isna()].copy()
    data["return"] = data["close"].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    data["log_volume"] = np.log1p(data["volume"].clip(lower=0.0))

    effective_window = min(max(int(z_window or 20), 10), max(len(data) - 2, 10))
    rolling_return_mean = data["return"].rolling(effective_window, min_periods=max(5, effective_window // 2)).mean()
    rolling_return_std = data["return"].rolling(effective_window, min_periods=max(5, effective_window // 2)).std()
    rolling_volume_mean = data["log_volume"].rolling(effective_window, min_periods=max(5, effective_window // 2)).mean()
    rolling_volume_std = data["log_volume"].rolling(effective_window, min_periods=max(5, effective_window // 2)).std()

    data["return_zscore"] = ((data["return"] - rolling_return_mean) / rolling_return_std.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    data["volume_zscore"] = ((data["log_volume"] - rolling_volume_mean) / rolling_volume_std.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    data["rolling_volatility"] = rolling_return_std.fillna(method="bfill").fillna(0.0)

    cusum_sigma = data["rolling_volatility"].replace(0, np.nan).fillna(float(data["return"].std() or 0.01))
    drift = rolling_return_mean.fillna(0.0)
    positive_cusum = 0.0
    negative_cusum = 0.0
    pos_scores = []
    neg_scores = []
    cusum_flags = []

    for ret, mu, sigma in zip(data["return"], drift, cusum_sigma):
        sigma = float(max(sigma, 1e-6))
        positive_cusum = max(0.0, positive_cusum + float(ret - mu))
        negative_cusum = min(0.0, negative_cusum + float(ret - mu))
        threshold = float(cusum_threshold_sigma or 2.5) * sigma
        positive_flag = positive_cusum > threshold
        negative_flag = abs(negative_cusum) > threshold
        pos_scores.append(positive_cusum / sigma)
        neg_scores.append(abs(negative_cusum) / sigma)
        cusum_flags.append(positive_flag or negative_flag)
        if positive_flag:
            positive_cusum = 0.0
        if negative_flag:
            negative_cusum = 0.0

    data["cusum_positive_score"] = pos_scores
    data["cusum_negative_score"] = neg_scores
    data["cusum_flag"] = cusum_flags

    anomaly_mask = (
        data["return_zscore"].abs().ge(float(return_z_threshold or 2.0))
        | data["volume_zscore"].abs().ge(float(volume_z_threshold or 2.0))
        | data["cusum_flag"]
    )
    anomaly_points = data.loc[anomaly_mask].copy()

    def _anomaly_types(row: pd.Series) -> str:
        tags = []
        if abs(float(row["return_zscore"])) >= float(return_z_threshold or 2.0):
            tags.append("price_zscore")
        if abs(float(row["volume_zscore"])) >= float(volume_z_threshold or 2.0):
            tags.append("volume_zscore")
        if bool(row["cusum_flag"]):
            tags.append("cusum_break")
        return ", ".join(tags) or "normal"

    anomaly_points["anomaly_type"] = anomaly_points.apply(_anomaly_types, axis=1)
    anomaly_points["severity"] = (
        anomaly_points["return_zscore"].abs()
        + anomaly_points["volume_zscore"].abs()
        + anomaly_points["cusum_positive_score"].clip(lower=0)
        + anomaly_points["cusum_negative_score"].clip(lower=0)
    )

    latest = data.iloc[-1]
    current_anchor = anomaly_points.iloc[-1] if not anomaly_points.empty else latest
    anchor_position = data.index.get_loc(current_anchor.name)
    lookback = min(max(int(pattern_lookback or 5), 3), 15)
    start = max(0, anchor_position - lookback + 1)
    anchor_slice = data.iloc[start:anchor_position + 1]
    anchor_vector = np.array(
        [
            float(anchor_slice["return_zscore"].mean()),
            float(anchor_slice["volume_zscore"].mean()),
            float(anchor_slice["return"].sum()),
        ],
        dtype=float,
    )

    pattern_candidates = []
    for index in range(lookback - 1, max(anchor_position - 5, lookback - 1)):
        candidate_slice = data.iloc[index - lookback + 1:index + 1]
        if len(candidate_slice) < lookback:
            continue
        candidate_vector = np.array(
            [
                float(candidate_slice["return_zscore"].mean()),
                float(candidate_slice["volume_zscore"].mean()),
                float(candidate_slice["return"].sum()),
            ],
            dtype=float,
        )
        distance = float(np.linalg.norm(anchor_vector - candidate_vector))
        next_1 = float(data["return"].iloc[index + 1]) if index + 1 < len(data) else 0.0
        next_5 = float(data["return"].iloc[index + 1:index + 6].sum()) if index + 1 < len(data) else 0.0
        pattern_candidates.append(
            {
                "timestamp": candidate_slice.index[-1].isoformat(),
                "similarity_score": round(float(1 / (1 + distance)), 4),
                "distance": round(distance, 4),
                "return_zscore": round(float(candidate_slice["return_zscore"].iloc[-1]), 4),
                "volume_zscore": round(float(candidate_slice["volume_zscore"].iloc[-1]), 4),
                "next_1_bar_return": round(next_1, 6),
                "next_5_bar_return": round(next_5, 6),
            }
        )

    pattern_candidates.sort(key=lambda item: item["distance"])
    recent_anomalies = []
    for timestamp, row in anomaly_points.tail(12).iterrows():
        recent_anomalies.append(
            {
                "timestamp": timestamp.isoformat(),
                "close": round(float(row["close"]), 4),
                "return": round(float(row["return"]), 6),
                "return_zscore": round(float(row["return_zscore"]), 4),
                "volume_zscore": round(float(row["volume_zscore"]), 4),
                "cusum_positive_score": round(float(row["cusum_positive_score"]), 4),
                "cusum_negative_score": round(float(row["cusum_negative_score"]), 4),
                "anomaly_type": row["anomaly_type"],
                "severity": round(float(row["severity"]), 4),
            }
        )

    return {
        "status": "ok",
        "sample_size": int(len(data)),
        "window": effective_window,
        "thresholds": {
            "return_zscore": float(return_z_threshold or 2.0),
            "volume_zscore": float(volume_z_threshold or 2.0),
            "cusum_sigma": float(cusum_threshold_sigma or 2.5),
        },
        "latest_signal": {
            "timestamp": data.index[-1].isoformat(),
            "close": round(float(latest["close"]), 4),
            "return": round(float(latest["return"]), 6),
            "return_zscore": round(float(latest["return_zscore"]), 4),
            "volume_zscore": round(float(latest["volume_zscore"]), 4),
            "cusum_positive_score": round(float(latest["cusum_positive_score"]), 4),
            "cusum_negative_score": round(float(latest["cusum_negative_score"]), 4),
            "rolling_volatility": round(float(latest["rolling_volatility"]), 6),
            "is_anomaly": bool(anomaly_mask.iloc[-1]),
        },
        "summary": {
            "anomaly_count": int(anomaly_mask.sum()),
            "recent_anomaly_rate": round(float(anomaly_mask.tail(min(20, len(data))).mean()), 4),
            "max_return_zscore": round(float(data["return_zscore"].abs().max()), 4),
            "max_volume_zscore": round(float(data["volume_zscore"].abs().max()), 4),
        },
        "recent_anomalies": recent_anomalies,
        "pattern_matches": pattern_candidates[: max(1, min(int(pattern_matches or 5), 10))],
    }


@router.get("/quote/{symbol}", summary="获取实时报价")
async def get_quote(symbol: str):
    """获取股票的统一实时报价信息。"""
    data = await run_in_threadpool(
        lambda: realtime_manager.get_quote_dict(symbol, use_cache=True)
    )
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

    if len(symbol_list) > MAX_SYMBOLS_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Too many symbols: {len(symbol_list)} (max {MAX_SYMBOLS_PER_REQUEST})",
        )

    results = await run_in_threadpool(
        lambda: realtime_manager.get_quotes_dict(symbol_list, use_cache=True)
    )
    return {"success": True, "data": results}


@router.get("/summary", summary="获取实时行情运行摘要")
async def get_realtime_summary():
    from backend.app.websocket.connection_manager import manager

    summary = await run_in_threadpool(realtime_manager.get_market_summary)
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
    if len(symbol_list) > MAX_SYMBOLS_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Too many symbols: {len(symbol_list)} (max {MAX_SYMBOLS_PER_REQUEST})",
        )
    data = await run_in_threadpool(
        lambda: {
            symbol: _build_symbol_metadata(symbol)
            for symbol in symbol_list
        }
    )
    return {"success": True, "data": data}


@router.get("/replay/{symbol}", summary="个股行情回放帧")
async def get_symbol_replay(
    symbol: str,
    period: str = "5d",
    interval: str = "1d",
    limit: int = 240,
):
    normalized = realtime_manager._normalize_symbol(symbol)
    frame = await run_in_threadpool(
        lambda: _load_replay_frame(
            normalized,
            period=period,
            interval=interval,
            limit=limit,
        )
    )
    bars = []
    for index, row in frame.iterrows():
        bars.append({
            "timestamp": index.isoformat() if hasattr(index, "isoformat") else str(index),
            "open": _number_or_none(row.get("open")),
            "high": _number_or_none(row.get("high")),
            "low": _number_or_none(row.get("low")),
            "close": _number_or_none(row.get("close") or row.get("adj_close")),
            "volume": _number_or_none(row.get("volume")),
        })
    return {
        "success": True,
        "data": {
            "symbol": normalized,
            "period": period,
            "interval": interval,
            "bar_count": len(bars),
            "bars": bars,
            "replay_controls": {
                "default_speed": 1,
                "supported_speeds": [0.5, 1, 2, 5, 10],
                "can_pause": True,
                "can_step": True,
            },
        },
    }


@router.get("/anomaly-diagnostics/{symbol}", summary="统计异常波动诊断")
async def get_realtime_anomaly_diagnostics(
    symbol: str,
    period: str = "3mo",
    interval: str = "1d",
    limit: int = 240,
    z_window: int = 20,
    return_z_threshold: float = 2.0,
    volume_z_threshold: float = 2.0,
    cusum_threshold_sigma: float = 2.5,
    pattern_lookback: int = 5,
    pattern_matches: int = 5,
):
    normalized = realtime_manager._normalize_symbol(symbol)
    diagnostics = await run_in_threadpool(
        lambda: _compute_realtime_anomaly_diagnostics(
            _load_replay_frame(
                normalized,
                period=period,
                interval=interval,
                limit=limit,
            ),
            z_window=z_window,
            return_z_threshold=return_z_threshold,
            volume_z_threshold=volume_z_threshold,
            cusum_threshold_sigma=cusum_threshold_sigma,
            pattern_lookback=pattern_lookback,
            pattern_matches=pattern_matches,
        )
    )
    return {
        "success": True,
        "data": {
            "symbol": normalized,
            "period": period,
            "interval": interval,
            **diagnostics,
        },
    }


@router.get("/orderbook/{symbol}", summary="Level 2 订单簿能力探测")
async def get_orderbook(symbol: str, levels: int = 10):
    normalized = realtime_manager._normalize_symbol(symbol)
    safe_levels = max(1, min(int(levels or 10), 50))
    provider_factory = getattr(realtime_manager, "provider_factory", None)

    def _load_orderbook():
        if provider_factory is None:
            quote = realtime_manager.get_quote_dict(normalized, use_cache=True) or {}
            return {
                "symbol": normalized,
                "source": quote.get("source") or "synthetic_quote_proxy",
                "mode": "synthetic_quote_proxy",
                "level2_supported": False,
                "bids": [],
                "asks": [],
                "metrics": {},
                "diagnostics": {
                    "message": "Provider factory unavailable; depth diagnostics skipped.",
                    "is_synthetic": True,
                    "provider_candidates": [],
                },
            }
        return provider_factory.get_market_depth_capabilities(normalized, levels=safe_levels)

    result = await run_in_threadpool(_load_orderbook)
    return {
        "success": True,
        "data": {
            "symbol": normalized,
            "requested_levels": safe_levels,
            "level2_supported": result.get("level2_supported", False),
            "is_synthetic": result.get("mode") != "provider_level2",
            "source": result.get("source", "unknown"),
            "mode": result.get("mode"),
            "bids": (result.get("bids") or [])[:safe_levels],
            "asks": (result.get("asks") or [])[:safe_levels],
            "metrics": result.get("metrics") or {},
            "diagnostics": result.get("diagnostics") or {},
        },
    }


def _resolve_realtime_profile(request: Request) -> str:
    header_profile = request.headers.get("X-Realtime-Profile")
    if header_profile:
        return header_profile

    query_profile = request.query_params.get("profile_id")
    if query_profile:
        return query_profile

    return "default"


@router.get("/preferences", summary="获取实时行情偏好配置")
async def get_preferences(request: Request):
    profile_id = _resolve_realtime_profile(request)
    return {"success": True, "data": realtime_preferences_store.get_preferences(profile_id=profile_id)}


@router.put("/preferences", summary="更新实时行情偏好配置")
async def update_preferences(payload: RealtimePreferencesRequest, request: Request):
    profile_id = _resolve_realtime_profile(request)
    data = realtime_preferences_store.update_preferences(payload.model_dump(), profile_id=profile_id)
    warnings = data.pop("_warnings", None)
    result = {"success": True, "data": data}
    if warnings:
        result["warnings"] = warnings
    return result


@router.get("/alerts", summary="获取实时提醒规则")
async def get_alerts(request: Request):
    profile_id = _resolve_realtime_profile(request)
    return {"success": True, "data": realtime_alerts_store.get_alerts(profile_id=profile_id)}


@router.put("/alerts", summary="更新实时提醒规则")
async def update_alerts(payload: RealtimeAlertsRequest, request: Request):
    profile_id = _resolve_realtime_profile(request)
    data = realtime_alerts_store.update_alerts(payload.model_dump(), profile_id=profile_id)
    warnings = data.pop("_warnings", None)
    result = {"success": True, "data": data}
    if warnings:
        result["warnings"] = warnings
    return result


@router.post("/alerts/hits", summary="记录实时提醒命中")
async def record_alert_hit(payload: RealtimeAlertHitRequest, request: Request):
    profile_id = _resolve_realtime_profile(request)
    try:
        stored = realtime_alerts_store.record_alert_hit(payload.entry, profile_id=profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "success": True,
        "data": {
            "entry": stored.get("entry"),
            "alert_hit_history": stored.get("alert_hit_history"),
            "bus_event": None,
            "cascade_results": [],
            "orchestration_summary": {},
        },
    }


@router.get("/journal", summary="获取实时行情复盘与时间线")
async def get_journal(request: Request):
    profile_id = _resolve_realtime_profile(request)
    return {"success": True, "data": realtime_journal_store.get_journal(profile_id=profile_id)}


@router.put("/journal", summary="更新实时行情复盘与时间线")
async def update_journal(payload: RealtimeJournalRequest, request: Request):
    profile_id = _resolve_realtime_profile(request)
    data = realtime_journal_store.update_journal(payload.model_dump(), profile_id=profile_id)
    warnings = data.pop("_warnings", None)
    result = {"success": True, "data": data}
    if warnings:
        result["warnings"] = warnings
    return result


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
