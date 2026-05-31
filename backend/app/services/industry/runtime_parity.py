"""Parity-score snapshot cache + degraded leader-detail fallback.

Extracted verbatim from ``runtime.py``. This is a self-contained cluster: a
TTL'd cache of list-board score snapshots plus a builder that turns a cached
snapshot into a *degraded* ``LeaderDetailResponse`` when the live detail path
fails. It depends only one-way on leaf helpers (``_model_to_dict``,
``_build_parity_price_data``, ``normalize_symbol``) and schemas, and never
calls back into the runtime singletons or other clusters — so it has no import
cycle with ``runtime.py``.

``_parity_cache`` is mutated in place (``cache[k] = v``) and never rebound, so
``runtime.py`` re-imports the *same* dict object; the ``_compat`` state-sync
(which targets ``runtime._parity_cache``) keeps operating on that shared
instance.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, Optional

from backend.app.api.v1.endpoints._industry_helpers import _model_to_dict
from backend.app.schemas.industry import LeaderDetailResponse
from backend.app.services.industry.runtime_helpers import _build_parity_price_data
from src.analytics.industry_stock_details import normalize_symbol

_parity_cache: dict = {}  # {key: {"data": ..., "ts": float}}

_PARITY_CACHE_TTL = 1800  # 30分钟（评分在交易日内变化缓慢）


def _set_parity_cache(symbol: str, score_type: str, data):
    """保存列表评分快照到独立 parity 缓存"""
    if data is None:
        return
    key = f"{symbol}:{score_type}"
    _parity_cache[key] = {"data": data, "ts": time.time()}


def _get_parity_cache(symbol: str, score_type: str):
    """获取有效的 parity 缓存（未过期）"""
    key = f"{symbol}:{score_type}"
    entry = _parity_cache.get(key)
    if entry and (time.time() - entry["ts"]) < _PARITY_CACHE_TTL:
        return entry["data"]
    return None


def _get_stale_parity_cache(symbol: str, score_type: str):
    """获取过期的 parity 缓存作为兜底（不检查 TTL）"""
    key = f"{symbol}:{score_type}"
    entry = _parity_cache.get(key)
    return entry["data"] if entry else None


def _is_fresh_parity_entry(entry: dict[str, Any]) -> bool:
    return (time.time() - entry["ts"]) < _PARITY_CACHE_TTL


def _get_matching_parity_cache(
    symbol_or_name: str,
    score_type: str,
    allow_stale: bool = True,
) -> tuple[Any, Optional[str], bool]:
    """按代码或股票名匹配 parity 快照，必要时允许使用过期条目。"""
    raw = str(symbol_or_name or "").strip()
    if not raw:
        return None, None, False

    normalized = normalize_symbol(raw)
    raw_casefold = raw.casefold()
    matched_entries: list[tuple[dict[str, Any], Optional[str]]] = []
    seen_entry_ids: set[int] = set()

    if re.fullmatch(r"\d{6}", normalized):
        exact_entry = _parity_cache.get(f"{normalized}:{score_type}")
        if exact_entry is not None:
            matched_entries.append((exact_entry, normalized))
            seen_entry_ids.add(id(exact_entry))

    for key, entry in _parity_cache.items():
        if not key.endswith(f":{score_type}") or id(entry) in seen_entry_ids:
            continue

        payload = _model_to_dict(entry.get("data"))
        cached_symbol = normalize_symbol(payload.get("symbol") or "")
        cached_name = str(payload.get("name") or "").strip()
        cached_name_casefold = cached_name.casefold()

        if re.fullmatch(r"\d{6}", normalized) and cached_symbol == normalized:
            matched_entries.append((entry, cached_symbol))
            seen_entry_ids.add(id(entry))
            continue

        if cached_name and cached_name_casefold == raw_casefold:
            matched_entries.append((entry, cached_symbol or normalized))
            seen_entry_ids.add(id(entry))

    ordered_entries = [
        (entry, matched_symbol)
        for entry, matched_symbol in matched_entries
        if _is_fresh_parity_entry(entry)
    ]
    if allow_stale:
        ordered_entries.extend(
            (entry, matched_symbol)
            for entry, matched_symbol in matched_entries
            if not _is_fresh_parity_entry(entry)
        )

    if not ordered_entries:
        return None, None, False

    selected_entry, matched_symbol = ordered_entries[0]
    payload = _model_to_dict(selected_entry.get("data"))
    return (
        selected_entry.get("data"),
        matched_symbol or normalize_symbol(payload.get("symbol") or normalized),
        not _is_fresh_parity_entry(selected_entry),
    )


def _build_leader_detail_fallback(
    parity_snapshot: Any,
    score_type: str,
    note: str,
    source: str,
) -> LeaderDetailResponse:
    payload = _model_to_dict(parity_snapshot)
    symbol = normalize_symbol(payload.get("symbol") or "")

    return LeaderDetailResponse(
        symbol=symbol or payload.get("symbol") or "",
        name=str(payload.get("name") or ""),
        total_score=float(payload.get("total_score") or 0),
        score_type=score_type,
        dimension_scores=payload.get("dimension_scores") or {},
        raw_data={
            "symbol": symbol or payload.get("symbol") or "",
            "name": str(payload.get("name") or ""),
            "market_cap": payload.get("market_cap"),
            "pe_ttm": payload.get("pe_ratio"),
            "change_pct": payload.get("change_pct"),
            "source": source,
            "updated_at": datetime.now().isoformat(),
        },
        technical_analysis={},
        price_data=_build_parity_price_data(payload.get("mini_trend") or []),
        degraded=True,
        note=note,
    )
