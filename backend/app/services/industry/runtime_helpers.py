"""Pure data-transform helpers for the industry runtime.

Lifted out of ``runtime.py`` — functions with no module-global state (no
caches, locks, executors or provider access), so they can be tested in
isolation. ``runtime.py`` imports and re-exports them.
"""
from __future__ import annotations

import re
from typing import Any

from backend.app.api.v1.endpoints._industry_helpers import (
    _model_to_dict,
    _normalize_sparkline_points,
)
from backend.app.schemas.industry import LeaderStockResponse
from src.analytics.industry_stock_details import (
    extract_stock_detail_fields,
    has_meaningful_numeric,
    normalize_symbol,
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


__all__ = [
    "_build_parity_price_data",
    "_coerce_trend_alignment_stock_rows",
    "_count_quick_stock_detail_fields",
    "_dedupe_leader_responses",
    "_leader_detail_error_status",
]
