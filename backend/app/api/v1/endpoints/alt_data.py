"""
另类数据 API 端点。
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.data.alternative import get_alt_data_manager, get_alt_data_scheduler

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_manager():
    return get_alt_data_manager()


def _get_scheduler():
    return get_alt_data_scheduler()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if number != number:
            return default
        return number
    except (TypeError, ValueError):
        return default


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _record_payload(record: Any) -> Dict[str, Any]:
    if hasattr(record, "to_dict"):
        return record.to_dict()
    if isinstance(record, dict):
        return record
    return {}


def _record_outcome(payload: Dict[str, Any]) -> Optional[bool]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    raw_value = payload.get("raw_value") if isinstance(payload.get("raw_value"), dict) else {}
    candidates = [
        payload.get("outcome"),
        payload.get("hit"),
        metadata.get("outcome"),
        metadata.get("hit"),
        raw_value.get("outcome"),
        raw_value.get("hit"),
    ]
    for candidate in candidates:
        if isinstance(candidate, bool):
            return candidate
        text = str(candidate).strip().lower()
        if text in {"hit", "success", "true", "true_positive", "win", "correct"}:
            return True
        if text in {"miss", "failed", "false", "false_positive", "loss", "wrong"}:
            return False

    realized_return = (
        payload.get("realized_return")
        if payload.get("realized_return") is not None
        else metadata.get("realized_return", raw_value.get("realized_return"))
    )
    if realized_return is not None:
        signal = _safe_float(payload.get("normalized_score"), 0.0)
        return signal * _safe_float(realized_return, 0.0) > 0
    return None


def _proxy_outcome(payload: Dict[str, Any]) -> bool:
    strength = abs(_safe_float(payload.get("normalized_score"), 0.0))
    confidence = _safe_float(payload.get("confidence"), 0.0)
    return strength * confidence >= 0.18


def _summarize_signal_group(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    items = list(rows)
    if not items:
        return {
            "count": 0,
            "avg_strength": 0.0,
            "avg_abs_strength": 0.0,
            "avg_confidence": 0.0,
            "hit_rate": None,
            "hit_rate_type": "none",
        }

    realized = [item["outcome"] for item in items if item.get("outcome") is not None]
    hit_values = realized if realized else [item["proxy_outcome"] for item in items]
    hit_rate_type = "realized" if realized else "proxy"
    avg_strength = sum(item["strength"] for item in items) / len(items)
    avg_abs_strength = sum(abs(item["strength"]) for item in items) / len(items)
    avg_confidence = sum(item["confidence"] for item in items) / len(items)

    return {
        "count": len(items),
        "avg_strength": round(avg_strength, 4),
        "avg_abs_strength": round(avg_abs_strength, 4),
        "avg_confidence": round(avg_confidence, 4),
        "hit_rate": round(sum(1 for hit in hit_values if hit) / len(hit_values), 4) if hit_values else None,
        "hit_rate_type": hit_rate_type,
    }


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
        category_value = category.strip() if isinstance(category, str) and category.strip() else None
        records = manager.get_records(category=category_value, timeframe=timeframe, limit=limit)
        history_analysis = manager.analyze_history(records)
        snapshot = manager.get_dashboard_snapshot(refresh=False)
        return {
            "records": [record.to_dict() for record in records],
            "count": len(records),
            "category": category_value,
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


@router.get("/diagnostics/signals", summary="另类数据信号命中率与衰减诊断")
async def get_alt_signal_diagnostics(
    category: Optional[str] = Query(default=None),
    timeframe: str = Query(default="90d"),
    limit: int = Query(default=300, ge=1, le=1000),
    half_life_days: float = Query(default=14.0, gt=0.1, le=365),
):
    try:
        manager = _get_manager()
        category_value = category.strip() if isinstance(category, str) and category.strip() else None
        records = manager.get_records(category=category_value, timeframe=timeframe, limit=limit)
        now = datetime.now()
        normalized_rows: List[Dict[str, Any]] = []

        for record in records:
            payload = _record_payload(record)
            timestamp = _parse_timestamp(payload.get("timestamp")) or now
            age_days = max((now - timestamp).total_seconds() / 86400.0, 0.0)
            strength = _safe_float(payload.get("normalized_score"), 0.0)
            confidence = _safe_float(payload.get("confidence"), 0.0)
            outcome = _record_outcome(payload)
            decay_weight = math.exp(-math.log(2) * age_days / half_life_days)
            normalized_rows.append({
                "record_id": payload.get("record_id") or f"record_{len(normalized_rows)}",
                "timestamp": timestamp.isoformat(),
                "source": payload.get("source") or payload.get("provider") or "unknown",
                "category": payload.get("category") or "unknown",
                "strength": strength,
                "confidence": confidence,
                "age_days": round(age_days, 2),
                "decay_weight": round(decay_weight, 4),
                "decayed_strength": round(strength * confidence * decay_weight, 6),
                "outcome": outcome,
                "proxy_outcome": _proxy_outcome(payload),
                "tags": payload.get("tags") or [],
            })

        by_provider: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        by_category: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in normalized_rows:
            by_provider[row["source"]].append(row)
            by_category[row["category"]].append(row)

        provider_rows = [
            {
                "provider": provider,
                **_summarize_signal_group(rows),
            }
            for provider, rows in sorted(by_provider.items())
        ]
        category_rows = [
            {
                "category": category_name,
                **_summarize_signal_group(rows),
            }
            for category_name, rows in sorted(by_category.items())
        ]

        decay_curve = []
        max_age = max([row["age_days"] for row in normalized_rows], default=0.0)
        for day in range(0, int(max(half_life_days * 3, max_age)) + 1, max(1, int(half_life_days // 3) or 1)):
            weight = math.exp(-math.log(2) * day / half_life_days)
            weighted_strengths = [
                abs(row["strength"]) * row["confidence"] * weight
                for row in normalized_rows
            ]
            decay_curve.append({
                "age_days": day,
                "decay_weight": round(weight, 4),
                "avg_decayed_signal": round(sum(weighted_strengths) / len(weighted_strengths), 6) if weighted_strengths else 0.0,
            })

        realized_count = sum(1 for row in normalized_rows if row.get("outcome") is not None)
        snapshot = manager.get_dashboard_snapshot(refresh=False)
        return {
            "status": "ok" if normalized_rows else "empty",
            "category": category_value,
            "timeframe": timeframe,
            "limit": limit,
            "half_life_days": half_life_days,
            "record_count": len(normalized_rows),
            "realized_outcome_count": realized_count,
            "hit_rate_note": (
                "存在已实现 outcome/realized_return 字段时使用真实命中率；否则使用 strength*confidence 阈值作为 proxy hit rate。"
            ),
            "overall": _summarize_signal_group(normalized_rows),
            "providers": provider_rows,
            "categories": category_rows,
            "decay_curve": decay_curve,
            "recent_records": normalized_rows[:20],
            "snapshot_timestamp": snapshot.get("snapshot_timestamp"),
        }
    except Exception as exc:
        logger.error("Failed to load alt-data signal diagnostics: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
