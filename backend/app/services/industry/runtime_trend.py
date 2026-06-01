"""Trend-panel summary helpers, extracted from runtime.py.

Two pure, leaf functions: one rebuilds the trend panel's constituent-stock
summary (counts, coverage ratios, weighted avg PE, top movers) from a unified
stock-row list; the other decides whether the trend summary should be
re-aligned to the stock-row count. They depend only one-way on leaf analytics
helpers (``extract_stock_detail_fields``, ``has_meaningful_numeric``) and the
stdlib — they call no runtime helper, touch no runtime module state, and are
never called from inside runtime.py (only by the sub-routers via ``_compat``) —
so moving them out creates no import cycle. runtime.py re-imports both so the
``__all__`` surface and ``_compat`` helper capture keep resolving.
"""

from __future__ import annotations

import math
from typing import Any

from src.analytics.industry_stock_details import (
    extract_stock_detail_fields,
    has_meaningful_numeric,
)


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
