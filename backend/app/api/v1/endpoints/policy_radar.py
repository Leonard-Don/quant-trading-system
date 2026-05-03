"""Policy radar — read-only HTTP surface for the alt-data PolicySignalProvider.

The crawling/NLP pipeline runs in `src/data/alternative/policy_radar/`. This
module only exposes already-collected signals so the frontend can render them.
Endpoint failures degrade to empty payloads (HTTP 200) rather than 500s,
consistent with the project's local-first philosophy: a fresh checkout that
hasn't bootstrapped any policy snapshots should still load the UI cleanly.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter()


def _empty_signal_payload() -> dict[str, Any]:
    return {
        "industry_signals": {},
        "policy_count": 0,
        "source_health": {},
        "last_refresh": None,
        "available": False,
    }


def _empty_records_payload(timeframe: str, industry: Optional[str], limit: int) -> dict[str, Any]:
    return {
        "records": [],
        "timeframe": timeframe,
        "industry": industry,
        "limit": limit,
        "available": False,
    }


def _get_alt_manager():
    """Resolve the singleton lazily so tests can monkeypatch it cleanly."""
    from src.data.alternative.runtime import get_alt_data_manager

    return get_alt_data_manager()


def _extract_policy_signal(alt_signals_payload: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the policy-category entry out of the multi-provider signals envelope."""
    signals = alt_signals_payload.get("signals") or []
    for signal in signals:
        if isinstance(signal, dict) and signal.get("category") == "policy":
            return signal
    return None


@router.get(
    "/signal",
    summary="获取最新政策雷达综合信号",
    description=(
        "返回 PolicySignalProvider 的最新汇总信号：industry_signals / source_health / "
        "policy_count / last_refresh。底层数据来自 AltDataManager 的 60 分钟缓存，"
        "不会触发现场抓取或 NLP 推理。"
    ),
)
def get_policy_signal() -> dict[str, Any]:
    try:
        manager = _get_alt_manager()
        payload = manager.get_alt_signals(category="policy")
    except Exception as exc:  # noqa: BLE001
        logger.warning("policy_radar /signal degrade to empty: %s", exc)
        return {"success": True, "data": _empty_signal_payload()}

    policy_signal = _extract_policy_signal(payload) or {}
    if not policy_signal:
        data = _empty_signal_payload()
        data["last_refresh"] = payload.get("last_refresh")
        return {"success": True, "data": data}

    return {
        "success": True,
        "data": {
            "industry_signals": policy_signal.get("industry_signals") or {},
            "policy_count": int(policy_signal.get("policy_count") or 0),
            "source_health": policy_signal.get("source_health") or {},
            "last_refresh": payload.get("last_refresh"),
            "available": True,
        },
    }


@router.get(
    "/records",
    summary="获取政策雷达历史记录",
    description=(
        "按时间倒序返回最近的政策记录，可选按行业 tag 过滤。`industry` 与记录 "
        "tags 完全匹配（区分大小写按字面值）。`timeframe` 形如 `7d` / `30d`。"
    ),
)
def get_policy_records(
    industry: Optional[str] = Query(default=None, description="可选：仅返回 tags 包含该值的记录"),
    timeframe: str = Query(default="7d", description="时间窗（如 7d / 30d）"),
    limit: int = Query(default=50, ge=1, le=200, description="最多返回的记录条数"),
) -> dict[str, Any]:
    try:
        manager = _get_alt_manager()
        records = manager.get_records(category="policy", timeframe=timeframe, limit=limit)
    except Exception as exc:  # noqa: BLE001
        logger.warning("policy_radar /records degrade to empty: %s", exc)
        return {"success": True, "data": _empty_records_payload(timeframe, industry, limit)}

    if industry:
        records = [record for record in records if industry in (record.tags or [])]

    serialized = [record.to_dict() for record in records[:limit]]
    serialized.sort(key=lambda item: item.get("timestamp") or "", reverse=True)

    return {
        "success": True,
        "data": {
            "records": serialized,
            "timeframe": timeframe,
            "industry": industry,
            "limit": limit,
            "available": True,
        },
    }
