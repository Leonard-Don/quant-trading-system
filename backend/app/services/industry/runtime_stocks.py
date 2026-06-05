"""Pure stock-row normalization / quick-rank backfill helpers.

Extracted verbatim from ``runtime.py``. This cluster turns raw provider stock
dicts into ``StockResponse`` rows, promotes detail-ready rows to the front of
the quick board, reads cached-only valuations, and backfills missing quick-row
fields from those valuations. The functions take the provider as an explicit
argument and never reach for the runtime singletons, caches, locks or
executors — and they only call each other within this module
(``_backfill_quick_rows_with_cached_valuation`` → ``_load_cached_quick_valuation``)
— so there is no import cycle. ``runtime.py`` re-imports each name.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from backend.app.schemas.industry import StockResponse
from backend.app.services.industry.runtime_helpers import _count_quick_stock_detail_fields
from src.analytics.industry_stock_details import (
    coerce_optional_float,
    extract_stock_detail_fields,
    has_meaningful_numeric,
    normalize_symbol,
)

logger = logging.getLogger(__name__)


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


__all__ = [
    "_backfill_quick_rows_with_cached_valuation",
    "_build_stock_responses",
    "_load_cached_quick_valuation",
    "_promote_detail_ready_quick_rows",
]
