"""
行业成分股明细补齐辅助函数
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging
import re


logger = logging.getLogger(__name__)


def normalize_symbol(symbol: str) -> str:
    """提取并标准化 A 股 6 位代码；无法识别时返回原值。"""
    raw = str(symbol or "").strip()
    if not raw:
        return raw
    match = re.search(r"(\d{6})", raw)
    return match.group(1) if match else raw


def has_meaningful_numeric(value) -> bool:
    """判断数值是否有效且非占位值。"""
    if value is None or value == "":
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def coerce_optional_float(value) -> Optional[float]:
    """将数值转换为 float；缺失或非法时返回 None。"""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_stock_detail_fields(stock: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """统一提取成分股明细字段，保留空值语义。"""
    market_cap = coerce_optional_float(stock.get("market_cap"))
    if market_cap is None and stock.get("mktcap") not in (None, ""):
        raw_mktcap = coerce_optional_float(stock.get("mktcap"))
        market_cap = raw_mktcap * 10000 if raw_mktcap is not None else None

    pe_ratio = coerce_optional_float(
        stock.get("pe_ratio", stock.get("pe_ttm", stock.get("pe")))
    )
    change_pct = coerce_optional_float(stock.get("change_pct", stock.get("pct_chg")))
    money_flow = coerce_optional_float(
        stock.get("money_flow", stock.get("main_net_inflow", stock.get("amount")))
    )
    turnover_rate = coerce_optional_float(
        stock.get("turnover_rate", stock.get("turnover"))
    )

    return {
        "name": str(stock.get("name") or "").strip() or None,
        "market_cap": market_cap,
        "pe_ratio": pe_ratio,
        "change_pct": change_pct,
        "money_flow": money_flow,
        "turnover_rate": turnover_rate,
        "turnover": turnover_rate,
    }


def merge_ranked_stocks_with_provider_details(
    ranked_stocks: List[Dict[str, Any]],
    provider_stocks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """保留评分排序，同时用 provider 明细补齐行情/基本面字段。"""
    details_by_symbol = {
        normalize_symbol(stock.get("symbol") or stock.get("code") or ""): extract_stock_detail_fields(stock)
        for stock in provider_stocks or []
        if normalize_symbol(stock.get("symbol") or stock.get("code") or "")
    }

    merged = []
    for stock in ranked_stocks or []:
        symbol = normalize_symbol(stock.get("symbol") or stock.get("code") or "")
        if not symbol:
            continue

        detail = details_by_symbol.get(symbol, {})
        ranked_detail = extract_stock_detail_fields(stock)
        merged_stock = dict(stock)

        if detail.get("name"):
            merged_stock["name"] = detail["name"]
        elif ranked_detail.get("name"):
            merged_stock["name"] = ranked_detail["name"]

        provider_market_cap = detail.get("market_cap")
        ranked_market_cap = ranked_detail.get("market_cap")
        merged_stock["market_cap"] = (
            provider_market_cap
            if has_meaningful_numeric(provider_market_cap)
            else (ranked_market_cap if has_meaningful_numeric(ranked_market_cap) else None)
        )

        provider_pe_ratio = detail.get("pe_ratio")
        ranked_pe_ratio = ranked_detail.get("pe_ratio")
        merged_stock["pe_ratio"] = (
            provider_pe_ratio
            if has_meaningful_numeric(provider_pe_ratio)
            else (ranked_pe_ratio if has_meaningful_numeric(ranked_pe_ratio) else None)
        )

        provider_change_pct = detail.get("change_pct")
        ranked_change_pct = ranked_detail.get("change_pct")
        merged_stock["change_pct"] = (
            provider_change_pct
            if provider_change_pct is not None
            else ranked_change_pct
        )

        provider_money_flow = detail.get("money_flow")
        ranked_money_flow = ranked_detail.get("money_flow")
        merged_stock["money_flow"] = (
            provider_money_flow
            if provider_money_flow is not None
            else ranked_money_flow
        )

        provider_turnover_rate = detail.get("turnover_rate")
        ranked_turnover_rate = ranked_detail.get("turnover_rate")
        merged_stock["turnover_rate"] = (
            provider_turnover_rate
            if provider_turnover_rate is not None
            else ranked_turnover_rate
        )
        merged_stock["turnover"] = merged_stock["turnover_rate"]

        merged.append(merged_stock)

    return merged


def backfill_stock_details_with_valuation(
    stocks: List[Dict[str, Any]],
    provider,
) -> List[Dict[str, Any]]:
    """在成分股明细缺失时，按 symbol 补单股估值数据。"""
    if not stocks or not hasattr(provider, "get_stock_valuation"):
        return stocks

    valuation_cache: dict[str, dict] = {}
    enriched = []

    for stock in stocks:
        symbol = normalize_symbol(stock.get("symbol") or stock.get("code") or "")
        if not symbol:
            enriched.append(stock)
            continue

        detail_fields = extract_stock_detail_fields(stock)
        missing_market_cap = not has_meaningful_numeric(detail_fields.get("market_cap"))
        missing_pe_ratio = not has_meaningful_numeric(detail_fields.get("pe_ratio"))
        missing_change_pct = detail_fields.get("change_pct") is None

        if not (missing_market_cap or missing_pe_ratio or missing_change_pct):
            enriched.append(stock)
            continue

        if symbol not in valuation_cache:
            try:
                valuation_cache[symbol] = provider.get_stock_valuation(symbol) or {}
            except Exception as e:
                logger.warning(f"Failed to backfill valuation for {symbol}: {e}")
                valuation_cache[symbol] = {}

        valuation = valuation_cache[symbol]
        valuation_market_cap = coerce_optional_float(valuation.get("market_cap"))
        valuation_pe_ratio = coerce_optional_float(valuation.get("pe_ratio", valuation.get("pe_ttm")))
        valuation_change_pct = coerce_optional_float(valuation.get("change_pct"))

        enriched_stock = dict(stock)
        if missing_market_cap and has_meaningful_numeric(valuation_market_cap):
            enriched_stock["market_cap"] = valuation_market_cap
        if missing_pe_ratio and has_meaningful_numeric(valuation_pe_ratio):
            enriched_stock["pe_ratio"] = valuation_pe_ratio
        if missing_change_pct and valuation_change_pct is not None:
            enriched_stock["change_pct"] = valuation_change_pct
        if not enriched_stock.get("name") and valuation.get("name"):
            enriched_stock["name"] = valuation["name"]

        enriched.append(enriched_stock)

    return enriched


def build_enriched_industry_stocks(
    provider,
    industry_name: str,
    ranked_stocks: Optional[List[Dict[str, Any]]] = None,
    provider_stocks: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """构造统一口径的行业成分股明细。"""
    raw_provider_stocks = provider_stocks
    if raw_provider_stocks is None:
        raw_provider_stocks = provider.get_stock_list_by_industry(industry_name)

    if ranked_stocks:
        merged = merge_ranked_stocks_with_provider_details(ranked_stocks, raw_provider_stocks or [])
    else:
        merged = list(raw_provider_stocks or [])

    return backfill_stock_details_with_valuation(merged, provider)
