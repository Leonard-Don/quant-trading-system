"""
行业分析 API 端点
提供热门行业识别和龙头股遴选功能
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from backend.app.api.v1.endpoints._industry_helpers import (
    _build_industry_events,
    _classify_industry_lifecycle,
    _cosine_similarity,
)
from backend.app.schemas.industry import (
    ClusterResponse,
    HeatmapDataItem,
    HeatmapHistoryItem,
    HeatmapHistoryResponse,
    HeatmapResponse,
    IndustryBootstrapResponse,
    IndustryPreferencesResponse,
    IndustryRankResponse,
    IndustryRotationResponse,
    IndustryStockBuildStatusResponse,
    IndustryTrendResponse,
    LeaderBoardsResponse,
    LeaderDetailResponse,
    LeaderStockResponse,
    StockResponse,
)
from backend.app.services.industry_preferences import (
    industry_preferences_store,
)
from backend.app.services.industry import runtime as industry_runtime
from src.analytics.industry_stock_details import (
    has_meaningful_numeric,
    normalize_symbol,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# Compatibility surface for tests and local debugging that still patch
# helpers on backend.app.api.v1.endpoints.industry directly.
SIX_DIGIT_SYMBOL_PATTERN = industry_runtime.SIX_DIGIT_SYMBOL_PATTERN
_endpoint_cache = industry_runtime._endpoint_cache
_parity_cache = industry_runtime._parity_cache
_stocks_full_build_inflight = industry_runtime._stocks_full_build_inflight
_leading_stock_symbol_lookup_cache = industry_runtime._leading_stock_symbol_lookup_cache
_leading_stock_symbol_lookup_cache_time = industry_runtime._leading_stock_symbol_lookup_cache_time
_heatmap_history = industry_runtime._heatmap_history
_heatmap_history_loaded = industry_runtime._heatmap_history_loaded
_heatmap_history_lock = industry_runtime._heatmap_history_lock
ThreadPoolExecutor = industry_runtime.ThreadPoolExecutor

_INDUSTRY_SERVICE_HELPERS = {
    "_load_symbol_mini_trend": industry_runtime._load_symbol_mini_trend,
    "_attach_leader_mini_trends": industry_runtime._attach_leader_mini_trends,
    "_get_endpoint_cache": industry_runtime._get_endpoint_cache,
    "_set_endpoint_cache": industry_runtime._set_endpoint_cache,
    "_get_stale_endpoint_cache": industry_runtime._get_stale_endpoint_cache,
    "_serialize_heatmap_response": industry_runtime._serialize_heatmap_response,
    "_build_hot_industry_rank_responses": industry_runtime._build_hot_industry_rank_responses,
    "_get_stock_cache_keys": industry_runtime._get_stock_cache_keys,
    "_set_parity_cache": industry_runtime._set_parity_cache,
    "_get_parity_cache": industry_runtime._get_parity_cache,
    "_get_stale_parity_cache": industry_runtime._get_stale_parity_cache,
    "_is_fresh_parity_entry": industry_runtime._is_fresh_parity_entry,
    "_get_matching_parity_cache": industry_runtime._get_matching_parity_cache,
    "_build_parity_price_data": industry_runtime._build_parity_price_data,
    "_build_leader_detail_fallback": industry_runtime._build_leader_detail_fallback,
    "_leader_detail_error_status": industry_runtime._leader_detail_error_status,
    "_extract_leading_stock_symbol_lookup": industry_runtime._extract_leading_stock_symbol_lookup,
    "_collect_hot_leader_candidates": industry_runtime._collect_hot_leader_candidates,
    "_build_leading_stock_symbol_lookup": industry_runtime._build_leading_stock_symbol_lookup,
    "_map_industry_etfs": industry_runtime._map_industry_etfs,
    "_trim_heatmap_history_payload": industry_runtime._trim_heatmap_history_payload,
    "_resolve_industry_profile": industry_runtime._resolve_industry_profile,
    "_get_stock_status_key": industry_runtime._get_stock_status_key,
    "_set_stock_build_status": industry_runtime._set_stock_build_status,
    "_get_stock_build_status": industry_runtime._get_stock_build_status,
    "_load_heatmap_history_from_disk": industry_runtime._load_heatmap_history_from_disk,
    "_persist_heatmap_history_to_disk": industry_runtime._persist_heatmap_history_to_disk,
    "_append_heatmap_history": industry_runtime._append_heatmap_history,
    "_build_heatmap_response_from_history": industry_runtime._build_heatmap_response_from_history,
    "_load_live_heatmap_response": industry_runtime._load_live_heatmap_response,
    "_schedule_heatmap_refresh": industry_runtime._schedule_heatmap_refresh,
    "_resolve_symbol_with_provider": industry_runtime._resolve_symbol_with_provider,
    "_build_stock_responses": industry_runtime._build_stock_responses,
    "_count_quick_stock_detail_fields": industry_runtime._count_quick_stock_detail_fields,
    "_promote_detail_ready_quick_rows": industry_runtime._promote_detail_ready_quick_rows,
    "_load_cached_quick_valuation": industry_runtime._load_cached_quick_valuation,
    "_backfill_quick_rows_with_cached_valuation": industry_runtime._backfill_quick_rows_with_cached_valuation,
    "_build_full_industry_stock_response": industry_runtime._build_full_industry_stock_response,
    "_build_quick_industry_stock_response": industry_runtime._build_quick_industry_stock_response,
    "_coerce_trend_alignment_stock_rows": industry_runtime._coerce_trend_alignment_stock_rows,
    "_load_trend_alignment_stock_rows": industry_runtime._load_trend_alignment_stock_rows,
    "_build_trend_summary_from_stock_rows": industry_runtime._build_trend_summary_from_stock_rows,
    "_should_align_trend_with_stock_rows": industry_runtime._should_align_trend_with_stock_rows,
    "_schedule_full_stock_cache_build": industry_runtime._schedule_full_stock_cache_build,
    "_dedupe_leader_responses": industry_runtime._dedupe_leader_responses,
    "_get_or_create_provider": industry_runtime._get_or_create_provider,
    "get_industry_analyzer": industry_runtime.get_industry_analyzer,
    "get_leader_scorer": industry_runtime.get_leader_scorer,
    "_build_leader_context": industry_runtime._build_leader_context,
    "_get_leader_overview_cache_key": industry_runtime._get_leader_overview_cache_key,
    "_get_leader_provider_stocks_cache_key": industry_runtime._get_leader_provider_stocks_cache_key,
    "_get_leader_snapshot_prewarm_key": industry_runtime._get_leader_snapshot_prewarm_key,
    "_has_leader_board_rows": industry_runtime._has_leader_board_rows,
    "_build_leader_boards_payload": industry_runtime._build_leader_boards_payload,
    "_prewarm_leader_stock_snapshot": industry_runtime._prewarm_leader_stock_snapshot,
    "_schedule_leader_stock_snapshot_prewarm": industry_runtime._schedule_leader_stock_snapshot_prewarm,
    "_compute_and_cache_leader_overview": industry_runtime._compute_and_cache_leader_overview,
    "_schedule_leader_overview_build": industry_runtime._schedule_leader_overview_build,
    "_load_leader_overview_payload": industry_runtime._load_leader_overview_payload,
    "_get_bootstrap_leader_payload": industry_runtime._get_bootstrap_leader_payload,
    "_hydrate_bootstrap_with_cached_leaders": industry_runtime._hydrate_bootstrap_with_cached_leaders,
    "_persist_leader_list_cache": industry_runtime._persist_leader_list_cache,
    "_load_provider_stocks_for_leaders": industry_runtime._load_provider_stocks_for_leaders,
    "_compute_core_leader_stocks": industry_runtime._compute_core_leader_stocks,
    "_compute_hot_leader_stocks": industry_runtime._compute_hot_leader_stocks,
    "_load_leader_stock_list": industry_runtime._load_leader_stock_list,
}
_INDUSTRY_WRAPPERS: dict[str, Any] = {}


def _sync_industry_runtime_state() -> None:
    for state_name in (
        "SIX_DIGIT_SYMBOL_PATTERN",
        "_endpoint_cache",
        "_parity_cache",
        "_stocks_full_build_inflight",
        "_leading_stock_symbol_lookup_cache",
        "_leading_stock_symbol_lookup_cache_time",
        "_heatmap_history",
        "_heatmap_history_loaded",
        "_heatmap_history_lock",
        "ThreadPoolExecutor",
    ):
        setattr(industry_runtime, state_name, globals()[state_name])

    for helper_name, original in _INDUSTRY_SERVICE_HELPERS.items():
        current = globals().get(helper_name, original)
        wrapper = _INDUSTRY_WRAPPERS.get(helper_name)
        setattr(industry_runtime, helper_name, original if current is wrapper else current)


def _call_industry_helper(helper_name: str, *args, **kwargs):
    _sync_industry_runtime_state()
    return _INDUSTRY_SERVICE_HELPERS[helper_name](*args, **kwargs)


def _load_symbol_mini_trend(*args, **kwargs):
    return _call_industry_helper("_load_symbol_mini_trend", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_symbol_mini_trend"] = _load_symbol_mini_trend


def _attach_leader_mini_trends(*args, **kwargs):
    return _call_industry_helper("_attach_leader_mini_trends", *args, **kwargs)


_INDUSTRY_WRAPPERS["_attach_leader_mini_trends"] = _attach_leader_mini_trends


def _get_endpoint_cache(*args, **kwargs):
    return _call_industry_helper("_get_endpoint_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_endpoint_cache"] = _get_endpoint_cache


def _set_endpoint_cache(*args, **kwargs):
    return _call_industry_helper("_set_endpoint_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_set_endpoint_cache"] = _set_endpoint_cache


def _get_stale_endpoint_cache(*args, **kwargs):
    return _call_industry_helper("_get_stale_endpoint_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_stale_endpoint_cache"] = _get_stale_endpoint_cache


def _serialize_heatmap_response(*args, **kwargs):
    return _call_industry_helper("_serialize_heatmap_response", *args, **kwargs)


_INDUSTRY_WRAPPERS["_serialize_heatmap_response"] = _serialize_heatmap_response


def _build_hot_industry_rank_responses(*args, **kwargs):
    return _call_industry_helper("_build_hot_industry_rank_responses", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_hot_industry_rank_responses"] = _build_hot_industry_rank_responses


def _get_stock_cache_keys(*args, **kwargs):
    return _call_industry_helper("_get_stock_cache_keys", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_stock_cache_keys"] = _get_stock_cache_keys


def _set_parity_cache(*args, **kwargs):
    return _call_industry_helper("_set_parity_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_set_parity_cache"] = _set_parity_cache


def _get_parity_cache(*args, **kwargs):
    return _call_industry_helper("_get_parity_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_parity_cache"] = _get_parity_cache


def _get_stale_parity_cache(*args, **kwargs):
    return _call_industry_helper("_get_stale_parity_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_stale_parity_cache"] = _get_stale_parity_cache


def _is_fresh_parity_entry(*args, **kwargs):
    return _call_industry_helper("_is_fresh_parity_entry", *args, **kwargs)


_INDUSTRY_WRAPPERS["_is_fresh_parity_entry"] = _is_fresh_parity_entry


def _get_matching_parity_cache(*args, **kwargs):
    return _call_industry_helper("_get_matching_parity_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_matching_parity_cache"] = _get_matching_parity_cache


def _build_parity_price_data(*args, **kwargs):
    return _call_industry_helper("_build_parity_price_data", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_parity_price_data"] = _build_parity_price_data


def _build_leader_detail_fallback(*args, **kwargs):
    return _call_industry_helper("_build_leader_detail_fallback", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_leader_detail_fallback"] = _build_leader_detail_fallback


def _leader_detail_error_status(*args, **kwargs):
    return _call_industry_helper("_leader_detail_error_status", *args, **kwargs)


_INDUSTRY_WRAPPERS["_leader_detail_error_status"] = _leader_detail_error_status


def _extract_leading_stock_symbol_lookup(*args, **kwargs):
    return _call_industry_helper("_extract_leading_stock_symbol_lookup", *args, **kwargs)


_INDUSTRY_WRAPPERS["_extract_leading_stock_symbol_lookup"] = _extract_leading_stock_symbol_lookup


def _collect_hot_leader_candidates(*args, **kwargs):
    return _call_industry_helper("_collect_hot_leader_candidates", *args, **kwargs)


_INDUSTRY_WRAPPERS["_collect_hot_leader_candidates"] = _collect_hot_leader_candidates


def _build_leading_stock_symbol_lookup(*args, **kwargs):
    return _call_industry_helper("_build_leading_stock_symbol_lookup", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_leading_stock_symbol_lookup"] = _build_leading_stock_symbol_lookup


def _map_industry_etfs(*args, **kwargs):
    return _call_industry_helper("_map_industry_etfs", *args, **kwargs)


_INDUSTRY_WRAPPERS["_map_industry_etfs"] = _map_industry_etfs


def _trim_heatmap_history_payload(*args, **kwargs):
    return _call_industry_helper("_trim_heatmap_history_payload", *args, **kwargs)


_INDUSTRY_WRAPPERS["_trim_heatmap_history_payload"] = _trim_heatmap_history_payload


def _resolve_industry_profile(*args, **kwargs):
    return _call_industry_helper("_resolve_industry_profile", *args, **kwargs)


_INDUSTRY_WRAPPERS["_resolve_industry_profile"] = _resolve_industry_profile


def _get_stock_status_key(*args, **kwargs):
    return _call_industry_helper("_get_stock_status_key", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_stock_status_key"] = _get_stock_status_key


def _set_stock_build_status(*args, **kwargs):
    return _call_industry_helper("_set_stock_build_status", *args, **kwargs)


_INDUSTRY_WRAPPERS["_set_stock_build_status"] = _set_stock_build_status


def _get_stock_build_status(*args, **kwargs):
    return _call_industry_helper("_get_stock_build_status", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_stock_build_status"] = _get_stock_build_status


def _load_heatmap_history_from_disk(*args, **kwargs):
    return _call_industry_helper("_load_heatmap_history_from_disk", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_heatmap_history_from_disk"] = _load_heatmap_history_from_disk


def _persist_heatmap_history_to_disk(*args, **kwargs):
    return _call_industry_helper("_persist_heatmap_history_to_disk", *args, **kwargs)


_INDUSTRY_WRAPPERS["_persist_heatmap_history_to_disk"] = _persist_heatmap_history_to_disk


def _append_heatmap_history(*args, **kwargs):
    return _call_industry_helper("_append_heatmap_history", *args, **kwargs)


_INDUSTRY_WRAPPERS["_append_heatmap_history"] = _append_heatmap_history


def _build_heatmap_response_from_history(*args, **kwargs):
    return _call_industry_helper("_build_heatmap_response_from_history", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_heatmap_response_from_history"] = _build_heatmap_response_from_history


def _load_live_heatmap_response(*args, **kwargs):
    return _call_industry_helper("_load_live_heatmap_response", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_live_heatmap_response"] = _load_live_heatmap_response


def _schedule_heatmap_refresh(*args, **kwargs):
    return _call_industry_helper("_schedule_heatmap_refresh", *args, **kwargs)


_INDUSTRY_WRAPPERS["_schedule_heatmap_refresh"] = _schedule_heatmap_refresh


def _resolve_symbol_with_provider(*args, **kwargs):
    return _call_industry_helper("_resolve_symbol_with_provider", *args, **kwargs)


_INDUSTRY_WRAPPERS["_resolve_symbol_with_provider"] = _resolve_symbol_with_provider


def _build_stock_responses(*args, **kwargs):
    return _call_industry_helper("_build_stock_responses", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_stock_responses"] = _build_stock_responses


def _count_quick_stock_detail_fields(*args, **kwargs):
    return _call_industry_helper("_count_quick_stock_detail_fields", *args, **kwargs)


_INDUSTRY_WRAPPERS["_count_quick_stock_detail_fields"] = _count_quick_stock_detail_fields


def _promote_detail_ready_quick_rows(*args, **kwargs):
    return _call_industry_helper("_promote_detail_ready_quick_rows", *args, **kwargs)


_INDUSTRY_WRAPPERS["_promote_detail_ready_quick_rows"] = _promote_detail_ready_quick_rows


def _load_cached_quick_valuation(*args, **kwargs):
    return _call_industry_helper("_load_cached_quick_valuation", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_cached_quick_valuation"] = _load_cached_quick_valuation


def _backfill_quick_rows_with_cached_valuation(*args, **kwargs):
    return _call_industry_helper("_backfill_quick_rows_with_cached_valuation", *args, **kwargs)


_INDUSTRY_WRAPPERS["_backfill_quick_rows_with_cached_valuation"] = (
    _backfill_quick_rows_with_cached_valuation
)


def _build_full_industry_stock_response(*args, **kwargs):
    return _call_industry_helper("_build_full_industry_stock_response", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_full_industry_stock_response"] = _build_full_industry_stock_response


def _build_quick_industry_stock_response(*args, **kwargs):
    return _call_industry_helper("_build_quick_industry_stock_response", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_quick_industry_stock_response"] = _build_quick_industry_stock_response


def _coerce_trend_alignment_stock_rows(*args, **kwargs):
    return _call_industry_helper("_coerce_trend_alignment_stock_rows", *args, **kwargs)


_INDUSTRY_WRAPPERS["_coerce_trend_alignment_stock_rows"] = _coerce_trend_alignment_stock_rows


def _load_trend_alignment_stock_rows(*args, **kwargs):
    return _call_industry_helper("_load_trend_alignment_stock_rows", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_trend_alignment_stock_rows"] = _load_trend_alignment_stock_rows


def _build_trend_summary_from_stock_rows(*args, **kwargs):
    return _call_industry_helper("_build_trend_summary_from_stock_rows", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_trend_summary_from_stock_rows"] = _build_trend_summary_from_stock_rows


def _should_align_trend_with_stock_rows(*args, **kwargs):
    return _call_industry_helper("_should_align_trend_with_stock_rows", *args, **kwargs)


_INDUSTRY_WRAPPERS["_should_align_trend_with_stock_rows"] = _should_align_trend_with_stock_rows


def _schedule_full_stock_cache_build(*args, **kwargs):
    return _call_industry_helper("_schedule_full_stock_cache_build", *args, **kwargs)


_INDUSTRY_WRAPPERS["_schedule_full_stock_cache_build"] = _schedule_full_stock_cache_build


def _dedupe_leader_responses(*args, **kwargs):
    return _call_industry_helper("_dedupe_leader_responses", *args, **kwargs)


_INDUSTRY_WRAPPERS["_dedupe_leader_responses"] = _dedupe_leader_responses


def _get_or_create_provider(*args, **kwargs):
    return _call_industry_helper("_get_or_create_provider", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_or_create_provider"] = _get_or_create_provider


def get_industry_analyzer(*args, **kwargs):
    return _call_industry_helper("get_industry_analyzer", *args, **kwargs)


_INDUSTRY_WRAPPERS["get_industry_analyzer"] = get_industry_analyzer


def get_leader_scorer(*args, **kwargs):
    return _call_industry_helper("get_leader_scorer", *args, **kwargs)


_INDUSTRY_WRAPPERS["get_leader_scorer"] = get_leader_scorer


def _build_leader_context(*args, **kwargs):
    return _call_industry_helper("_build_leader_context", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_leader_context"] = _build_leader_context


def _get_leader_overview_cache_key(*args, **kwargs):
    return _call_industry_helper("_get_leader_overview_cache_key", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_leader_overview_cache_key"] = _get_leader_overview_cache_key


def _get_leader_provider_stocks_cache_key(*args, **kwargs):
    return _call_industry_helper("_get_leader_provider_stocks_cache_key", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_leader_provider_stocks_cache_key"] = _get_leader_provider_stocks_cache_key


def _get_leader_snapshot_prewarm_key(*args, **kwargs):
    return _call_industry_helper("_get_leader_snapshot_prewarm_key", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_leader_snapshot_prewarm_key"] = _get_leader_snapshot_prewarm_key


def _has_leader_board_rows(*args, **kwargs):
    return _call_industry_helper("_has_leader_board_rows", *args, **kwargs)


_INDUSTRY_WRAPPERS["_has_leader_board_rows"] = _has_leader_board_rows


def _build_leader_boards_payload(*args, **kwargs):
    return _call_industry_helper("_build_leader_boards_payload", *args, **kwargs)


_INDUSTRY_WRAPPERS["_build_leader_boards_payload"] = _build_leader_boards_payload


def _prewarm_leader_stock_snapshot(*args, **kwargs):
    return _call_industry_helper("_prewarm_leader_stock_snapshot", *args, **kwargs)


_INDUSTRY_WRAPPERS["_prewarm_leader_stock_snapshot"] = _prewarm_leader_stock_snapshot


def _schedule_leader_stock_snapshot_prewarm(*args, **kwargs):
    return _call_industry_helper("_schedule_leader_stock_snapshot_prewarm", *args, **kwargs)


_INDUSTRY_WRAPPERS["_schedule_leader_stock_snapshot_prewarm"] = (
    _schedule_leader_stock_snapshot_prewarm
)


def _compute_and_cache_leader_overview(*args, **kwargs):
    return _call_industry_helper("_compute_and_cache_leader_overview", *args, **kwargs)


_INDUSTRY_WRAPPERS["_compute_and_cache_leader_overview"] = _compute_and_cache_leader_overview


def _schedule_leader_overview_build(*args, **kwargs):
    return _call_industry_helper("_schedule_leader_overview_build", *args, **kwargs)


_INDUSTRY_WRAPPERS["_schedule_leader_overview_build"] = _schedule_leader_overview_build


def _load_leader_overview_payload(*args, **kwargs):
    return _call_industry_helper("_load_leader_overview_payload", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_leader_overview_payload"] = _load_leader_overview_payload


def _get_bootstrap_leader_payload(*args, **kwargs):
    return _call_industry_helper("_get_bootstrap_leader_payload", *args, **kwargs)


_INDUSTRY_WRAPPERS["_get_bootstrap_leader_payload"] = _get_bootstrap_leader_payload


def _hydrate_bootstrap_with_cached_leaders(*args, **kwargs):
    return _call_industry_helper("_hydrate_bootstrap_with_cached_leaders", *args, **kwargs)


_INDUSTRY_WRAPPERS["_hydrate_bootstrap_with_cached_leaders"] = (
    _hydrate_bootstrap_with_cached_leaders
)


def _persist_leader_list_cache(*args, **kwargs):
    return _call_industry_helper("_persist_leader_list_cache", *args, **kwargs)


_INDUSTRY_WRAPPERS["_persist_leader_list_cache"] = _persist_leader_list_cache


def _load_provider_stocks_for_leaders(*args, **kwargs):
    return _call_industry_helper("_load_provider_stocks_for_leaders", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_provider_stocks_for_leaders"] = _load_provider_stocks_for_leaders


def _compute_core_leader_stocks(*args, **kwargs):
    return _call_industry_helper("_compute_core_leader_stocks", *args, **kwargs)


_INDUSTRY_WRAPPERS["_compute_core_leader_stocks"] = _compute_core_leader_stocks


def _compute_hot_leader_stocks(*args, **kwargs):
    return _call_industry_helper("_compute_hot_leader_stocks", *args, **kwargs)


_INDUSTRY_WRAPPERS["_compute_hot_leader_stocks"] = _compute_hot_leader_stocks


def _load_leader_stock_list(*args, **kwargs):
    return _call_industry_helper("_load_leader_stock_list", *args, **kwargs)


_INDUSTRY_WRAPPERS["_load_leader_stock_list"] = _load_leader_stock_list


@router.get("/industries/hot", response_model=list[IndustryRankResponse])
def get_hot_industries(
    top_n: int = Query(10, ge=1, le=50, description="返回前N个热门行业"),
    lookback_days: int = Query(5, ge=1, le=30, description="回看周期（天）"),
    sort_by: str = Query(
        "total_score",
        description="排序字段: total_score, change_pct, money_flow, industry_volatility",
    ),
    order: str = Query("desc", description="排序顺序: desc, asc"),
) -> list[IndustryRankResponse]:
    """
    获取热门行业排名

    基于动量、资金流向和成交量变化综合评分，识别当前市场关注度高的行业。

    - **top_n**: 返回排名前 N 的行业
    - **lookback_days**: 用于计算动量和资金流向的回看周期
    - **sort_by**: 排序字段 (total_score, change_pct, money_flow, industry_volatility)
    - **order**: 排序顺序 (desc, asc)
    """
    try:
        # 端点级缓存
        cache_key = f"hot:v3:{top_n}:{lookback_days}:{sort_by}:{order}"
        cached = _get_endpoint_cache(cache_key)
        if cached is not None:
            return cached

        analyzer = get_industry_analyzer()
        ascending = order.lower() == "asc"
        hot_industries = analyzer.rank_industries(
            top_n=top_n, sort_by=sort_by, ascending=ascending, lookback_days=lookback_days
        )
        result = _build_hot_industry_rank_responses(analyzer, hot_industries)
        _set_endpoint_cache(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting hot industries: {e}")
        stale = _get_stale_endpoint_cache(cache_key)
        if stale is not None:
            logger.warning(f"Using stale cache for hot industries: {cache_key}")
            return stale
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/industries/{industry_name}/stocks", response_model=list[StockResponse])
def get_industry_stocks(
    industry_name: str, top_n: int = Query(20, ge=1, le=100, description="返回前N只股票")
) -> list[StockResponse]:
    """
    获取行业成分股及排名

    返回指定行业内按综合得分排名的股票列表。

    - **industry_name**: 行业名称（如 "电子"、"医药生物"）
    - **top_n**: 返回排名前 N 的股票
    """
    quick_cache_key, full_cache_key = _get_stock_cache_keys(industry_name, top_n)
    try:
        full_cached = _get_endpoint_cache(full_cache_key)
        if full_cached is not None:
            return full_cached

        quick_cached = _get_endpoint_cache(quick_cache_key)
        if quick_cached is not None:
            _schedule_full_stock_cache_build(industry_name, top_n)
            return quick_cached

        provider = _get_or_create_provider()
        cached_provider_rows = []
        cached_stock_loader = getattr(provider, "get_cached_stock_list_by_industry", None)
        if callable(cached_stock_loader):
            try:
                try:
                    cached_provider_rows = cached_stock_loader(
                        industry_name,
                        include_market_cap_lookup=False,
                        allow_stale=True,
                    )
                except TypeError:
                    cached_provider_rows = cached_stock_loader(industry_name)
            except Exception as e:
                logger.warning(f"Failed to load cached industry stocks for {industry_name}: {e}")

        if cached_provider_rows:
            quick_result = _build_quick_industry_stock_response(
                industry_name,
                top_n,
                cached_provider_rows,
                provider=provider,
                enable_valuation_backfill=False,
            )
            _set_endpoint_cache(quick_cache_key, quick_result)
            _schedule_full_stock_cache_build(industry_name, top_n)
            return quick_result

        provider_stocks = provider.get_stock_list_by_industry(industry_name)

        # 首次请求优先返回 provider 的原始行业成分股，避免评分排序和估值回填阻塞首屏。
        if provider_stocks:
            quick_result = _build_quick_industry_stock_response(
                industry_name,
                top_n,
                provider_stocks,
                provider=provider,
                enable_valuation_backfill=True,
            )
            _set_endpoint_cache(quick_cache_key, quick_result)
            _schedule_full_stock_cache_build(industry_name, top_n)
            return quick_result

        # provider 明细为空时，同步退回完整版构建逻辑，避免接口直接空掉。
        full_result = _build_full_industry_stock_response(industry_name, top_n, provider=provider)
        _set_endpoint_cache(full_cache_key, full_result)
        return full_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting industry stocks: {e}")
        stale = _get_stale_endpoint_cache(full_cache_key)
        if stale is None:
            stale = _get_stale_endpoint_cache(quick_cache_key)
        if stale is not None:
            logger.warning(
                f"Using stale cache for industry stocks: {full_cache_key} / {quick_cache_key}"
            )
            return stale
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/industries/{industry_name}/stocks/status", response_model=IndustryStockBuildStatusResponse
)
def get_industry_stock_build_status(
    industry_name: str,
    top_n: int = Query(20, ge=1, le=100, description="返回前N只股票"),
) -> IndustryStockBuildStatusResponse:
    status = _get_stock_build_status(industry_name, top_n)
    return IndustryStockBuildStatusResponse(**status)


@router.get("/industries/{industry_name}/stocks/stream")
async def stream_industry_stock_build_status(
    industry_name: str,
    top_n: int = Query(20, ge=1, le=100, description="返回前N只股票"),
):
    async def event_generator():
        emitted = None
        started_at = time.time()
        while True:
            status = _get_stock_build_status(industry_name, top_n)
            payload = json.dumps(status, ensure_ascii=False)
            if payload != emitted:
                emitted = payload
                yield f"data: {payload}\n\n"

            if status.get("status") in {"ready", "failed"}:
                break
            if (time.time() - started_at) > 30:
                break
            await __import__("asyncio").sleep(0.75)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/industries/heatmap", response_model=HeatmapResponse)
def get_industry_heatmap(
    days: int = Query(5, ge=1, le=90, description="分析周期（天）"),
) -> HeatmapResponse:
    """
    获取行业热力图数据

    返回所有行业的涨跌幅和市值数据，用于渲染热力图可视化。
    """
    try:
        # 端点级缓存
        cache_key = f"heatmap:v2:{days}"
        cached = _get_endpoint_cache(cache_key)
        if cached is not None:
            return cached

        history_result = _build_heatmap_response_from_history(days)
        if history_result is not None:
            _schedule_heatmap_refresh(days)
            return history_result

        return _load_live_heatmap_response(days)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting industry heatmap: {e}")
        stale = _get_stale_endpoint_cache(cache_key)
        if stale is not None:
            logger.warning(f"Using stale cache for heatmap: {cache_key}")
            return stale
        history_result = _build_heatmap_response_from_history(days)
        if history_result is not None:
            logger.warning(f"Using heatmap history snapshot for {cache_key}")
            _schedule_heatmap_refresh(days)
            return history_result
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/industries/heatmap/history", response_model=HeatmapHistoryResponse)
def get_industry_heatmap_history(
    limit: int = Query(10, ge=1, le=50, description="返回快照数量"),
    days: Optional[int] = Query(None, ge=1, le=90, description="按周期过滤"),
) -> HeatmapHistoryResponse:
    """
    获取行业热力图历史快照。

    用于行业热度模块的历史回放。当前返回服务端近期保留的快照窗口。
    """
    _load_heatmap_history_from_disk()
    with _heatmap_history_lock:
        items = list(_heatmap_history)

    if days is not None:
        items = [item for item in items if int(item.get("days", 0) or 0) == days]

    history_items = [
        HeatmapHistoryItem(
            snapshot_id=item.get("snapshot_id", ""),
            days=item.get("days", 0),
            captured_at=item.get("captured_at", ""),
            update_time=item.get("update_time", ""),
            max_value=item.get("max_value", 0),
            min_value=item.get("min_value", 0),
            industries=[
                HeatmapDataItem(**industry_item) for industry_item in item.get("industries", [])
            ],
        )
        for item in items[:limit]
    ]
    return HeatmapHistoryResponse(items=history_items)


@router.get("/preferences", response_model=IndustryPreferencesResponse)
def get_industry_preferences(request: Request) -> IndustryPreferencesResponse:
    profile_id = _resolve_industry_profile(request)
    return IndustryPreferencesResponse(
        **industry_preferences_store.get_preferences(profile_id=profile_id)
    )


@router.put("/preferences", response_model=IndustryPreferencesResponse)
def update_industry_preferences(
    payload: IndustryPreferencesResponse, request: Request
) -> IndustryPreferencesResponse:
    profile_id = _resolve_industry_profile(request)
    data = industry_preferences_store.update_preferences(
        payload.model_dump(), profile_id=profile_id
    )
    return IndustryPreferencesResponse(**data)


@router.get("/preferences/export")
def export_industry_preferences(request: Request):
    profile_id = _resolve_industry_profile(request)
    return JSONResponse(content=industry_preferences_store.get_preferences(profile_id=profile_id))


@router.post("/preferences/import", response_model=IndustryPreferencesResponse)
def import_industry_preferences(
    payload: IndustryPreferencesResponse, request: Request
) -> IndustryPreferencesResponse:
    profile_id = _resolve_industry_profile(request)
    data = industry_preferences_store.update_preferences(
        payload.model_dump(), profile_id=profile_id
    )
    return IndustryPreferencesResponse(**data)


@router.get("/industries/{industry_name}/trend", response_model=IndustryTrendResponse)
def get_industry_trend(
    industry_name: str, days: int = Query(30, ge=1, le=90, description="分析周期（天）")
) -> IndustryTrendResponse:
    """
    获取行业趋势分析

    返回指定行业的详细趋势分析，包括涨幅/跌幅前5的股票。
    """
    cache_key = f"trend:v5:{industry_name}:{days}"
    try:
        # 1. 检查有效缓存
        cached = _get_endpoint_cache(cache_key)
        if cached is not None:
            return cached

        analyzer = get_industry_analyzer()
        trend_data = analyzer.get_industry_trend(industry_name, days=days)

        if "error" in trend_data:
            raise HTTPException(status_code=404, detail=trend_data["error"])

        result = IndustryTrendResponse(
            industry_name=trend_data.get("industry_name", ""),
            stock_count=trend_data.get("stock_count", 0),
            expected_stock_count=trend_data.get("expected_stock_count", 0),
            total_market_cap=trend_data.get("total_market_cap", 0),
            avg_pe=trend_data.get("avg_pe", 0),
            industry_volatility=trend_data.get("industry_volatility", 0),
            industry_volatility_source=trend_data.get("industry_volatility_source", "unavailable"),
            period_days=trend_data.get("period_days", days),
            period_change_pct=trend_data.get("period_change_pct", 0),
            period_money_flow=trend_data.get("period_money_flow", 0),
            top_gainers=trend_data.get("top_gainers", []),
            top_losers=trend_data.get("top_losers", []),
            rise_count=trend_data.get("rise_count", 0),
            fall_count=trend_data.get("fall_count", 0),
            flat_count=trend_data.get("flat_count", 0),
            stock_coverage_ratio=trend_data.get("stock_coverage_ratio", 0),
            change_coverage_ratio=trend_data.get("change_coverage_ratio", 0),
            market_cap_coverage_ratio=trend_data.get("market_cap_coverage_ratio", 0),
            pe_coverage_ratio=trend_data.get("pe_coverage_ratio", 0),
            total_market_cap_fallback=trend_data.get("total_market_cap_fallback", False),
            avg_pe_fallback=trend_data.get("avg_pe_fallback", False),
            market_cap_source=trend_data.get("market_cap_source", "unknown"),
            valuation_source=trend_data.get("valuation_source", "unavailable"),
            valuation_quality=trend_data.get("valuation_quality", "unavailable"),
            trend_series=trend_data.get("trend_series", []),
            degraded=trend_data.get("degraded", False),
            note=trend_data.get("note"),
            update_time=trend_data.get("update_time", ""),
        )

        should_attempt_alignment = result.degraded or (
            result.expected_stock_count > 0
            and result.stock_count
            > max(result.expected_stock_count * 2, result.expected_stock_count + 15)
        )
        if should_attempt_alignment:
            provider = getattr(analyzer, "provider", None) or _get_or_create_provider()
            aligned_stock_rows = _load_trend_alignment_stock_rows(
                industry_name,
                result.expected_stock_count,
                provider=provider,
            )
            if _should_align_trend_with_stock_rows(result.model_dump(), aligned_stock_rows):
                aligned_summary = _build_trend_summary_from_stock_rows(
                    aligned_stock_rows,
                    expected_count=result.expected_stock_count,
                    fallback_total_market_cap=result.total_market_cap,
                    fallback_avg_pe=result.avg_pe,
                )
                aligned_payload = result.model_dump()
                aligned_payload.update(aligned_summary)
                result = IndustryTrendResponse(**aligned_payload)

        # 2. 如果当前数据降级，尝试使用健康的过期缓存兜底
        if result.degraded:
            stale = _get_stale_endpoint_cache(cache_key)
            if stale is not None and not getattr(stale, "degraded", True):
                logger.warning(
                    f"Trend data degraded for {industry_name}, returning healthy stale cache"
                )
                return stale

        # 3. 更新缓存（包含健康数据或只能接受的降级数据）
        _set_endpoint_cache(cache_key, result)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting industry trend: {e}")
        stale = _get_stale_endpoint_cache(cache_key)
        if stale is not None:
            logger.warning(f"Using stale cache for trend: {cache_key}")
            return stale
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/industries/clusters", response_model=ClusterResponse)
def get_industry_clusters(
    n_clusters: int = Query(4, ge=2, le=10, description="聚类数量"),
) -> ClusterResponse:
    """
    获取行业聚类分析

    使用 K-Means 算法将行业聚类为热门组和非热门组。
    """
    try:
        analyzer = get_industry_analyzer()
        cluster_data = analyzer.cluster_hot_industries(n_clusters=n_clusters)

        return ClusterResponse(
            clusters=cluster_data.get("clusters", {}),
            hot_cluster=cluster_data.get("hot_cluster", -1),
            cluster_stats=cluster_data.get("cluster_stats", {}),
            points=cluster_data.get("points", []),
            selected_cluster_count=cluster_data.get("selected_cluster_count", n_clusters),
            silhouette_score=cluster_data.get("silhouette_score"),
            cluster_candidates=cluster_data.get("cluster_candidates", {}),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting industry clusters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/industries/rotation", response_model=IndustryRotationResponse)
def get_industry_rotation(
    industries: str = Query(..., description="行业名称列表，逗号分隔"),
    periods: Optional[str] = Query(None, description="统计周期列表，逗号分隔，如 1,5,20"),
) -> IndustryRotationResponse:
    """
    获取行业轮动对比数据

    比较多个行业在不同时间周期的涨跌幅表现。

    - **industries**: 行业名称列表，用逗号分隔（如2-5个）
    """
    try:
        industry_list = [i.strip() for i in industries.split(",") if i.strip()]
        if len(industry_list) < 2:
            raise HTTPException(status_code=400, detail="至少需要选择 2 个行业进行对比")
        if len(industry_list) > 5:
            industry_list = industry_list[:5]

        requested_periods = None
        if periods:
            requested_periods = []
            for raw in periods.split(","):
                raw_value = raw.strip()
                if not raw_value:
                    continue
                try:
                    requested_periods.append(max(int(raw_value), 1))
                except ValueError as exc:
                    raise HTTPException(
                        status_code=400, detail=f"非法周期参数: {raw_value}"
                    ) from exc

        analyzer = get_industry_analyzer()
        rotation_data = analyzer.get_industry_rotation(industry_list, requested_periods)

        if "error" in rotation_data:
            raise HTTPException(status_code=500, detail=rotation_data["error"])

        return IndustryRotationResponse(
            industries=rotation_data.get("industries", []),
            periods=rotation_data.get("periods", []),
            data=rotation_data.get("data", []),
            update_time=rotation_data.get("update_time", ""),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting industry rotation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/industries/intelligence", summary="行业生命周期、ETF 映射与事件日历")
def get_industry_intelligence(
    top_n: int = Query(12, ge=1, le=30, description="分析前 N 个热门行业"),
    lookback_days: int = Query(5, ge=1, le=30, description="热度回看周期"),
):
    cache_key = f"industry_intelligence:v1:{top_n}:{lookback_days}"
    cached = _get_endpoint_cache(cache_key)
    if cached is not None:
        return cached
    try:
        analyzer = get_industry_analyzer()
        rows = analyzer.rank_industries(
            top_n=top_n,
            sort_by="total_score",
            ascending=False,
            lookback_days=lookback_days,
        )
        industries = []
        for row in rows:
            industry_name = row.get("industry_name", "")
            industries.append(
                {
                    "industry_name": industry_name,
                    "rank": row.get("rank", 0),
                    "score": row.get("score", row.get("total_score", 0)),
                    "change_pct": row.get("change_pct", 0),
                    "money_flow": row.get("money_flow", 0),
                    "lifecycle": _classify_industry_lifecycle(row),
                    "etf_mapping": _map_industry_etfs(industry_name),
                    "event_calendar": _build_industry_events(industry_name),
                }
            )
        result = {
            "success": True,
            "data": {
                "lookback_days": lookback_days,
                "industries": industries,
                "generated_at": datetime.now().isoformat(),
            },
        }
        _set_endpoint_cache(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Error building industry intelligence: {e}", exc_info=True)
        stale = _get_stale_endpoint_cache(cache_key)
        if stale is not None:
            return stale
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/industries/network", summary="行业相关性网络图")
def get_industry_network(
    top_n: int = Query(18, ge=4, le=50, description="网络节点数量"),
    lookback_days: int = Query(5, ge=1, le=30, description="热度回看周期"),
    min_similarity: float = Query(0.92, ge=0.0, le=1.0, description="最小相似度"),
):
    cache_key = f"industry_network:v1:{top_n}:{lookback_days}:{min_similarity}"
    cached = _get_endpoint_cache(cache_key)
    if cached is not None:
        return cached
    try:
        analyzer = get_industry_analyzer()
        rows = analyzer.rank_industries(
            top_n=top_n,
            sort_by="total_score",
            ascending=False,
            lookback_days=lookback_days,
        )
        nodes = []
        vectors = {}
        for row in rows:
            name = row.get("industry_name", "")
            score = float(row.get("score", row.get("total_score", 0)) or 0)
            momentum = float(row.get("momentum", 0) or 0)
            change_pct = float(row.get("change_pct", 0) or 0)
            flow = float(row.get("money_flow", row.get("flow_strength", 0)) or 0)
            volatility = float(row.get("industry_volatility", 0) or 0)
            vectors[name] = [
                score / 100,
                momentum / 100,
                change_pct / 20,
                flow / max(abs(flow), 1_000_000_000),
                volatility / 20,
            ]
            nodes.append(
                {
                    "id": name,
                    "label": name,
                    "score": round(score, 3),
                    "stage": _classify_industry_lifecycle(row)["stage"],
                    "etfs": _map_industry_etfs(name)[:2],
                }
            )

        edges = []
        names = list(vectors.keys())
        for left_index, left_name in enumerate(names):
            for right_name in names[left_index + 1 :]:
                similarity = _cosine_similarity(vectors[left_name], vectors[right_name])
                if similarity >= min_similarity:
                    edges.append(
                        {
                            "source": left_name,
                            "target": right_name,
                            "weight": round(float(similarity), 4),
                            "relationship": "factor_similarity",
                        }
                    )
        edges.sort(key=lambda item: item["weight"], reverse=True)
        result = {
            "success": True,
            "data": {
                "nodes": nodes,
                "edges": edges[:120],
                "metadata": {
                    "top_n": top_n,
                    "lookback_days": lookback_days,
                    "min_similarity": min_similarity,
                    "generated_at": datetime.now().isoformat(),
                },
            },
        }
        _set_endpoint_cache(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Error building industry network: {e}", exc_info=True)
        stale = _get_stale_endpoint_cache(cache_key)
        if stale is not None:
            return stale
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaders", response_model=list[LeaderStockResponse])
def get_leader_stocks(
    top_n: int = Query(20, ge=1, le=100, description="返回龙头股数量"),
    top_industries: int = Query(5, ge=1, le=20, description="从前N个热门行业中选取"),
    per_industry: int = Query(5, ge=1, le=20, description="每个行业选取的龙头数量"),
    list_type: Literal["hot", "core"] = Query(
        "hot", description="榜单类型：hot(热点先锋) 或 core(核心资产)"
    ),
) -> list[LeaderStockResponse]:
    """
    获取龙头股推荐列表

    - hot (热点先锋): 使用独立的 0-100 动量评分，聚焦短期涨势与资金关注度。
    - core (核心资产): 使用 0-100 综合评分，侧重长线基本面与流动性。
    """
    leaders = _load_leader_stock_list(
        top_n=top_n,
        top_industries=top_industries,
        per_industry=per_industry,
        list_type=list_type,
    )
    return leaders


@router.get("/leaders/overview", response_model=LeaderBoardsResponse)
def get_leader_boards(
    top_n: int = Query(20, ge=1, le=100, description="返回龙头股数量"),
    top_industries: int = Query(5, ge=1, le=20, description="从前N个热门行业中选取"),
    per_industry: int = Query(5, ge=1, le=20, description="每个行业选取的龙头数量"),
) -> LeaderBoardsResponse:
    """
    一次性返回核心资产与热点先锋榜单，减少前端冷启动的双请求成本。
    """
    analyzer, hot_industries, top_industry_names = _build_leader_context(top_industries)
    return _load_leader_overview_payload(
        top_n=top_n,
        top_industries=top_industries,
        per_industry=per_industry,
        analyzer=analyzer,
        hot_industries=hot_industries,
        top_industry_names=top_industry_names,
    )


@router.get("/bootstrap", response_model=IndustryBootstrapResponse)
def get_industry_bootstrap(
    days: int = Query(5, ge=1, le=90, description="热力图与默认热度排序使用的周期"),
    ranking_top_n: int = Query(50, ge=1, le=100, description="预热排行榜条数"),
    leader_top_n: int = Query(20, ge=1, le=100, description="预热龙头股总条数"),
    top_industries: int = Query(5, ge=1, le=20, description="龙头股从前N个热门行业中选取"),
    per_industry: int = Query(5, ge=1, le=20, description="每个行业选取的龙头数量"),
) -> IndustryBootstrapResponse:
    cache_key = f"industry_bootstrap:v2:{days}:{ranking_top_n}:{leader_top_n}:{top_industries}:{per_industry}"
    cached = _get_endpoint_cache(cache_key)
    if cached is not None:
        return _hydrate_bootstrap_with_cached_leaders(
            cached,
            cache_key,
            leader_top_n,
            top_industries,
            per_industry,
        )

    errors: dict[str, str] = {}
    try:
        analyzer = get_industry_analyzer()
        heatmap_data = analyzer.get_industry_heatmap_data(days=days)
        heatmap = _serialize_heatmap_response(heatmap_data)
        if heatmap.industries:
            _set_endpoint_cache(f"heatmap:v2:{days}", heatmap)
            _append_heatmap_history(days, heatmap)

        ranking_rows: list[dict[str, Any]] = []
        hot_industries: list[IndustryRankResponse] = []
        try:
            ranking_rows = analyzer.rank_industries(
                top_n=max(ranking_top_n, top_industries),
                sort_by="total_score",
                ascending=False,
                lookback_days=days,
            )
            hot_industries = _build_hot_industry_rank_responses(
                analyzer, ranking_rows[:ranking_top_n]
            )
        except Exception as exc:
            logger.warning("Industry bootstrap ranking warmup failed: %s", exc)
            errors["ranking"] = "行业排行榜预热失败"

        leader_payload = LeaderBoardsResponse()
        try:
            leader_source_rows = ranking_rows[: max(top_industries, 0)] if ranking_rows else None
            leader_source_names = {
                row.get("industry_name")
                for row in (leader_source_rows or [])
                if row.get("industry_name")
            } or None
            bootstrapped_leaders = _get_bootstrap_leader_payload(
                top_n=leader_top_n,
                top_industries=top_industries,
                per_industry=per_industry,
                analyzer=analyzer,
                hot_industries=leader_source_rows,
                top_industry_names=leader_source_names,
            )
            if bootstrapped_leaders is not None:
                leader_payload = bootstrapped_leaders
            if leader_payload.errors:
                errors.update(
                    {f"leaders_{key}": value for key, value in leader_payload.errors.items()}
                )
        except Exception as exc:
            logger.warning("Industry bootstrap leader warmup failed: %s", exc)
            errors["leaders"] = "龙头股榜单预热失败"

        payload = IndustryBootstrapResponse(
            days=days,
            ranking_top_n=ranking_top_n,
            ranking_type="gainers",
            ranking_sort_by="total_score",
            ranking_order="desc",
            heatmap=heatmap,
            hot_industries=hot_industries,
            leaders=leader_payload,
            errors=errors,
        )
        if payload.heatmap.industries:
            _set_endpoint_cache(cache_key, payload)
        return _hydrate_bootstrap_with_cached_leaders(
            payload,
            cache_key,
            leader_top_n,
            top_industries,
            per_industry,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error building industry bootstrap payload: %s", exc)
        stale = _get_stale_endpoint_cache(cache_key)
        if stale is not None:
            logger.warning("Using stale cache for industry bootstrap: %s", cache_key)
            return stale
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/leaders/{symbol}/detail", response_model=LeaderDetailResponse)
def get_leader_detail(
    symbol: str,
    score_type: Literal["core", "hot"] = Query("core", description="评分类型: core 或 hot"),
) -> LeaderDetailResponse:
    """
    获取龙头股详细分析

    返回指定股票的完整分析报告，包括评分详情、技术分析和历史价格。

    - **symbol**: 股票代码（如 "000001"、"600519"）
    """
    try:
        requested_symbol = str(symbol or "").strip()
        parity, matched_symbol, parity_is_stale = _get_matching_parity_cache(
            requested_symbol, score_type
        )
        if SIX_DIGIT_SYMBOL_PATTERN.fullmatch(matched_symbol or ""):
            resolved_symbol = matched_symbol
        else:
            resolved_symbol = _resolve_symbol_with_provider(requested_symbol)
            if parity is None:
                matched_parity, matched_symbol, matched_is_stale = _get_matching_parity_cache(
                    resolved_symbol, score_type
                )
                if matched_parity is not None:
                    parity = matched_parity
                    parity_is_stale = matched_is_stale
                    if SIX_DIGIT_SYMBOL_PATTERN.fullmatch(matched_symbol or ""):
                        resolved_symbol = matched_symbol

        # 端点级缓存
        cache_key = f"leader_detail:v2:{resolved_symbol}:{score_type}"
        cached = _get_endpoint_cache(cache_key)
        if cached is not None:
            return cached

        scorer = get_leader_scorer()
        detail = scorer.get_leader_detail(resolved_symbol, score_type=score_type)

        if "error" in detail:
            stale_detail = _get_stale_endpoint_cache(cache_key)
            if stale_detail is not None:
                logger.warning(
                    "Using stale leader detail cache for %s:%s after scorer error: %s",
                    resolved_symbol,
                    score_type,
                    detail["error"],
                )
                return stale_detail

            if parity is not None:
                fallback_note = (
                    "实时明细暂不可用，当前展示的是较早的榜单快照。"
                    if parity_is_stale
                    else "实时明细暂不可用，当前先展示榜单快照与缓存评分。"
                )
                fallback = _build_leader_detail_fallback(
                    parity,
                    score_type=score_type,
                    note=fallback_note,
                    source="leader_parity_cache_stale"
                    if parity_is_stale
                    else "leader_parity_cache",
                )
                logger.warning(
                    "Using parity fallback for leader detail %s -> %s:%s because scorer returned error: %s",
                    requested_symbol,
                    resolved_symbol,
                    score_type,
                    detail["error"],
                )
                _set_endpoint_cache(cache_key, fallback)
                return fallback

            raise HTTPException(
                status_code=_leader_detail_error_status(detail["error"]),
                detail=detail["error"],
            )

        # 尝试使用列表端点计算的快照得分来保证前端展示完全一致 (Score Parity)
        # 优先使用独立 parity 缓存（30分钟 TTL），过期后仍作为兜底
        if parity is None:
            parity = _get_parity_cache(resolved_symbol, score_type)
        if parity is None:
            parity = _get_stale_parity_cache(resolved_symbol, score_type)
            if parity is not None:
                parity_is_stale = True
                logger.info(f"Using stale parity cache for {resolved_symbol}:{score_type}")

        if parity:
            detail["total_score"] = parity.total_score
            if hasattr(parity, "dimension_scores") and parity.dimension_scores:
                detail["dimension_scores"] = parity.dimension_scores
            raw_data = detail.setdefault("raw_data", {})
            if hasattr(parity, "change_pct") and not has_meaningful_numeric(
                raw_data.get("change_pct")
            ):
                raw_data["change_pct"] = parity.change_pct
            if (
                hasattr(parity, "market_cap")
                and has_meaningful_numeric(parity.market_cap)
                and not has_meaningful_numeric(raw_data.get("market_cap"))
            ):
                raw_data["market_cap"] = parity.market_cap
            if (
                hasattr(parity, "pe_ratio")
                and has_meaningful_numeric(parity.pe_ratio)
                and not has_meaningful_numeric(raw_data.get("pe_ttm"))
            ):
                raw_data["pe_ttm"] = parity.pe_ratio

        result = LeaderDetailResponse(
            symbol=normalize_symbol(detail.get("symbol", resolved_symbol)),
            name=detail.get("name", ""),
            total_score=detail.get("total_score", 0),
            score_type=score_type,
            dimension_scores=detail.get("dimension_scores", {}),
            raw_data=detail.get("raw_data", {}),
            technical_analysis=detail.get("technical_analysis", {}),
            price_data=detail.get("price_data", []),
            degraded=bool(detail.get("degraded", False)),
            note=detail.get("note"),
        )
        _set_endpoint_cache(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting leader detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
def health_check():
    """
    行业分析模块健康检查 + 数据源状态

    返回当前活跃数据源、能力、连接状态等详细信息
    """
    import time

    try:
        from src.data.providers.akshare_provider import AKSHARE_AVAILABLE
    except Exception:
        AKSHARE_AVAILABLE = False

    # 判断当前活跃的 provider
    try:
        provider = _get_or_create_provider()
    except Exception:
        provider = None
    provider_name = "未初始化"
    provider_type = "none"

    if provider is not None:
        class_name = type(provider).__name__
        if "Sina" in class_name:
            provider_name = "新浪财经 (Sina Finance)"
            provider_type = "sina"
        elif "AKShare" in class_name:
            provider_name = "AKShare (东方财富)"
            provider_type = "akshare"
        else:
            provider_name = class_name
            provider_type = "unknown"

    # 数据源能力矩阵
    capabilities = {
        "akshare": {
            "name": "AKShare (东方财富)",
            "installed": AKSHARE_AVAILABLE,
            "has_market_cap": True,
            "has_multi_day": True,
            "has_real_money_flow": True,
            "day_options": ["1日", "5日", "10日"],
            "status": "unavailable",
            "status_detail": "",
        },
        "sina": {
            "name": "新浪财经 (Sina Finance)",
            "installed": True,
            "has_market_cap": True,  # 通过成分股汇总
            "has_multi_day": False,
            "has_real_money_flow": False,
            "day_options": ["当日"],
            "status": "unknown",
            "status_detail": "市值通过成分股数据汇总计算",
        },
        "ths": {
            "name": "同花顺 (THS)",
            "installed": True,
            "has_market_cap": False,
            "has_multi_day": True,
            "has_real_money_flow": True,
            "day_options": ["当日", "5日", "10日", "20日"],
            "status": "unknown",
            "status_detail": "多日涨跌与主力资金流向增强",
        },
    }

    # 检查 AKShare 实际连接
    if AKSHARE_AVAILABLE:
        try:
            import akshare as ak

            start = time.time()
            df = ak.stock_sector_fund_flow_rank(indicator="今日")
            elapsed = time.time() - start
            if df is not None and not df.empty:
                capabilities["akshare"]["status"] = "connected"
                capabilities["akshare"]["status_detail"] = f"响应 {elapsed:.1f}s, {len(df)} 行业"
            else:
                capabilities["akshare"]["status"] = "empty"
                capabilities["akshare"]["status_detail"] = "API 返回空数据"
        except Exception as e:
            err_msg = str(e)
            if "proxy" in err_msg.lower() or "connection" in err_msg.lower():
                capabilities["akshare"]["status"] = "blocked"
                capabilities["akshare"]["status_detail"] = "网络代理拦截"
            else:
                capabilities["akshare"]["status"] = "error"
                capabilities["akshare"]["status_detail"] = err_msg[:80]
    else:
        capabilities["akshare"]["status"] = "not_installed"
        capabilities["akshare"]["status_detail"] = "akshare 未安装"

    # 检查 Sina 连接
    try:
        from src.data.providers.sina_provider import SinaFinanceProvider

        sina = SinaFinanceProvider()
        start = time.time()
        industries = sina.get_industry_list()
        elapsed = time.time() - start

        # 兼容 DataFrame 判断和 None 判断
        is_success = False
        data_len = 0

        if industries is not None:
            if hasattr(industries, "empty"):
                is_success = not industries.empty
                data_len = len(industries)
            else:
                is_success = len(industries) > 0
                data_len = len(industries)

        if is_success:
            capabilities["sina"]["status"] = "connected"
            capabilities["sina"]["status_detail"] = f"响应 {elapsed:.1f}s, {data_len} 行业"
        else:
            capabilities["sina"]["status"] = "empty"
            capabilities["sina"]["status_detail"] = "API 返回空数据"
    except Exception as e:
        capabilities["sina"]["status"] = "error"
        capabilities["sina"]["status_detail"] = str(e)[:80]

    # 检查 THS 连接
    try:
        from src.data.providers.sina_ths_adapter import SinaIndustryAdapter

        adapter = SinaIndustryAdapter()
        start = time.time()
        ths_df = adapter._get_ths_flow_data(days=1)
        elapsed = time.time() - start

        if not ths_df.empty:
            capabilities["ths"]["status"] = "connected"
            capabilities["ths"]["status_detail"] = f"响应 {elapsed:.1f}s, {len(ths_df)} 行业"
        else:
            capabilities["ths"]["status"] = "empty"
            capabilities["ths"]["status_detail"] = "API 返回空数据"
    except Exception as e:
        capabilities["ths"]["status"] = "error"
        capabilities["ths"]["status_detail"] = str(e)[:80]

    # Sina fallback 状态
    try:
        analyzer = get_industry_analyzer()
    except Exception:
        analyzer = None
    has_sina_fallback = bool(analyzer and hasattr(analyzer, "_sina_fallback"))

    # 数据来源透出：当前生效的数据源组合
    data_sources_contributing = []
    if capabilities.get("ths", {}).get("status") == "connected":
        data_sources_contributing.append("ths")
    if capabilities.get("sina", {}).get("status") == "connected":
        data_sources_contributing.append("sina")
    if capabilities.get("akshare", {}).get("status") == "connected":
        data_sources_contributing.append("akshare")
    if not data_sources_contributing:
        data_sources_contributing = ["unknown"]

    data_source_mode = "sina_fallback" if has_sina_fallback else "ths_primary"

    return {
        "status": "healthy" if provider is not None else "degraded",
        "active_provider": {
            "name": provider_name,
            "type": provider_type,
        },
        "data_sources": capabilities,
        "sina_fallback_active": has_sina_fallback,
        "akshare_available": AKSHARE_AVAILABLE,
        "data_sources_contributing": data_sources_contributing,
        "data_source_mode": data_source_mode,
        "message": f"当前数据源: {provider_name}",
    }
