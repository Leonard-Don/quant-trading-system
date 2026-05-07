"""Rotation / preferences / trend / cluster / health routes.

Catch-all sub-router for industry endpoints that aren't heatmap or
leader specific.
"""

import json
import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from backend.app.api.v1.endpoints._industry_helpers import (
    _build_industry_events,
    _classify_industry_lifecycle,
    _cosine_similarity,
)
from backend.app.api.v1.endpoints.industry._compat import (
    _build_full_industry_stock_response,
    _build_hot_industry_rank_responses,
    _build_quick_industry_stock_response,
    _build_trend_summary_from_stock_rows,
    _get_endpoint_cache,
    _get_or_create_provider,
    _get_stale_endpoint_cache,
    _get_stock_build_status,
    _get_stock_cache_keys,
    _load_trend_alignment_stock_rows,
    _map_industry_etfs,
    _resolve_industry_profile,
    _schedule_full_stock_cache_build,
    _set_endpoint_cache,
    _should_align_trend_with_stock_rows,
    get_industry_analyzer,
)
from backend.app.core.error_handler import AppException
from backend.app.schemas.industry import (
    ClusterResponse,
    IndustryPreferencesResponse,
    IndustryRankResponse,
    IndustryRotationResponse,
    IndustryStockBuildStatusResponse,
    IndustryTrendResponse,
    StockResponse,
)
from backend.app.services.industry_preferences import (
    industry_preferences_store,
)

logger = logging.getLogger(__name__)
router = APIRouter()
_INDUSTRY_ENDPOINT_OPERATIONAL_ERRORS = (
    AppException,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


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
    except _INDUSTRY_ENDPOINT_OPERATIONAL_ERRORS as e:
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
            except _INDUSTRY_ENDPOINT_OPERATIONAL_ERRORS as e:
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
    except _INDUSTRY_ENDPOINT_OPERATIONAL_ERRORS as e:
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
    except _INDUSTRY_ENDPOINT_OPERATIONAL_ERRORS as e:
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
    except _INDUSTRY_ENDPOINT_OPERATIONAL_ERRORS as e:
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
