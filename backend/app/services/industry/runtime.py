"""Runtime helpers for the industry API surface.

Orchestration layer for the industry feature: caching, in-flight dedup,
prewarm scheduling, payload serialization, disk persistence, and provider
fallback. Wraps the pure analytics in ``src/analytics/industry_analyzer.py``
and is exposed through ``backend/app/api/v1/endpoints/industry.py`` (which
also maintains a test-patch shim mirroring helpers from this module).
Layer charter: ``docs/architecture/industry-layering.md``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Literal, Optional

from fastapi import HTTPException, Request

from backend.app.api.v1.endpoints._industry_helpers import (
    _format_storage_size,
    _model_to_dict,
    _normalize_sparkline_points,
)
from backend.app.schemas.industry import (
    HeatmapDataItem,
    HeatmapResponse,
    IndustryBootstrapResponse,
    IndustryRankResponse,
    LeaderBoardsResponse,
    LeaderDetailResponse,
    LeaderStockResponse,
    StockResponse,
)
from src.analytics.industry_stock_details import (
    build_enriched_industry_stocks,
    coerce_optional_float,
    extract_stock_detail_fields,
    has_meaningful_numeric,
    normalize_symbol,
)
from src.utils.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

_industry_analyzer = None

_leader_scorer = None

_akshare_provider = None

SIX_DIGIT_SYMBOL_PATTERN = re.compile(r"\d{6}")

_endpoint_cache: dict = {}  # {key: {"data": ..., "ts": float}}

_ENDPOINT_CACHE_TTL = 180  # 3分钟

_stocks_full_build_executor = ThreadPoolExecutor(max_workers=2)

_stocks_full_build_lock = threading.Lock()

_stocks_full_build_inflight: set[str] = set()

_stocks_full_build_status: dict[str, dict] = {}

_leader_overview_build_executor = ThreadPoolExecutor(max_workers=2)

_leader_overview_build_lock = threading.Lock()

_leader_overview_build_inflight: dict[str, Future] = {}

_leader_snapshot_prewarm_executor = ThreadPoolExecutor(max_workers=2)

_leader_snapshot_prewarm_lock = threading.Lock()

_leader_snapshot_prewarm_inflight: set[str] = set()

_leading_stock_symbol_lookup_cache: dict[str, str] = {}

_leading_stock_symbol_lookup_cache_time: float = 0.0

_LEADING_STOCK_SYMBOL_LOOKUP_TTL = 600

_leading_stock_symbol_lookup_lock = threading.Lock()

_heatmap_history_lock = threading.Lock()

_heatmap_history: list[dict] = []

_heatmap_history_loaded = False

_HEATMAP_HISTORY_MAX_ITEMS = 48

_HEATMAP_HISTORY_MAX_FILE_BYTES = 2 * 1024 * 1024

_HEATMAP_HISTORY_FILE = PROJECT_ROOT / "data" / "industry" / "heatmap_history.json"

_heatmap_refresh_executor = ThreadPoolExecutor(max_workers=1)

_heatmap_refresh_lock = threading.Lock()

_heatmap_refresh_inflight: set[int] = set()

_parity_cache: dict = {}  # {key: {"data": ..., "ts": float}}

_PARITY_CACHE_TTL = 1800  # 30分钟（评分在交易日内变化缓慢）

INDUSTRY_ETF_MAP: dict[str, list[dict[str, str]]] = {
    "半导体": [{"symbol": "SOXX", "market": "US"}, {"symbol": "512760.SS", "market": "CN"}],
    "芯片": [{"symbol": "SOXX", "market": "US"}, {"symbol": "159995.SZ", "market": "CN"}],
    "人工智能": [{"symbol": "AIQ", "market": "US"}, {"symbol": "CHAT", "market": "US"}],
    "软件": [{"symbol": "IGV", "market": "US"}, {"symbol": "515230.SS", "market": "CN"}],
    "新能源": [{"symbol": "ICLN", "market": "US"}, {"symbol": "516160.SS", "market": "CN"}],
    "光伏": [{"symbol": "TAN", "market": "US"}, {"symbol": "515790.SS", "market": "CN"}],
    "电池": [{"symbol": "LIT", "market": "US"}, {"symbol": "159755.SZ", "market": "CN"}],
    "医药": [{"symbol": "XLV", "market": "US"}, {"symbol": "512010.SS", "market": "CN"}],
    "医疗": [{"symbol": "XLV", "market": "US"}, {"symbol": "159883.SZ", "market": "CN"}],
    "消费": [{"symbol": "XLY", "market": "US"}, {"symbol": "159928.SZ", "market": "CN"}],
    "白酒": [{"symbol": "512690.SS", "market": "CN"}],
    "金融": [{"symbol": "XLF", "market": "US"}, {"symbol": "510230.SS", "market": "CN"}],
    "银行": [{"symbol": "KBE", "market": "US"}, {"symbol": "512800.SS", "market": "CN"}],
    "证券": [{"symbol": "KCE", "market": "US"}, {"symbol": "512880.SS", "market": "CN"}],
    "地产": [{"symbol": "VNQ", "market": "US"}, {"symbol": "512200.SS", "market": "CN"}],
    "军工": [{"symbol": "ITA", "market": "US"}, {"symbol": "512660.SS", "market": "CN"}],
    "能源": [{"symbol": "XLE", "market": "US"}, {"symbol": "159930.SZ", "market": "CN"}],
    "煤炭": [{"symbol": "KOL", "market": "US"}, {"symbol": "515220.SS", "market": "CN"}],
    "有色": [{"symbol": "XME", "market": "US"}, {"symbol": "512400.SS", "market": "CN"}],
    "汽车": [{"symbol": "CARZ", "market": "US"}, {"symbol": "516110.SS", "market": "CN"}],
}


def _load_symbol_mini_trend(symbol: str) -> list[float]:
    scorer = get_leader_scorer()
    provider = getattr(scorer, "provider", None)
    if provider is None or not hasattr(provider, "get_historical_data"):
        return []

    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=45)
        hist_data = provider.get_historical_data(symbol, start_date, end_date)
        if hist_data is None or hist_data.empty or "close" not in hist_data.columns:
            return []
        return _normalize_sparkline_points(hist_data["close"].tail(20).tolist(), max_points=20)
    except Exception as exc:
        logger.warning("Failed to load mini trend for leader %s: %s", symbol, exc)
        return []


def _attach_leader_mini_trends(leaders: list[LeaderStockResponse]) -> list[LeaderStockResponse]:
    if not leaders:
        return leaders

    symbols = [leader.symbol for leader in leaders if re.fullmatch(r"\d{6}", leader.symbol or "")]
    if not symbols:
        return leaders

    with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as executor:
        trend_values = list(executor.map(_load_symbol_mini_trend, symbols))

    trend_map = dict(zip(symbols, trend_values))
    for leader in leaders:
        leader.mini_trend = trend_map.get(leader.symbol, [])
    return leaders


def _get_endpoint_cache(key: str):
    """Get cached endpoint result if not expired"""
    entry = _endpoint_cache.get(key)
    if entry and (time.time() - entry["ts"]) < _ENDPOINT_CACHE_TTL:
        return entry["data"]
    return None


def _set_endpoint_cache(key: str, data):
    """Set endpoint result cache (skip empty results)"""
    # 不缓存空结果，防止数据源临时故障时导致长时间返回空
    if data is None:
        return
    if isinstance(data, (list, tuple)) and len(data) == 0:
        return
    if isinstance(data, dict):
        # heatmap 返回的 industries 为空时不缓存
        industries = data.get("industries")
        if isinstance(industries, list) and len(industries) == 0:
            return
    _endpoint_cache[key] = {"data": data, "ts": time.time()}


def _get_stale_endpoint_cache(key: str):
    """获取过期缓存作为兜底。"""
    entry = _endpoint_cache.get(key)
    return entry["data"] if entry else None


def _serialize_heatmap_response(
    heatmap_data: dict[str, Any],
    leading_stock_symbol_lookup: Optional[dict[str, str]] = None,
) -> HeatmapResponse:
    leading_stock_symbol_lookup = (
        leading_stock_symbol_lookup or _build_leading_stock_symbol_lookup()
    )

    industries = []
    for ind in heatmap_data.get("industries", []):
        leading_stock_name = (
            str(ind["leadingStock"])
            if ind.get("leadingStock") and ind["leadingStock"] != 0
            else None
        )
        leading_stock_symbol = None
        if leading_stock_name:
            lookup_symbol = leading_stock_symbol_lookup.get(leading_stock_name)
            if re.fullmatch(r"\d{6}", lookup_symbol or ""):
                leading_stock_symbol = lookup_symbol
            else:
                resolved_symbol = _resolve_symbol_with_provider(leading_stock_name)
                if re.fullmatch(r"\d{6}", resolved_symbol or ""):
                    leading_stock_symbol = resolved_symbol

        industries.append(
            HeatmapDataItem(
                name=ind.get("name", ""),
                value=ind.get("value", 0),
                total_score=ind.get("total_score", 0),
                size=ind.get("size", 0),
                stockCount=ind.get("stockCount", 0),
                moneyFlow=ind.get("moneyFlow", 0),
                turnoverRate=ind.get("turnoverRate", 0),
                industryVolatility=ind.get("industryVolatility", 0),
                industryVolatilitySource=ind.get("industryVolatilitySource", "unavailable"),
                netInflowRatio=ind.get("netInflowRatio", 0),
                leadingStock=leading_stock_name,
                leadingStockSymbol=leading_stock_symbol,
                sizeSource=ind.get("sizeSource", "estimated"),
                marketCapSource=ind.get("marketCapSource", "unknown"),
                marketCapSnapshotAgeHours=ind.get("marketCapSnapshotAgeHours"),
                marketCapSnapshotIsStale=ind.get("marketCapSnapshotIsStale", False),
                valuationSource=ind.get("valuationSource", "unavailable"),
                valuationQuality=ind.get("valuationQuality", "unavailable"),
                dataSources=ind.get("dataSources", []),
                industryIndex=ind.get("industryIndex", 0),
                totalInflow=ind.get("totalInflow", 0),
                totalOutflow=ind.get("totalOutflow", 0),
                leadingStockChange=ind.get("leadingStockChange", 0),
                leadingStockPrice=ind.get("leadingStockPrice", 0),
                pe_ttm=ind.get("pe_ttm"),
                pb=ind.get("pb"),
                dividend_yield=ind.get("dividend_yield"),
            )
        )

    return HeatmapResponse(
        industries=industries,
        max_value=heatmap_data.get("max_value", 0),
        min_value=heatmap_data.get("min_value", 0),
        update_time=heatmap_data.get("update_time", ""),
    )


def _build_hot_industry_rank_responses(
    analyzer, hot_industries: list[dict[str, Any]]
) -> list[IndustryRankResponse]:
    return [
        IndustryRankResponse(
            rank=ind.get("rank", 0),
            industry_name=ind.get("industry_name", ""),
            score=ind.get("score", 0),
            momentum=ind.get("momentum", 0),
            change_pct=ind.get("change_pct", 0),
            money_flow=ind.get("money_flow", 0),
            flow_strength=ind.get("flow_strength", 0),
            industryVolatility=ind.get("industry_volatility", 0),
            industryVolatilitySource=ind.get("industry_volatility_source", "unavailable"),
            stock_count=ind.get("stock_count", 0),
            total_market_cap=ind.get("total_market_cap", 0),
            marketCapSource=ind.get("market_cap_source", "unknown"),
            mini_trend=ind.get("mini_trend", []),
            score_breakdown=analyzer.build_rank_score_breakdown(ind),
        )
        for ind in hot_industries
    ]


def _get_stock_cache_keys(industry_name: str, top_n: int) -> tuple[str, str]:
    """生成行业成分股快/全量缓存键。"""
    return (
        f"stocks:quick:{industry_name}:{top_n}",
        f"stocks:full:{industry_name}:{top_n}",
    )


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


def _build_parity_price_data(mini_trend: list[Any]) -> list[dict[str, Any]]:
    normalized_points = _normalize_sparkline_points(mini_trend or [], max_points=20)
    point_count = len(normalized_points)
    if point_count < 2:
        return []

    return [
        {
            "date": f"T-{point_count - index - 1}",
            "close": point,
            "volume": 0,
        }
        for index, point in enumerate(normalized_points)
    ]


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


def _leader_detail_error_status(error_message: str) -> int:
    normalized = str(error_message or "").strip().lower()
    if not normalized:
        return 502

    not_found_tokens = (
        "stock not found",
        "quote not found",
        "no data for",
        "missing symbol",
        "not found",
        "data provider not set",
    )
    if any(token in normalized for token in not_found_tokens):
        return 404

    return 502


def _extract_leading_stock_symbol_lookup(industries) -> dict[str, str]:
    if (
        industries is None
        or industries.empty
        or not {"leading_stock_name", "leading_stock_code"}.issubset(industries.columns)
    ):
        return {}

    filtered = industries.loc[:, ["leading_stock_name", "leading_stock_code"]].copy()
    filtered["leading_stock_name"] = (
        filtered["leading_stock_name"].fillna("").astype(str).str.strip()
    )
    filtered["leading_stock_code"] = filtered["leading_stock_code"].map(
        lambda value: normalize_symbol(value or "")
    )
    filtered = filtered[
        filtered["leading_stock_name"].ne("")
        & filtered["leading_stock_code"].map(
            lambda value: bool(SIX_DIGIT_SYMBOL_PATTERN.fullmatch(value or ""))
        )
    ]
    if filtered.empty:
        return {}
    filtered = filtered.drop_duplicates(subset=["leading_stock_name"], keep="first")
    return dict(zip(filtered["leading_stock_name"], filtered["leading_stock_code"]))


def _collect_hot_leader_candidates(
    heatmap_df,
    top_industry_names: set[str],
    top_n: int,
) -> list[dict[str, Any]]:
    if heatmap_df is None or heatmap_df.empty or "leading_stock" not in heatmap_df.columns:
        return []

    sort_col = "main_net_inflow" if "main_net_inflow" in heatmap_df.columns else "change_pct"
    hot_candidate_limit = max(1, int(top_n * 1.2))
    sorted_df = heatmap_df.sort_values(sort_col, ascending=False)
    filtered_df = sorted_df[
        sorted_df["leading_stock"].map(lambda value: isinstance(value, str) and bool(value))
    ]
    if top_industry_names:
        filtered_df = filtered_df[filtered_df["industry_name"].isin(top_industry_names)]
    if filtered_df.empty:
        return []
    return (
        filtered_df.drop_duplicates(subset=["leading_stock"], keep="first")
        .head(hot_candidate_limit)
        .to_dict("records")
    )


def _build_leading_stock_symbol_lookup(force_refresh: bool = False) -> dict[str, str]:
    """复用 Sina 行业维表里的领涨股代码，减少热力图点击对名称解析的依赖。"""
    global _leading_stock_symbol_lookup_cache_time

    now = time.time()
    with _leading_stock_symbol_lookup_lock:
        if (
            not force_refresh
            and _leading_stock_symbol_lookup_cache
            and now - _leading_stock_symbol_lookup_cache_time < _LEADING_STOCK_SYMBOL_LOOKUP_TTL
        ):
            return dict(_leading_stock_symbol_lookup_cache)

    try:
        from src.data.providers.sina_provider import SinaFinanceProvider

        persistent_industries = SinaFinanceProvider._load_persistent_industry_list()
    except Exception as exc:
        logger.warning(
            "Failed to load persistent Sina industry list for leading stock lookup: %s", exc
        )
        persistent_industries = None

    persistent_lookup = _extract_leading_stock_symbol_lookup(persistent_industries)
    if persistent_lookup:
        with _leading_stock_symbol_lookup_lock:
            _leading_stock_symbol_lookup_cache.clear()
            _leading_stock_symbol_lookup_cache.update(persistent_lookup)
            _leading_stock_symbol_lookup_cache_time = now
        return dict(persistent_lookup)

    provider = _get_or_create_provider()
    sina_provider = getattr(provider, "sina", None)
    if sina_provider is None or not hasattr(sina_provider, "get_industry_list"):
        return {}

    try:
        industries = sina_provider.get_industry_list()
    except Exception as exc:
        logger.warning("Failed to load Sina industry list for leading stock lookup: %s", exc)
        return {}

    symbol_lookup = _extract_leading_stock_symbol_lookup(industries)
    if symbol_lookup:
        with _leading_stock_symbol_lookup_lock:
            _leading_stock_symbol_lookup_cache.clear()
            _leading_stock_symbol_lookup_cache.update(symbol_lookup)
            _leading_stock_symbol_lookup_cache_time = now
    return symbol_lookup


def _map_industry_etfs(industry_name: str) -> list[dict[str, str]]:
    normalized = str(industry_name or "")
    matches: list[dict[str, str]] = []
    for keyword, etfs in INDUSTRY_ETF_MAP.items():
        if keyword in normalized:
            matches.extend(etfs)
    if not matches:
        matches = [{"symbol": "SPY", "market": "US"}, {"symbol": "510300.SS", "market": "CN"}]
    seen = set()
    result = []
    for item in matches:
        key = item["symbol"]
        if key in seen:
            continue
        seen.add(key)
        result.append({**item, "reason": f"{industry_name} ETF proxy"})
    return result


def _trim_heatmap_history_payload(payload: list[dict]) -> list[dict]:
    trimmed = list(payload[:_HEATMAP_HISTORY_MAX_ITEMS])
    while trimmed:
        encoded = json.dumps(trimmed, ensure_ascii=False, indent=2).encode("utf-8")
        if len(encoded) <= _HEATMAP_HISTORY_MAX_FILE_BYTES:
            break
        trimmed = trimmed[:-1]
    return trimmed


def _resolve_industry_profile(request: Request | None) -> str:
    if request is None:
        return "default"
    return request.headers.get("X-Industry-Profile", "default")


def _get_stock_status_key(industry_name: str, top_n: int) -> str:
    return f"{industry_name}:{top_n}"


def _set_stock_build_status(
    industry_name: str, top_n: int, status: str, rows: int = 0, message: Optional[str] = None
) -> None:
    _stocks_full_build_status[_get_stock_status_key(industry_name, top_n)] = {
        "industry_name": industry_name,
        "top_n": top_n,
        "status": status,
        "rows": int(rows or 0),
        "message": message,
        "updated_at": datetime.now().isoformat(),
    }


def _get_stock_build_status(industry_name: str, top_n: int) -> dict:
    _, full_cache_key = _get_stock_cache_keys(industry_name, top_n)
    cached = _get_endpoint_cache(full_cache_key)
    if cached is not None:
        return {
            "industry_name": industry_name,
            "top_n": top_n,
            "status": "ready",
            "rows": len(cached),
            "message": "完整版成分股缓存已就绪",
            "updated_at": datetime.now().isoformat(),
        }
    return _stocks_full_build_status.get(
        _get_stock_status_key(industry_name, top_n),
        {
            "industry_name": industry_name,
            "top_n": top_n,
            "status": "idle",
            "rows": 0,
            "message": "当前尚未开始构建完整版成分股缓存",
            "updated_at": datetime.now().isoformat(),
        },
    )


def _load_heatmap_history_from_disk() -> None:
    global _heatmap_history_loaded
    with _heatmap_history_lock:
        if _heatmap_history_loaded:
            return
        try:
            if _HEATMAP_HISTORY_FILE.exists():
                file_size = _HEATMAP_HISTORY_FILE.stat().st_size
                with open(_HEATMAP_HISTORY_FILE, encoding="utf-8") as file:
                    payload = json.load(file)
                    if isinstance(payload, list):
                        _heatmap_history[:] = _trim_heatmap_history_payload(payload)
                logger.info(
                    "Loaded heatmap history snapshots from disk (%s, snapshots=%s)",
                    _format_storage_size(file_size),
                    len(_heatmap_history),
                )
        except Exception as exc:
            logger.warning("Failed to load heatmap history from disk: %s", exc)
        _heatmap_history_loaded = True


def _persist_heatmap_history_to_disk() -> None:
    try:
        _HEATMAP_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = _trim_heatmap_history_payload(_heatmap_history)
        _heatmap_history[:] = payload
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        with open(_HEATMAP_HISTORY_FILE, "w", encoding="utf-8") as file:
            file.write(serialized)
        logger.info(
            "Persisted heatmap history snapshots (%s, snapshots=%s)",
            _format_storage_size(len(serialized.encode("utf-8"))),
            len(payload),
        )
    except Exception as exc:
        logger.warning("Failed to persist heatmap history: %s", exc)


def _append_heatmap_history(days: int, result: HeatmapResponse):
    if not result or not getattr(result, "industries", None):
        return
    _load_heatmap_history_from_disk()

    entry = {
        "snapshot_id": f"{days}:{result.update_time}",
        "days": days,
        "captured_at": datetime.now().isoformat(),
        "update_time": result.update_time,
        "max_value": result.max_value,
        "min_value": result.min_value,
        "industries": [_model_to_dict(item) for item in result.industries],
    }

    with _heatmap_history_lock:
        existing_index = next(
            (
                index
                for index, item in enumerate(_heatmap_history)
                if item.get("days") == days and item.get("update_time") == result.update_time
            ),
            -1,
        )
        if existing_index >= 0:
            _heatmap_history[existing_index] = entry
        else:
            _heatmap_history.insert(0, entry)
            del _heatmap_history[_HEATMAP_HISTORY_MAX_ITEMS:]
        _persist_heatmap_history_to_disk()


def _build_heatmap_response_from_history(days: int) -> Optional[HeatmapResponse]:
    """从最近历史快照构造热力图响应，避免远端数据源慢启动拖垮首屏。"""
    _load_heatmap_history_from_disk()
    with _heatmap_history_lock:
        matching_items = [
            dict(item) for item in _heatmap_history if int(item.get("days", 0) or 0) == int(days)
        ]

    if not matching_items:
        return None

    latest = matching_items[0]
    try:
        industries = [
            HeatmapDataItem(**industry_item) for industry_item in latest.get("industries", [])
        ]
    except Exception as exc:
        logger.warning("Failed to hydrate heatmap history for days=%s: %s", days, exc)
        return None

    if not industries:
        return None

    return HeatmapResponse(
        industries=industries,
        max_value=latest.get("max_value", 0),
        min_value=latest.get("min_value", 0),
        update_time=latest.get("update_time")
        or latest.get("captured_at")
        or datetime.now().isoformat(),
    )


def _load_live_heatmap_response(days: int) -> HeatmapResponse:
    analyzer = get_industry_analyzer()
    heatmap_data = analyzer.get_industry_heatmap_data(days=days)
    result = _serialize_heatmap_response(heatmap_data)
    if result.industries:
        _set_endpoint_cache(f"heatmap:v2:{days}", result)
        _append_heatmap_history(days, result)
    return result


def _schedule_heatmap_refresh(days: int) -> None:
    """后台刷新热力图缓存；请求线程可先返回历史快照。"""
    normalized_days = int(days)
    cache_key = f"heatmap:v2:{normalized_days}"
    if _get_endpoint_cache(cache_key) is not None:
        return

    with _heatmap_refresh_lock:
        if normalized_days in _heatmap_refresh_inflight:
            return
        _heatmap_refresh_inflight.add(normalized_days)

    def _task() -> None:
        started_at = time.time()
        try:
            _load_live_heatmap_response(normalized_days)
            logger.info(
                "Refreshed heatmap cache for days=%s in %.2fs",
                normalized_days,
                time.time() - started_at,
            )
        except Exception as exc:
            logger.warning("Failed to refresh heatmap cache for days=%s: %s", normalized_days, exc)
        finally:
            with _heatmap_refresh_lock:
                _heatmap_refresh_inflight.discard(normalized_days)

    _heatmap_refresh_executor.submit(_task)


def _resolve_symbol_with_provider(symbol_or_name: str) -> str:
    """允许详情接口和龙头列表同时接受代码或股票名。"""
    normalized = normalize_symbol(symbol_or_name)
    if re.fullmatch(r"\d{6}", normalized):
        return normalized

    provider = _get_or_create_provider()
    if hasattr(provider, "get_symbol_by_name"):
        try:
            resolved = normalize_symbol(provider.get_symbol_by_name(symbol_or_name))
            if re.fullmatch(r"\d{6}", resolved):
                return resolved
        except Exception as e:
            logger.warning(f"Failed to resolve symbol '{symbol_or_name}': {e}")

    return normalized


def _build_stock_responses(
    stocks: list[dict],
    industry_name: str,
    top_n: int,
    score_stage: Optional[str] = None,
) -> list[StockResponse]:
    """将 provider 返回的原始成分股标准化为接口响应。"""
    normalized_stocks = []
    for idx, stock in enumerate(stocks[:top_n], 1):
        symbol = normalize_symbol(stock.get("symbol") or stock.get("code") or "")
        if not symbol:
            continue
        detail_fields = extract_stock_detail_fields(stock)

        normalized_stocks.append(
            StockResponse(
                symbol=symbol,
                name=stock.get("name", ""),
                rank=int(stock.get("rank") or idx),
                total_score=float(stock.get("total_score") or 0),
                scoreStage=score_stage,
                market_cap=detail_fields.get("market_cap"),
                pe_ratio=detail_fields.get("pe_ratio"),
                change_pct=detail_fields.get("change_pct"),
                money_flow=detail_fields.get("money_flow"),
                turnover_rate=detail_fields.get("turnover_rate") or detail_fields.get("turnover"),
                industry=industry_name,
            )
        )

    return normalized_stocks


def _count_quick_stock_detail_fields(stock: dict[str, Any]) -> int:
    detail_fields = extract_stock_detail_fields(stock)
    return sum(
        [
            1 if has_meaningful_numeric(detail_fields.get("market_cap")) else 0,
            1 if has_meaningful_numeric(detail_fields.get("pe_ratio")) else 0,
            1 if detail_fields.get("money_flow") is not None else 0,
            1 if has_meaningful_numeric(detail_fields.get("turnover_rate")) else 0,
        ]
    )


def _promote_detail_ready_quick_rows(
    stocks: list[dict[str, Any]],
    visible_top_n: int = 5,
    detail_target: int = 2,
) -> list[dict[str, Any]]:
    """在 quick 阶段尽量让首屏先出现有真实明细的成分股。"""
    if not stocks:
        return stocks

    front_size = min(len(stocks), visible_top_n)
    target_count = min(detail_target, front_size)
    front_rows = list(stocks[:front_size])
    back_rows = list(stocks[front_size:])

    front_detail_indexes = [
        index
        for index, stock in enumerate(front_rows)
        if _count_quick_stock_detail_fields(stock) > 0
    ]
    if len(front_detail_indexes) >= target_count:
        return stocks

    promoted_rows: list[dict[str, Any]] = []
    remaining_back_rows: list[dict[str, Any]] = []
    needed_promotions = target_count - len(front_detail_indexes)

    for stock in back_rows:
        if len(promoted_rows) < needed_promotions and _count_quick_stock_detail_fields(stock) > 0:
            promoted_rows.append(stock)
            continue
        remaining_back_rows.append(stock)

    if not promoted_rows:
        return stocks

    replacement_positions = [
        index
        for index, stock in reversed(list(enumerate(front_rows)))
        if _count_quick_stock_detail_fields(stock) == 0
    ][: len(promoted_rows)]
    if not replacement_positions:
        return stocks

    replacement_positions_set = set(replacement_positions)
    kept_front_rows = [
        stock for index, stock in enumerate(front_rows) if index not in replacement_positions_set
    ]
    displaced_front_rows = [
        stock for index, stock in enumerate(front_rows) if index in replacement_positions_set
    ]
    return kept_front_rows + promoted_rows + displaced_front_rows + remaining_back_rows


def _load_cached_quick_valuation(provider, symbol: str) -> dict[str, Any]:
    """仅读取缓存估值；旧测试桩不支持 cached_only 时退回老签名。"""
    if provider is None or not hasattr(provider, "get_stock_valuation"):
        return {}

    try:
        valuation = provider.get_stock_valuation(symbol, cached_only=True)
    except TypeError:
        try:
            valuation = provider.get_stock_valuation(symbol)
        except Exception as exc:
            logger.warning("Failed to load quick valuation for %s: %s", symbol, exc)
            return {}
    except Exception as exc:
        logger.warning("Failed to load cached quick valuation for %s: %s", symbol, exc)
        return {}

    if not isinstance(valuation, dict) or valuation.get("error"):
        return {}
    return valuation


def _backfill_quick_rows_with_cached_valuation(
    stocks: list[dict[str, Any]],
    provider,
) -> list[dict[str, Any]]:
    """用 cached-only 估值补齐 quick 首屏所需字段，避免远端冷启动阻塞接口。"""
    if not stocks or provider is None or not hasattr(provider, "get_stock_valuation"):
        return stocks

    valuation_cache: dict[str, dict[str, Any]] = {}
    enriched: list[dict[str, Any]] = []

    for stock in stocks:
        symbol = normalize_symbol(stock.get("symbol") or stock.get("code") or "")
        if not symbol:
            enriched.append(stock)
            continue

        detail_fields = extract_stock_detail_fields(stock)
        missing_market_cap = not has_meaningful_numeric(detail_fields.get("market_cap"))
        missing_pe_ratio = not has_meaningful_numeric(detail_fields.get("pe_ratio"))
        missing_change_pct = detail_fields.get("change_pct") is None
        missing_turnover_rate = not has_meaningful_numeric(detail_fields.get("turnover_rate"))

        if not (
            missing_market_cap or missing_pe_ratio or missing_change_pct or missing_turnover_rate
        ):
            enriched.append(stock)
            continue

        if symbol not in valuation_cache:
            valuation_cache[symbol] = _load_cached_quick_valuation(provider, symbol)
        valuation = valuation_cache[symbol]
        if not valuation:
            enriched.append(stock)
            continue

        valuation_market_cap = coerce_optional_float(valuation.get("market_cap"))
        valuation_pe_ratio = coerce_optional_float(
            valuation.get("pe_ratio", valuation.get("pe_ttm"))
        )
        valuation_change_pct = coerce_optional_float(valuation.get("change_pct"))
        valuation_turnover_rate = coerce_optional_float(
            valuation.get("turnover_rate", valuation.get("turnover"))
        )

        enriched_stock = dict(stock)
        if missing_market_cap and has_meaningful_numeric(valuation_market_cap):
            enriched_stock["market_cap"] = valuation_market_cap
        if missing_pe_ratio and has_meaningful_numeric(valuation_pe_ratio):
            enriched_stock["pe_ratio"] = valuation_pe_ratio
        if missing_change_pct and valuation_change_pct is not None:
            enriched_stock["change_pct"] = valuation_change_pct
        if missing_turnover_rate and has_meaningful_numeric(valuation_turnover_rate):
            enriched_stock["turnover_rate"] = valuation_turnover_rate
            enriched_stock["turnover"] = valuation_turnover_rate
        if not enriched_stock.get("name") and valuation.get("name"):
            enriched_stock["name"] = valuation["name"]

        enriched.append(enriched_stock)

    return enriched


def _build_full_industry_stock_response(
    industry_name: str,
    top_n: int,
    provider=None,
) -> list[StockResponse]:
    """构造完整版行业成分股结果（评分排序 + 明细补齐 + 估值回填）。"""
    scorer = get_leader_scorer()
    provider = provider or _get_or_create_provider()

    ranked_stocks = scorer.rank_stocks_in_industry(industry_name, top_n=top_n)
    provider_stocks = provider.get_stock_list_by_industry(industry_name)

    if ranked_stocks:
        enriched_stocks = build_enriched_industry_stocks(
            provider,
            industry_name,
            ranked_stocks=ranked_stocks,
            provider_stocks=provider_stocks,
        )
        return _build_stock_responses(enriched_stocks, industry_name, top_n, score_stage="full")

    if provider_stocks:
        fallback_stocks = build_enriched_industry_stocks(
            provider,
            industry_name,
            provider_stocks=provider_stocks,
        )
        return _build_stock_responses(fallback_stocks, industry_name, top_n, score_stage="full")

    return []


def _build_quick_industry_stock_response(
    industry_name: str,
    top_n: int,
    provider_stocks: list[dict],
    provider=None,
    enable_valuation_backfill: bool = True,
) -> list[StockResponse]:
    """构造快速版行业成分股结果（仅用现有行情和缓存估值做轻量评分）。"""
    if not provider_stocks:
        return []

    try:
        scorer = get_leader_scorer()
        provider = provider or getattr(scorer, "provider", None) or _get_or_create_provider()
        industry_stats = scorer.calculate_industry_stats(provider_stocks)
        quick_scored_stocks = []
        for stock in provider_stocks:
            quick_score = scorer.score_stock_from_industry_snapshot(
                stock,
                industry_stats,
                score_type="core",
            )
            quick_scored_stocks.append(
                {
                    **stock,
                    "symbol": quick_score.get("symbol") or stock.get("symbol"),
                    "name": quick_score.get("name") or stock.get("name"),
                    "total_score": quick_score.get("total_score"),
                }
            )
        quick_scored_stocks.sort(
            key=lambda item: float(item.get("total_score") or 0),
            reverse=True,
        )

        quick_display_stocks = quick_scored_stocks[:top_n]
        if provider is not None:
            # 本地快照首屏优先保证尽快可渲染，避免首次请求重新被估值回填拖回远端冷启动。
            if enable_valuation_backfill:
                quick_display_stocks = _backfill_quick_rows_with_cached_valuation(
                    quick_display_stocks, provider
                )
            quick_display_stocks = _promote_detail_ready_quick_rows(quick_display_stocks)

        for idx, stock in enumerate(quick_display_stocks, 1):
            stock["rank"] = idx
        return _build_stock_responses(
            quick_display_stocks, industry_name, top_n, score_stage="quick"
        )
    except Exception as e:
        logger.warning(f"Failed to build quick stock scores for {industry_name}: {e}")
        return _build_stock_responses(provider_stocks, industry_name, top_n, score_stage="quick")


def _coerce_trend_alignment_stock_rows(stocks: list[Any]) -> list[dict[str, Any]]:
    """将 StockResponse / dict 统一转成趋势面板可复用的成分股字典。"""
    rows: list[dict[str, Any]] = []
    for stock in stocks or []:
        payload = _model_to_dict(stock)
        symbol = normalize_symbol(payload.get("symbol") or payload.get("code") or "")
        if not symbol:
            continue
        rows.append(
            {
                "symbol": symbol,
                "code": symbol,
                "name": payload.get("name", ""),
                "market_cap": payload.get("market_cap"),
                "pe_ratio": payload.get("pe_ratio"),
                "change_pct": payload.get("change_pct"),
                "money_flow": payload.get("money_flow"),
                "turnover_rate": payload.get("turnover_rate"),
                "turnover": payload.get("turnover_rate"),
                "total_score": payload.get("total_score"),
            }
        )
    return rows


def _load_trend_alignment_stock_rows(
    industry_name: str,
    expected_count: int,
    provider=None,
) -> list[dict[str, Any]]:
    """
    为趋势详情加载一组与弹窗成分股列表更一致的股票行。

    这里优先复用 stocks 接口缓存；若没有缓存，再走 quick 构建，避免趋势接口被完整评分阻塞。
    """
    provider = provider or _get_or_create_provider()
    target_top_n = min(max(int(expected_count or 0), 12), 30) if expected_count else 20
    quick_cache_key, full_cache_key = _get_stock_cache_keys(industry_name, target_top_n)

    cached_rows = _get_endpoint_cache(full_cache_key)
    if cached_rows is None:
        cached_rows = _get_endpoint_cache(quick_cache_key)
    if cached_rows is not None:
        return _coerce_trend_alignment_stock_rows(cached_rows)

    provider_rows: list[dict[str, Any]] = []
    cached_stock_loader = getattr(provider, "get_cached_stock_list_by_industry", None)
    if callable(cached_stock_loader):
        try:
            provider_rows = cached_stock_loader(industry_name) or []
        except Exception as exc:
            logger.warning(
                "Failed to load cached trend-alignment stocks for %s: %s", industry_name, exc
            )

    if not provider_rows:
        try:
            provider_rows = provider.get_stock_list_by_industry(industry_name) or []
        except Exception as exc:
            logger.warning(
                "Failed to load provider trend-alignment stocks for %s: %s", industry_name, exc
            )
            provider_rows = []

    if provider_rows:
        quick_rows = _build_quick_industry_stock_response(
            industry_name,
            target_top_n,
            provider_rows,
            provider=provider,
            enable_valuation_backfill=False,
        )
        if quick_rows:
            return _coerce_trend_alignment_stock_rows(quick_rows)

    full_rows = _build_full_industry_stock_response(
        industry_name,
        target_top_n,
        provider=provider,
    )
    return _coerce_trend_alignment_stock_rows(full_rows)


def _build_trend_summary_from_stock_rows(
    stocks: list[dict[str, Any]],
    expected_count: int,
    fallback_total_market_cap: float = 0.0,
    fallback_avg_pe: float = 0.0,
) -> dict[str, Any]:
    """根据统一股票列表重建趋势面板的成分股摘要字段。"""
    expected_count = max(int(expected_count or 0), 0)
    expected_count_base = max(expected_count, 1)

    detailed_stocks = []
    valid_change_stocks = []
    for stock in stocks or []:
        detail = extract_stock_detail_fields(stock)
        enriched_stock = {**stock, **detail}
        detailed_stocks.append(enriched_stock)
        if detail.get("change_pct") is not None:
            valid_change_stocks.append(enriched_stock)

    valid_market_caps = [
        stock["market_cap"]
        for stock in detailed_stocks
        if has_meaningful_numeric(stock.get("market_cap"))
    ]
    valid_pe_ratios = [
        stock["pe_ratio"]
        for stock in detailed_stocks
        if stock.get("pe_ratio") is not None and 0 < stock["pe_ratio"] < 500
    ]
    valid_pe_weighted_pairs = [
        (stock["market_cap"], stock["pe_ratio"])
        for stock in detailed_stocks
        if has_meaningful_numeric(stock.get("market_cap"))
        and stock.get("pe_ratio") is not None
        and 0 < stock["pe_ratio"] < 500
    ]

    total_market_cap = sum(float(value) for value in valid_market_caps)
    total_market_cap_fallback = False
    if not total_market_cap and fallback_total_market_cap > 0:
        total_market_cap = float(fallback_total_market_cap)
        total_market_cap_fallback = True

    if valid_pe_weighted_pairs:
        total_pe_market_cap = sum(float(market_cap) for market_cap, _ in valid_pe_weighted_pairs)
        total_earnings_proxy = sum(
            float(market_cap) / float(pe_ratio)
            for market_cap, pe_ratio in valid_pe_weighted_pairs
            if float(pe_ratio) > 0
        )
        avg_pe = (
            (total_pe_market_cap / total_earnings_proxy)
            if total_pe_market_cap > 0 and total_earnings_proxy > 0
            else None
        )
    elif valid_pe_ratios:
        avg_pe = sum(float(value) for value in valid_pe_ratios) / len(valid_pe_ratios)
    else:
        avg_pe = None

    avg_pe_fallback = False
    if avg_pe is None and fallback_avg_pe > 0:
        avg_pe = float(fallback_avg_pe)
        avg_pe_fallback = True

    stock_coverage_ratio = (
        min(len(stocks) / expected_count_base, 1.0)
        if expected_count > 0
        else (1.0 if stocks else 0.0)
    )
    change_coverage_ratio = (
        min(len(valid_change_stocks) / expected_count_base, 1.0)
        if expected_count > 0
        else (1.0 if valid_change_stocks else 0.0)
    )
    market_cap_coverage_ratio = (
        min(len(valid_market_caps) / expected_count_base, 1.0)
        if expected_count > 0
        else (1.0 if valid_market_caps else 0.0)
    )
    pe_coverage_base = (
        len(valid_pe_weighted_pairs) if valid_pe_weighted_pairs else len(valid_pe_ratios)
    )
    pe_coverage_ratio = (
        min(pe_coverage_base / expected_count_base, 1.0)
        if expected_count > 0
        else (1.0 if pe_coverage_base > 0 else 0.0)
    )

    top_gainers = sorted(
        valid_change_stocks, key=lambda item: item.get("change_pct", 0), reverse=True
    )[:5]
    top_losers = sorted(valid_change_stocks, key=lambda item: item.get("change_pct", 0))[:5]
    rise_count = sum(1 for item in valid_change_stocks if item.get("change_pct", 0) > 0)
    fall_count = sum(1 for item in valid_change_stocks if item.get("change_pct", 0) < 0)
    flat_count = sum(1 for item in valid_change_stocks if item.get("change_pct", 0) == 0)

    note = None
    degraded = False
    if len(stocks) <= 3 and expected_count > 10:
        degraded = True
        note = f"成分股列表可能不完整（获取到 {len(stocks)} 只，预期约 {expected_count} 只）。当前展示可能存在偏差。"
    elif len(stocks) == 1:
        note = "该行业目前仅获取到单只成分股明细，分布数据仅供参考。"

    return {
        "stock_count": len(stocks),
        "expected_stock_count": expected_count,
        "total_market_cap": total_market_cap,
        "avg_pe": round(avg_pe, 2)
        if avg_pe is not None and not (isinstance(avg_pe, float) and math.isnan(avg_pe))
        else 0,
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "rise_count": rise_count,
        "fall_count": fall_count,
        "flat_count": flat_count,
        "stock_coverage_ratio": round(stock_coverage_ratio, 4),
        "change_coverage_ratio": round(change_coverage_ratio, 4),
        "market_cap_coverage_ratio": round(market_cap_coverage_ratio, 4),
        "pe_coverage_ratio": round(pe_coverage_ratio, 4),
        "total_market_cap_fallback": total_market_cap_fallback,
        "avg_pe_fallback": avg_pe_fallback,
        "degraded": degraded,
        "note": note,
    }


def _should_align_trend_with_stock_rows(
    trend_data: dict[str, Any],
    stock_rows: list[dict[str, Any]],
) -> bool:
    """判断趋势摘要是否应该回收成分股列表口径。"""
    if not stock_rows:
        return False

    trend_count = int(trend_data.get("stock_count", 0) or 0)
    expected_count = int(trend_data.get("expected_stock_count", 0) or 0)
    aligned_count = len(stock_rows)

    if trend_data.get("degraded") and aligned_count > trend_count:
        return True
    if trend_count <= 3 and aligned_count >= 5:
        return True
    if expected_count > 0 and trend_count > max(expected_count * 2, expected_count + 15):
        return aligned_count >= min(max(expected_count // 3, 4), 30)
    return False


def _schedule_full_stock_cache_build(
    industry_name: str,
    top_n: int,
) -> None:
    """异步构建完整版行业成分股缓存。"""
    _, full_cache_key = _get_stock_cache_keys(industry_name, top_n)
    if _get_endpoint_cache(full_cache_key) is not None:
        return

    with _stocks_full_build_lock:
        if full_cache_key in _stocks_full_build_inflight:
            return
        _stocks_full_build_inflight.add(full_cache_key)
        _set_stock_build_status(
            industry_name, top_n, "building", rows=0, message="完整版成分股缓存构建中"
        )

    def _task():
        started_at = time.time()
        try:
            logger.info(
                "Building full stock cache for %s (top_n=%s)",
                industry_name,
                top_n,
            )
            result = _build_full_industry_stock_response(industry_name, top_n)
            if result:
                _set_endpoint_cache(full_cache_key, result)
                _set_stock_build_status(
                    industry_name,
                    top_n,
                    "ready",
                    rows=len(result),
                    message="完整版成分股缓存构建完成",
                )
                logger.info(
                    "Built full stock cache for %s (top_n=%s, rows=%s, elapsed=%.2fs)",
                    industry_name,
                    top_n,
                    len(result),
                    time.time() - started_at,
                )
            else:
                _set_stock_build_status(
                    industry_name,
                    top_n,
                    "failed",
                    rows=0,
                    message="完整版成分股缓存构建返回空结果",
                )
                logger.warning(
                    "Full stock cache build returned empty for %s (top_n=%s, elapsed=%.2fs)",
                    industry_name,
                    top_n,
                    time.time() - started_at,
                )
        except Exception as e:
            _set_stock_build_status(
                industry_name,
                top_n,
                "failed",
                rows=0,
                message=f"构建失败: {e}",
            )
            logger.warning(f"Failed to build full stock cache for {industry_name}: {e}")
        finally:
            with _stocks_full_build_lock:
                _stocks_full_build_inflight.discard(full_cache_key)

    _stocks_full_build_executor.submit(_task)


def _dedupe_leader_responses(leaders: list[LeaderStockResponse]) -> list[LeaderStockResponse]:
    """按 symbol 去重，保留总分更高、信息更完整的记录。"""
    best_by_symbol: dict[str, LeaderStockResponse] = {}

    for leader in leaders:
        symbol = normalize_symbol(getattr(leader, "symbol", ""))
        if not re.fullmatch(r"\d{6}", symbol):
            continue

        leader.symbol = symbol
        current = best_by_symbol.get(symbol)
        if current is None:
            best_by_symbol[symbol] = leader
            continue

        current_score = float(getattr(current, "total_score", 0) or 0)
        next_score = float(getattr(leader, "total_score", 0) or 0)
        current_cap = float(getattr(current, "market_cap", 0) or 0)
        next_cap = float(getattr(leader, "market_cap", 0) or 0)

        if (next_score, next_cap) > (current_score, current_cap):
            best_by_symbol[symbol] = leader

    deduped = list(best_by_symbol.values())
    deduped.sort(key=lambda item: float(getattr(item, "total_score", 0) or 0), reverse=True)
    for idx, leader in enumerate(deduped, 1):
        leader.global_rank = idx
    return deduped


def _get_or_create_provider():
    """获取或创建数据提供器实例（共用逻辑）"""
    global _akshare_provider
    if _akshare_provider is None:
        try:
            from src.data.providers.sina_ths_adapter import create_industry_provider

            _akshare_provider = create_industry_provider()
        except Exception as e:
            logger.warning(f"Failed to create provider via factory: {e}")
            from src.data.providers.sina_ths_adapter import SinaIndustryAdapter

            _akshare_provider = SinaIndustryAdapter()
    return _akshare_provider


def get_industry_analyzer():
    """获取行业分析器实例（延迟初始化，自动选择数据源）"""
    global _industry_analyzer

    if _industry_analyzer is None:
        try:
            from src.analytics.industry_analyzer import IndustryAnalyzer

            provider = _get_or_create_provider()
            _industry_analyzer = IndustryAnalyzer(provider)
            logger.info(f"Industry analyzer initialized with {type(provider).__name__}")
        except Exception as e:
            logger.error(f"Failed to initialize industry analyzer: {e}")
            raise HTTPException(
                status_code=500, detail=f"Industry analyzer initialization failed: {e!s}"
            )

    return _industry_analyzer


def get_leader_scorer():
    """获取龙头股评分器实例（延迟初始化）"""
    global _leader_scorer

    if _leader_scorer is None:
        try:
            from src.analytics.leader_stock_scorer import LeaderStockScorer

            provider = _get_or_create_provider()
            _leader_scorer = LeaderStockScorer(provider)
            logger.info(f"Leader stock scorer initialized with {type(provider).__name__}")
        except Exception as e:
            logger.error(f"Failed to initialize leader scorer: {e}")
            raise HTTPException(
                status_code=500, detail=f"Leader scorer initialization failed: {e!s}"
            )

    return _leader_scorer


def _build_leader_context(
    top_industries: int,
    analyzer=None,
) -> tuple[Any, list[dict[str, Any]], set[str]]:
    analyzer = analyzer or get_industry_analyzer()
    hot_industries = analyzer.rank_industries(top_n=top_industries)
    top_industry_names = {
        industry.get("industry_name")
        for industry in hot_industries
        if industry.get("industry_name")
    }
    return analyzer, hot_industries, top_industry_names


def _get_leader_overview_cache_key(top_n: int, top_industries: int, per_industry: int) -> str:
    return f"leaders:overview:v1:{top_n}:{top_industries}:{per_industry}"


def _get_leader_provider_stocks_cache_key(industry_name: str) -> str:
    return f"leaders:provider_stocks:v1:{industry_name}"


def _get_leader_snapshot_prewarm_key(industry_name: str) -> str:
    return f"leaders:stock_snapshot:v1:{industry_name}"


def _has_leader_board_rows(payload: Any) -> bool:
    board_payload = _model_to_dict(payload) or {}
    return bool(board_payload.get("core") or board_payload.get("hot"))


def _build_leader_boards_payload(
    top_n: int,
    top_industries: int,
    per_industry: int,
    analyzer=None,
    hot_industries: Optional[list[dict[str, Any]]] = None,
    top_industry_names: Optional[set[str]] = None,
) -> LeaderBoardsResponse:
    if analyzer is None or hot_industries is None or top_industry_names is None:
        analyzer, hot_industries, top_industry_names = _build_leader_context(
            top_industries, analyzer=analyzer
        )

    results: dict[str, list[LeaderStockResponse]] = {"core": [], "hot": []}
    errors: dict[str, str] = {}
    provider_stock_cache: dict[str, Any] = {}
    provider_stock_cache_lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_map = {
            "core": executor.submit(
                _load_leader_stock_list,
                top_n=top_n,
                top_industries=top_industries,
                per_industry=per_industry,
                list_type="core",
                analyzer=analyzer,
                hot_industries=hot_industries,
                top_industry_names=top_industry_names,
                provider_stock_cache=provider_stock_cache,
                provider_stock_cache_lock=provider_stock_cache_lock,
            ),
            "hot": executor.submit(
                _load_leader_stock_list,
                top_n=top_n,
                top_industries=top_industries,
                per_industry=per_industry,
                list_type="hot",
                analyzer=analyzer,
                hot_industries=hot_industries,
                top_industry_names=top_industry_names,
                provider_stock_cache=provider_stock_cache,
                provider_stock_cache_lock=provider_stock_cache_lock,
            ),
        }
        for list_type, future in future_map.items():
            try:
                results[list_type] = future.result()
            except HTTPException as exc:
                logger.warning("Leader overview failed for %s list: %s", list_type, exc.detail)
                errors[list_type] = (
                    "核心资产榜单加载失败" if list_type == "core" else "热点先锋榜单加载失败"
                )
            except Exception as exc:
                logger.error("Leader overview failed for %s list: %s", list_type, exc)
                errors[list_type] = (
                    "核心资产榜单加载失败" if list_type == "core" else "热点先锋榜单加载失败"
                )

    return LeaderBoardsResponse(
        core=results["core"],
        hot=results["hot"],
        errors=errors,
    )


def _prewarm_leader_stock_snapshot(industry_name: str, analyzer=None) -> None:
    normalized_name = str(industry_name or "").strip()
    if not normalized_name:
        return

    analyzer = analyzer or get_industry_analyzer()
    provider = getattr(analyzer, "provider", None)
    if provider is None:
        return

    akshare_provider = getattr(provider, "akshare", None)
    persist_snapshot = getattr(akshare_provider, "persist_stock_list_snapshot", None)

    cached_loader = getattr(provider, "get_cached_stock_list_by_industry", None)
    if callable(cached_loader):
        try:
            cached_rows = cached_loader(normalized_name) or []
            if cached_rows:
                if callable(persist_snapshot):
                    try:
                        persist_snapshot(
                            normalized_name,
                            cached_rows,
                            include_market_cap_lookup=False,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Leader snapshot persist failed for %s: %s", normalized_name, exc
                        )
                return
        except Exception as exc:
            logger.warning(
                "Leader snapshot prewarm cached lookup failed for %s: %s", normalized_name, exc
            )

    if akshare_provider is None:
        return

    akshare_cached_loader = getattr(akshare_provider, "get_cached_stock_list_by_industry", None)
    if callable(akshare_cached_loader):
        try:
            cached_rows = (
                akshare_cached_loader(
                    normalized_name,
                    include_market_cap_lookup=False,
                    allow_stale=True,
                )
                or []
            )
            if cached_rows:
                return
        except TypeError:
            cached_rows = akshare_cached_loader(normalized_name) or []
            if cached_rows:
                return
        except Exception as exc:
            logger.warning("AKShare snapshot lookup failed for %s: %s", normalized_name, exc)

    akshare_loader = getattr(akshare_provider, "get_stock_list_by_industry", None)
    if callable(akshare_loader):
        try:
            akshare_loader(normalized_name, include_market_cap_lookup=False)
        except TypeError:
            akshare_loader(normalized_name)
        except Exception as exc:
            logger.warning(
                "Leader snapshot prewarm live fetch failed for %s: %s", normalized_name, exc
            )


def _schedule_leader_stock_snapshot_prewarm(
    analyzer,
    hot_industries: Optional[list[dict[str, Any]]],
) -> None:
    if not hot_industries:
        return

    for industry in hot_industries:
        industry_name = str(industry.get("industry_name") or "").strip()
        if not industry_name:
            continue
        inflight_key = _get_leader_snapshot_prewarm_key(industry_name)
        with _leader_snapshot_prewarm_lock:
            if inflight_key in _leader_snapshot_prewarm_inflight:
                continue
            _leader_snapshot_prewarm_inflight.add(inflight_key)

        future = _leader_snapshot_prewarm_executor.submit(
            _prewarm_leader_stock_snapshot,
            industry_name,
            analyzer,
        )

        def _cleanup(_: Future, key: str = inflight_key) -> None:
            with _leader_snapshot_prewarm_lock:
                _leader_snapshot_prewarm_inflight.discard(key)

        future.add_done_callback(_cleanup)


def _compute_and_cache_leader_overview(
    cache_key: str,
    top_n: int,
    top_industries: int,
    per_industry: int,
    analyzer=None,
    hot_industries: Optional[list[dict[str, Any]]] = None,
    top_industry_names: Optional[set[str]] = None,
) -> LeaderBoardsResponse:
    payload = _build_leader_boards_payload(
        top_n=top_n,
        top_industries=top_industries,
        per_industry=per_industry,
        analyzer=analyzer,
        hot_industries=hot_industries,
        top_industry_names=top_industry_names,
    )
    _schedule_leader_stock_snapshot_prewarm(analyzer, hot_industries)
    if _has_leader_board_rows(payload):
        _set_endpoint_cache(cache_key, payload)
    return payload


def _schedule_leader_overview_build(
    top_n: int,
    top_industries: int,
    per_industry: int,
    analyzer=None,
    hot_industries: Optional[list[dict[str, Any]]] = None,
    top_industry_names: Optional[set[str]] = None,
) -> Optional[Future]:
    cache_key = _get_leader_overview_cache_key(top_n, top_industries, per_industry)
    if _get_endpoint_cache(cache_key) is not None:
        return None

    with _leader_overview_build_lock:
        inflight = _leader_overview_build_inflight.get(cache_key)
        if inflight is not None and not inflight.done():
            return inflight

        hot_rows = [dict(row) for row in (hot_industries or [])] if hot_industries else None
        hot_names = set(top_industry_names) if top_industry_names else None
        future = _leader_overview_build_executor.submit(
            _compute_and_cache_leader_overview,
            cache_key,
            top_n,
            top_industries,
            per_industry,
            analyzer,
            hot_rows,
            hot_names,
        )
        _leader_overview_build_inflight[cache_key] = future

        def _cleanup(done_future: Future) -> None:
            with _leader_overview_build_lock:
                if _leader_overview_build_inflight.get(cache_key) is done_future:
                    _leader_overview_build_inflight.pop(cache_key, None)

        future.add_done_callback(_cleanup)
        return future


def _load_leader_overview_payload(
    top_n: int,
    top_industries: int,
    per_industry: int,
    analyzer=None,
    hot_industries: Optional[list[dict[str, Any]]] = None,
    top_industry_names: Optional[set[str]] = None,
) -> LeaderBoardsResponse:
    cache_key = _get_leader_overview_cache_key(top_n, top_industries, per_industry)
    cached = _get_endpoint_cache(cache_key)
    if cached is not None:
        return cached

    build_error: Exception | HTTPException | None = None
    future = _schedule_leader_overview_build(
        top_n=top_n,
        top_industries=top_industries,
        per_industry=per_industry,
        analyzer=analyzer,
        hot_industries=hot_industries,
        top_industry_names=top_industry_names,
    )
    if future is None:
        cached = _get_endpoint_cache(cache_key)
        if cached is not None:
            return cached

    try:
        if future is not None:
            return future.result()
    except HTTPException as exc:
        build_error = exc
    except Exception as exc:
        logger.error("Leader overview build failed for %s: %s", cache_key, exc)
        build_error = exc

    stale = _get_stale_endpoint_cache(cache_key)
    if stale is not None:
        logger.warning("Using stale cache for leader overview: %s", cache_key)
        return stale
    if isinstance(build_error, HTTPException):
        raise build_error
    if build_error is not None:
        raise HTTPException(status_code=500, detail=str(build_error))
    return LeaderBoardsResponse()


def _get_bootstrap_leader_payload(
    top_n: int,
    top_industries: int,
    per_industry: int,
    analyzer=None,
    hot_industries: Optional[list[dict[str, Any]]] = None,
    top_industry_names: Optional[set[str]] = None,
) -> Optional[LeaderBoardsResponse]:
    cache_key = _get_leader_overview_cache_key(top_n, top_industries, per_industry)
    cached = _get_endpoint_cache(cache_key)
    if cached is not None:
        return cached

    stale = _get_stale_endpoint_cache(cache_key)
    _schedule_leader_overview_build(
        top_n=top_n,
        top_industries=top_industries,
        per_industry=per_industry,
        analyzer=analyzer,
        hot_industries=hot_industries,
        top_industry_names=top_industry_names,
    )
    if stale is not None and _has_leader_board_rows(stale):
        return stale
    return None


def _hydrate_bootstrap_with_cached_leaders(
    payload: IndustryBootstrapResponse,
    cache_key: str,
    leader_top_n: int,
    top_industries: int,
    per_industry: int,
) -> IndustryBootstrapResponse:
    if _has_leader_board_rows(payload.leaders):
        return payload

    overview_cache_key = _get_leader_overview_cache_key(leader_top_n, top_industries, per_industry)
    cached_overview = _get_endpoint_cache(overview_cache_key)
    if cached_overview is None:
        cached_overview = _get_stale_endpoint_cache(overview_cache_key)
        if cached_overview is not None:
            _schedule_leader_overview_build(
                top_n=leader_top_n,
                top_industries=top_industries,
                per_industry=per_industry,
            )

    if cached_overview is None or not _has_leader_board_rows(cached_overview):
        return payload

    payload_dict = _model_to_dict(payload)
    payload_dict["leaders"] = _model_to_dict(cached_overview)
    payload_dict["errors"] = {
        key: value
        for key, value in (payload_dict.get("errors") or {}).items()
        if not key.startswith("leaders")
    }
    hydrated = IndustryBootstrapResponse(**payload_dict)
    _set_endpoint_cache(cache_key, hydrated)
    return hydrated


def _persist_leader_list_cache(
    cache_key: str,
    list_type: Literal["hot", "core"],
    leaders: list[LeaderStockResponse],
) -> None:
    if not leaders:
        return
    _set_endpoint_cache(cache_key, leaders)
    for leader in leaders:
        _set_parity_cache(leader.symbol, list_type, leader)


def _load_provider_stocks_for_leaders(
    provider,
    industry_name: str,
    shared_cache: Optional[dict[str, Any]] = None,
    shared_cache_lock: Optional[threading.Lock] = None,
) -> list[dict[str, Any]]:
    cache_key = _get_leader_provider_stocks_cache_key(industry_name)
    cached_rows = _get_endpoint_cache(cache_key)
    if cached_rows is not None:
        return cached_rows

    wait_event = None
    owns_load = True
    if shared_cache is not None and shared_cache_lock is not None:
        with shared_cache_lock:
            shared_entry = shared_cache.get(industry_name)
            if isinstance(shared_entry, list):
                return shared_entry
            if isinstance(shared_entry, threading.Event):
                wait_event = shared_entry
                owns_load = False
            else:
                wait_event = threading.Event()
                shared_cache[industry_name] = wait_event

    if not owns_load:
        wait_event.wait(timeout=20)
        cached_rows = _get_endpoint_cache(cache_key)
        if cached_rows is not None:
            return cached_rows
        if shared_cache is not None and shared_cache_lock is not None:
            with shared_cache_lock:
                shared_entry = shared_cache.get(industry_name)
                if isinstance(shared_entry, list):
                    return shared_entry
        return []

    rows: list[dict[str, Any]] = []
    load_error: Exception | None = None
    cached_loader = getattr(provider, "get_cached_stock_list_by_industry", None)
    try:
        if callable(cached_loader):
            try:
                cached_rows = cached_loader(industry_name) or []
                if cached_rows:
                    rows = cached_rows
            except Exception as exc:
                logger.warning("Failed to load cached leader stocks for %s: %s", industry_name, exc)

        if not rows:
            try:
                rows = provider.get_stock_list_by_industry(industry_name, fast_mode=True) or []
            except TypeError:
                rows = provider.get_stock_list_by_industry(industry_name) or []

        if rows:
            _set_endpoint_cache(cache_key, rows)
        return rows
    except Exception as exc:
        load_error = exc
        raise
    finally:
        if shared_cache is not None and shared_cache_lock is not None and wait_event is not None:
            with shared_cache_lock:
                shared_cache[industry_name] = rows if rows else []
                wait_event.set()
        if (
            load_error is not None
            and shared_cache is not None
            and shared_cache_lock is not None
            and wait_event is None
        ):
            with shared_cache_lock:
                shared_cache[industry_name] = []


def _compute_core_leader_stocks(
    analyzer,
    hot_industries: list[dict[str, Any]],
    top_n: int,
    per_industry: int,
    provider_stock_cache: Optional[dict[str, Any]] = None,
    provider_stock_cache_lock: Optional[threading.Lock] = None,
) -> list[LeaderStockResponse]:
    scorer = get_leader_scorer()
    provider = analyzer.provider

    def _process_core_industry(industry):
        ind_name = industry.get("industry_name")
        if not ind_name:
            return []
        try:
            stocks = _load_provider_stocks_for_leaders(
                provider,
                ind_name,
                shared_cache=provider_stock_cache,
                shared_cache_lock=provider_stock_cache_lock,
            )
            if not stocks:
                return []

            candidate_pool = []
            for stock in stocks:
                sym = normalize_symbol(stock.get("symbol") or stock.get("code") or "")
                if not re.fullmatch(r"\d{6}", sym):
                    continue
                candidate_pool.append(
                    {
                        "symbol": sym,
                        "name": stock.get("name", ""),
                        "market_cap": float(stock.get("market_cap") or 0),
                        "pe_ratio": float(stock.get("pe_ratio") or 0),
                        "change_pct": float(stock.get("change_pct") or 0),
                        "amount": float(stock.get("amount") or 0),
                    }
                )

            if not candidate_pool:
                return []

            candidate_pool.sort(
                key=lambda item: (
                    item["market_cap"] > 0,
                    item["market_cap"],
                    item["amount"],
                    abs(item["change_pct"]),
                ),
                reverse=True,
            )

            valid_stocks = []
            for item in candidate_pool[: max(5, per_industry * 2)]:
                mkt_cap = item["market_cap"]
                pe = item["pe_ratio"]
                if mkt_cap > 0 and mkt_cap < 3000000000:
                    continue
                if pe != 0 and (pe < 0 or pe > 150):
                    continue
                valid_stocks.append(item["symbol"])

            if not valid_stocks:
                valid_stocks = [
                    item["symbol"] for item in candidate_pool[: min(5, len(candidate_pool))]
                ]

            logger.debug("For %s, selected %s valid core candidates.", ind_name, len(valid_stocks))
            candidate_map = {item["symbol"]: item for item in candidate_pool}
            industry_stats = scorer.calculate_industry_stats(candidate_pool)

            fast_results = []
            for sym in valid_stocks[: max(5, int(per_industry * 1.5))]:
                snapshot = candidate_map.get(sym, {"symbol": sym, "name": sym})
                score_detail = scorer.score_stock_from_snapshot(
                    snapshot, industry_stats=industry_stats, enrich_financial=False
                )
                roe = score_detail.get("raw_data", {}).get("roe")
                if roe is not None and roe < 0:
                    continue
                fast_results.append((sym, score_detail.get("total_score", 0), score_detail))

            fast_results.sort(key=lambda item: item[1], reverse=True)
            top_symbols = [sym for sym, _, _ in fast_results[:per_industry]]

            industry_core_list = []
            for sym in top_symbols:
                snapshot = candidate_map.get(sym, {"symbol": sym, "name": sym})
                score_detail = None
                with contextlib.suppress(Exception):
                    score_detail = scorer.score_stock_from_snapshot(
                        snapshot,
                        industry_stats=industry_stats,
                        enrich_financial=True,
                        cached_only=True,
                    )
                if not score_detail or "error" in score_detail:
                    score_detail = scorer.score_stock_from_snapshot(
                        snapshot,
                        industry_stats=industry_stats,
                        enrich_financial=False,
                    )
                roe = score_detail.get("raw_data", {}).get("roe")
                if roe is not None and roe < 0:
                    continue
                industry_core_list.append(
                    LeaderStockResponse(
                        symbol=sym,
                        name=score_detail.get("name", sym),
                        industry=ind_name,
                        score_type="core",
                        global_rank=0,
                        industry_rank=0,
                        total_score=round(score_detail.get("total_score", 0), 2),
                        market_cap=score_detail.get("raw_data", {}).get(
                            "market_cap", snapshot.get("market_cap", 0)
                        ),
                        pe_ratio=score_detail.get("raw_data", {}).get(
                            "pe_ttm", snapshot.get("pe_ratio", 0)
                        ),
                        change_pct=score_detail.get("raw_data", {}).get(
                            "change_pct", snapshot.get("change_pct", 0)
                        ),
                        dimension_scores=score_detail.get("dimension_scores", {}),
                        mini_trend=[],
                    )
                )

            industry_core_list.sort(key=lambda item: item.total_score, reverse=True)
            for rank_idx, stock in enumerate(industry_core_list[:per_industry], 1):
                stock.industry_rank = rank_idx
            return industry_core_list[:per_industry]
        except Exception as exc:
            logger.error("Error fetching core stocks for %s: %s", ind_name, exc)
            return []

    core_leaders: list[LeaderStockResponse] = []
    # After the provider path was tightened around local snapshots and endpoint caches,
    # thread-pool startup/teardown became more expensive than the per-industry work itself.
    industry_results = [_process_core_industry(industry) for industry in hot_industries]
    for result in industry_results:
        core_leaders.extend(result)

    try:
        from src.analytics.leader_stock_scorer import LeaderStockScorer

        LeaderStockScorer._persist_financial_cache()
    except Exception:
        pass

    return _dedupe_leader_responses(core_leaders)[:top_n]


def _compute_hot_leader_stocks(
    analyzer,
    hot_industries: list[dict[str, Any]],
    top_industry_names: set[str],
    top_n: int,
    per_industry: int,
    provider_stock_cache: Optional[dict[str, Any]] = None,
    provider_stock_cache_lock: Optional[threading.Lock] = None,
) -> list[LeaderStockResponse]:
    lightweight_loader = getattr(analyzer, "_load_lightweight_money_flow", None)
    if callable(lightweight_loader):
        try:
            heatmap_df = lightweight_loader(days=1)
        except Exception as exc:
            logger.warning(
                "Lightweight money flow loader failed for hot leaders, falling back to full flow: %s",
                exc,
            )
            heatmap_df = analyzer.analyze_money_flow(days=1)
    else:
        heatmap_df = analyzer.analyze_money_flow(days=1)
    leaders_from_heatmap: list[LeaderStockResponse] = []
    scorer = get_leader_scorer()
    valuation_provider = getattr(analyzer, "provider", None)
    leading_stock_symbol_lookup = _build_leading_stock_symbol_lookup()

    hot_candidates = _collect_hot_leader_candidates(heatmap_df, top_industry_names, top_n)
    if hot_candidates:

        def _score_hot_stock(row: dict[str, Any]):
            industry_name = row.get("industry_name", "")
            leading_stock = row.get("leading_stock")
            change_pct = float(row.get("leading_stock_change", row.get("change_pct", 0)) or 0)
            net_inflow_ratio = float(row.get("main_net_ratio", 0) or 0)

            quick_symbol = normalize_symbol(row.get("leading_stock_code") or leading_stock)
            if SIX_DIGIT_SYMBOL_PATTERN.fullmatch(quick_symbol):
                real_symbol = quick_symbol
            else:
                lookup_symbol = normalize_symbol(
                    leading_stock_symbol_lookup.get(str(leading_stock or "").strip()) or ""
                )
                if SIX_DIGIT_SYMBOL_PATTERN.fullmatch(lookup_symbol):
                    real_symbol = lookup_symbol
                else:
                    real_symbol = _resolve_symbol_with_provider(leading_stock)

            valuation_snapshot = {}
            if (
                SIX_DIGIT_SYMBOL_PATTERN.fullmatch(real_symbol)
                and valuation_provider
                and hasattr(valuation_provider, "get_stock_valuation")
            ):
                try:
                    candidate = valuation_provider.get_stock_valuation(
                        real_symbol, cached_only=True
                    )
                    if isinstance(candidate, dict) and "error" not in candidate:
                        valuation_snapshot = candidate
                except Exception as exc:
                    logger.warning(
                        "Failed to hydrate hot leader valuation for %s: %s", real_symbol, exc
                    )

            snapshot_data = {
                "symbol": real_symbol,
                "name": leading_stock,
                "market_cap": float(valuation_snapshot.get("market_cap") or 0),
                "pe_ratio": float(
                    valuation_snapshot.get("pe_ttm") or valuation_snapshot.get("pe_ratio") or 0
                ),
                "change_pct": change_pct,
                "amount": float(
                    valuation_snapshot.get("amount")
                    or abs(float(row.get("main_net_inflow", 0) or 0))
                ),
                "turnover": float(valuation_snapshot.get("turnover") or 0),
                "net_inflow_ratio": net_inflow_ratio,
            }

            score_detail = scorer.score_stock_from_snapshot(snapshot_data, score_type="hot")

            if "error" not in score_detail:
                scored_symbol = normalize_symbol(score_detail.get("symbol", real_symbol))
                market_cap = score_detail.get("raw_data", {}).get("market_cap", 0)
                pe_ratio = score_detail.get("raw_data", {}).get("pe_ttm", 0)
                dimension_scores = score_detail.get("dimension_scores", {})
                total_score = score_detail.get("total_score", 0)
            else:
                scored_symbol = real_symbol
                total_score = round(
                    min(
                        100,
                        max(
                            0,
                            (change_pct + 15) / 30 * 50
                            + max(0, min(50, net_inflow_ratio * 5 + 25)),
                        ),
                    ),
                    2,
                )
                market_cap = 0
                pe_ratio = 0
                dimension_scores = {
                    "momentum": min(1.0, max(0.0, (change_pct + 15) / 30)),
                    "money_flow": min(1.0, max(0.0, (net_inflow_ratio + 10) / 20)),
                    "valuation": 0.5,
                    "profitability": 0.5,
                    "growth": 0.5,
                    "activity": 0.5,
                    "score_type": "hot",
                }

            if not SIX_DIGIT_SYMBOL_PATTERN.fullmatch(scored_symbol):
                logger.warning(
                    "Skipping leader '%s' because symbol could not be resolved: %s",
                    leading_stock,
                    scored_symbol,
                )
                return None

            return LeaderStockResponse(
                symbol=scored_symbol,
                name=leading_stock,
                industry=industry_name,
                score_type="hot",
                global_rank=0,
                industry_rank=1,
                total_score=total_score,
                market_cap=market_cap,
                pe_ratio=pe_ratio,
                change_pct=change_pct,
                dimension_scores=dimension_scores,
                mini_trend=[],
            )

        # This path now relies mostly on lightweight money-flow snapshots and cached valuation reads.
        # Keeping it serial avoids per-request thread-pool churn that is often slower than the work itself.
        results = [_score_hot_stock(row) for row in hot_candidates]
        for result in results:
            if result:
                leaders_from_heatmap.append(result)

        leaders_from_heatmap = _dedupe_leader_responses(leaders_from_heatmap)[:top_n]

    if len(leaders_from_heatmap) < top_n:
        logger.info(
            "Heatmap hot leaders underfilled (%s/%s), backfilling from LeaderStockScorer",
            len(leaders_from_heatmap),
            top_n,
        )
        provider = getattr(analyzer, "provider", None)
        existing_symbols = {leader.symbol for leader in leaders_from_heatmap if leader.symbol}
        supplemental_responses: list[LeaderStockResponse] = []
        needed_count = max(0, top_n - len(leaders_from_heatmap))
        industry_names = [
            industry.get("industry_name")
            for industry in hot_industries
            if industry.get("industry_name")
        ]
        supplemental_per_industry = max(
            1,
            (needed_count + max(len(industry_names), 1) - 1) // max(len(industry_names), 1),
        )
        if provider is not None:
            for industry_name in industry_names:
                if len(supplemental_responses) >= needed_count:
                    break
                provider_rows = _load_provider_stocks_for_leaders(
                    provider,
                    industry_name,
                    shared_cache=provider_stock_cache,
                    shared_cache_lock=provider_stock_cache_lock,
                )
                if not provider_rows:
                    continue
                ranked_snapshots = []
                for row in provider_rows:
                    symbol = normalize_symbol(row.get("symbol") or row.get("code") or "")
                    if not re.fullmatch(r"\d{6}", symbol) or symbol in existing_symbols:
                        continue
                    snapshot = {
                        "symbol": symbol,
                        "name": row.get("name", ""),
                        "market_cap": float(row.get("market_cap") or 0),
                        "pe_ratio": float(row.get("pe_ratio") or 0),
                        "change_pct": float(row.get("change_pct") or 0),
                        "amount": float(row.get("amount") or 0),
                        "turnover": float(row.get("turnover") or row.get("turnover_ratio") or 0),
                        "net_inflow_ratio": float(row.get("net_inflow_ratio") or 0),
                    }
                    scored = scorer.score_stock_from_snapshot(snapshot, score_type="hot")
                    if "error" in scored:
                        continue
                    ranked_snapshots.append((scored.get("total_score", 0), snapshot, scored))

                ranked_snapshots.sort(key=lambda item: item[0], reverse=True)
                for rank_index, (_, snapshot, scored) in enumerate(
                    ranked_snapshots[:supplemental_per_industry], 1
                ):
                    existing_symbols.add(snapshot["symbol"])
                    supplemental_responses.append(
                        LeaderStockResponse(
                            symbol=snapshot["symbol"],
                            name=snapshot["name"],
                            industry=industry_name,
                            score_type="hot",
                            global_rank=0,
                            industry_rank=rank_index,
                            total_score=scored.get("total_score", 0),
                            market_cap=scored.get("raw_data", {}).get(
                                "market_cap", snapshot["market_cap"]
                            ),
                            pe_ratio=scored.get("raw_data", {}).get("pe_ttm", snapshot["pe_ratio"]),
                            change_pct=scored.get("raw_data", {}).get(
                                "change_pct", snapshot["change_pct"]
                            ),
                            dimension_scores=scored.get("dimension_scores", {}),
                            mini_trend=[],
                        )
                    )
                    if len(supplemental_responses) >= needed_count:
                        break

        if supplemental_responses:
            leaders_from_heatmap.extend(supplemental_responses)
            leaders_from_heatmap = _dedupe_leader_responses(leaders_from_heatmap)[:top_n]
        else:
            supplemental = scorer.get_leader_stocks(
                industry_names,
                top_per_industry=supplemental_per_industry,
                score_type="hot",
            )
            leaders_from_heatmap.extend(
                [
                    LeaderStockResponse(
                        symbol=item.get("symbol", ""),
                        name=item.get("name", ""),
                        industry=item.get("industry", ""),
                        score_type="hot",
                        global_rank=item.get("global_rank", 0),
                        industry_rank=item.get("rank", 0),
                        total_score=item.get("total_score", 0),
                        market_cap=item.get("market_cap", 0),
                        pe_ratio=item.get("pe_ratio", 0),
                        change_pct=item.get("change_pct", 0),
                        dimension_scores=item.get("dimension_scores", {}),
                        mini_trend=item.get("mini_trend", []),
                    )
                    for item in supplemental
                ]
            )
            leaders_from_heatmap = _dedupe_leader_responses(leaders_from_heatmap)[:top_n]

    if leaders_from_heatmap:
        return leaders_from_heatmap

    logger.warning("Heatmap leading_stock unavailable, falling back to LeaderStockScorer")
    industry_names = [
        industry.get("industry_name")
        for industry in hot_industries
        if industry.get("industry_name")
    ]
    leaders = scorer.get_leader_stocks(
        industry_names, top_per_industry=per_industry, score_type="hot"
    )[:top_n]
    result = [
        LeaderStockResponse(
            symbol=item.get("symbol", ""),
            name=item.get("name", ""),
            industry=item.get("industry", ""),
            score_type="hot",
            global_rank=item.get("global_rank", 0),
            industry_rank=item.get("rank", 0),
            total_score=item.get("total_score", 0),
            market_cap=item.get("market_cap", 0),
            pe_ratio=item.get("pe_ratio", 0),
            change_pct=item.get("change_pct", 0),
            dimension_scores=item.get("dimension_scores", {}),
            mini_trend=item.get("mini_trend", []),
        )
        for item in leaders
    ]
    return _dedupe_leader_responses(result)[:top_n]


def _load_leader_stock_list(
    top_n: int,
    top_industries: int,
    per_industry: int,
    list_type: Literal["hot", "core"],
    analyzer=None,
    hot_industries: Optional[list[dict[str, Any]]] = None,
    top_industry_names: Optional[set[str]] = None,
    provider_stock_cache: Optional[dict[str, Any]] = None,
    provider_stock_cache_lock: Optional[threading.Lock] = None,
) -> list[LeaderStockResponse]:
    cache_key = f"leaders:v3:{list_type}:{top_n}:{top_industries}:{per_industry}"
    cached = _get_endpoint_cache(cache_key)
    if cached is not None:
        return cached

    try:
        if analyzer is None or hot_industries is None or top_industry_names is None:
            analyzer, hot_industries, top_industry_names = _build_leader_context(
                top_industries, analyzer=analyzer
            )

        if list_type == "core":
            leaders = _compute_core_leader_stocks(
                analyzer=analyzer,
                hot_industries=hot_industries,
                top_n=top_n,
                per_industry=per_industry,
                provider_stock_cache=provider_stock_cache,
                provider_stock_cache_lock=provider_stock_cache_lock,
            )
        else:
            leaders = _compute_hot_leader_stocks(
                analyzer=analyzer,
                hot_industries=hot_industries,
                top_industry_names=top_industry_names,
                top_n=top_n,
                per_industry=per_industry,
                provider_stock_cache=provider_stock_cache,
                provider_stock_cache_lock=provider_stock_cache_lock,
            )

        if leaders:
            _persist_leader_list_cache(cache_key, list_type, leaders)
            return leaders

        stale = _get_stale_endpoint_cache(cache_key)
        if stale is not None:
            logger.warning(
                "%s leaders empty, using stale cache: %s", list_type.capitalize(), cache_key
            )
            return stale
        return leaders
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error getting %s leader stocks: %s", list_type, exc)
        stale = _get_stale_endpoint_cache(cache_key)
        if stale is not None:
            logger.warning("Using stale cache for %s leaders: %s", list_type, cache_key)
            return stale
        raise


__all__ = [
    "_load_symbol_mini_trend",
    "_attach_leader_mini_trends",
    "_get_endpoint_cache",
    "_set_endpoint_cache",
    "_get_stale_endpoint_cache",
    "_serialize_heatmap_response",
    "_build_hot_industry_rank_responses",
    "_get_stock_cache_keys",
    "_set_parity_cache",
    "_get_parity_cache",
    "_get_stale_parity_cache",
    "_is_fresh_parity_entry",
    "_get_matching_parity_cache",
    "_build_parity_price_data",
    "_build_leader_detail_fallback",
    "_leader_detail_error_status",
    "_extract_leading_stock_symbol_lookup",
    "_collect_hot_leader_candidates",
    "_build_leading_stock_symbol_lookup",
    "_map_industry_etfs",
    "_trim_heatmap_history_payload",
    "_resolve_industry_profile",
    "_get_stock_status_key",
    "_set_stock_build_status",
    "_get_stock_build_status",
    "_load_heatmap_history_from_disk",
    "_persist_heatmap_history_to_disk",
    "_append_heatmap_history",
    "_build_heatmap_response_from_history",
    "_load_live_heatmap_response",
    "_schedule_heatmap_refresh",
    "_resolve_symbol_with_provider",
    "_build_stock_responses",
    "_count_quick_stock_detail_fields",
    "_promote_detail_ready_quick_rows",
    "_load_cached_quick_valuation",
    "_backfill_quick_rows_with_cached_valuation",
    "_build_full_industry_stock_response",
    "_build_quick_industry_stock_response",
    "_coerce_trend_alignment_stock_rows",
    "_load_trend_alignment_stock_rows",
    "_build_trend_summary_from_stock_rows",
    "_should_align_trend_with_stock_rows",
    "_schedule_full_stock_cache_build",
    "_dedupe_leader_responses",
    "_get_or_create_provider",
    "get_industry_analyzer",
    "get_leader_scorer",
    "_build_leader_context",
    "_get_leader_overview_cache_key",
    "_get_leader_provider_stocks_cache_key",
    "_get_leader_snapshot_prewarm_key",
    "_has_leader_board_rows",
    "_build_leader_boards_payload",
    "_prewarm_leader_stock_snapshot",
    "_schedule_leader_stock_snapshot_prewarm",
    "_compute_and_cache_leader_overview",
    "_schedule_leader_overview_build",
    "_load_leader_overview_payload",
    "_get_bootstrap_leader_payload",
    "_hydrate_bootstrap_with_cached_leaders",
    "_persist_leader_list_cache",
    "_load_provider_stocks_for_leaders",
    "_compute_core_leader_stocks",
    "_compute_hot_leader_stocks",
    "_load_leader_stock_list",
]
