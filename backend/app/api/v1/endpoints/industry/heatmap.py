"""Heatmap / snapshot / bootstrap routes for the industry sub-router.

Routes here cover ``/industries/heatmap*`` plus the cold-start
``/bootstrap`` endpoint that warms the heatmap + leader caches.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.app.api.v1.endpoints.industry._compat import (
    _append_heatmap_history,
    _build_heatmap_response_from_history,
    _build_hot_industry_rank_responses,
    _get_bootstrap_leader_payload,
    _get_endpoint_cache,
    _get_stale_endpoint_cache,
    _heatmap_history,
    _heatmap_history_lock,
    _hydrate_bootstrap_with_cached_leaders,
    _load_heatmap_history_from_disk,
    _load_live_heatmap_response,
    _schedule_heatmap_refresh,
    _serialize_heatmap_response,
    _set_endpoint_cache,
    get_industry_analyzer,
)
from backend.app.schemas.industry import (
    HeatmapDataItem,
    HeatmapHistoryItem,
    HeatmapHistoryResponse,
    HeatmapResponse,
    IndustryBootstrapResponse,
    IndustryRankResponse,
    LeaderBoardsResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


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
