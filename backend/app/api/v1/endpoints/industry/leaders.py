"""Leaders / leader-detail routes for the industry sub-router.

Routes here cover ``/leaders*`` and ``/leaders/{symbol}/detail``.
"""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError as PydanticValidationError

from backend.app.api.v1.endpoints.industry._compat import (
    SIX_DIGIT_SYMBOL_PATTERN,
    _build_leader_context,
    _build_leader_detail_fallback,
    _get_endpoint_cache,
    _get_matching_parity_cache,
    _get_parity_cache,
    _get_stale_endpoint_cache,
    _get_stale_parity_cache,
    _leader_detail_error_status,
    _load_leader_overview_payload,
    _load_leader_stock_list,
    _resolve_symbol_with_provider,
    _set_endpoint_cache,
    get_leader_scorer,
)
from backend.app.core.error_handler import AppException
from backend.app.schemas.industry import (
    LeaderBoardsResponse,
    LeaderDetailResponse,
    LeaderStockResponse,
)
from src.analytics.industry_stock_details import (
    has_meaningful_numeric,
    normalize_symbol,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_INDUSTRY_ENDPOINT_ERRORS = (
    ConnectionError,
    KeyError,
    OSError,
    PydanticValidationError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)


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
    except AppException:
        raise
    except _INDUSTRY_ENDPOINT_ERRORS as exc:
        logger.error("Error getting leader detail: %s", exc)
        raise AppException(
            message=str(exc),
            error_code="INDUSTRY_LEADER_DETAIL_FAILED",
            status_code=500,
        ) from exc
