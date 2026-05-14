"""ETF rotation — read-only HTTP surface for the daily manual trade plan.

This wraps :func:`scripts.daily_etf_signal.generate_plan` so the frontend can
render the same manual-only suggestions the CLI prints. The endpoint remains
broker-agnostic: it may read market quotes, but it never contacts a broker and
never submits orders.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from scripts import daily_etf_signal
from src.data.etf_rotation import DEFAULT_UNIVERSE, EtfQuote, EtfUniverseItem
from src.data.realtime_manager import realtime_manager

logger = logging.getLogger(__name__)

router = APIRouter()

_UNIVERSE_BY_CODE = {item.code: item for item in DEFAULT_UNIVERSE}


def _realtime_symbol_for(item: EtfUniverseItem) -> str:
    suffix = "SS" if item.exchange == "sh" else "SZ"
    return f"{item.code}.{suffix}"


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _iso_timestamp(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _quote_from_realtime_payload(
    code: str,
    payload: Mapping[str, Any],
) -> EtfQuote | None:
    price = _float_or_none(payload.get("price"))
    if price is None or price <= 0:
        return None

    item = _UNIVERSE_BY_CODE.get(code)
    name = (
        payload.get("short_name")
        or payload.get("long_name")
        or payload.get("display_name")
        or payload.get("name")
        or (item.name if item else code)
    )
    timestamp = _iso_timestamp(payload.get("timestamp"))
    return EtfQuote(
        code=code,
        name=str(name),
        current_price=price,
        prev_close=_float_or_none(payload.get("previous_close", payload.get("prev_close"))),
        open_price=_float_or_none(payload.get("open")),
        high=_float_or_none(payload.get("high")),
        low=_float_or_none(payload.get("low")),
        volume=_float_or_none(payload.get("volume")),
        amount=_float_or_none(payload.get("amount")),
        timestamp=timestamp,
        source=str(payload.get("source") or "realtime_manager"),
    )


def _load_live_quotes(*, use_cache: bool = True) -> tuple[dict[str, EtfQuote], dict[str, Any]]:
    symbol_to_code = {
        _realtime_symbol_for(item): item.code
        for item in DEFAULT_UNIVERSE
    }
    symbols = list(symbol_to_code)
    try:
        payloads = realtime_manager.get_quotes_dict(symbols, use_cache=use_cache)
    except Exception as exc:  # pragma: no cover - defensive; covered by status contract
        logger.warning("ETF live quote fetch failed: %s", exc)
        return {}, {
            "requested": len(symbols),
            "resolved": 0,
            "missing": len(symbols),
            "use_cache": use_cache,
            "error": str(exc),
        }

    quotes: dict[str, EtfQuote] = {}
    for symbol, code in symbol_to_code.items():
        payload = payloads.get(symbol) or payloads.get(symbol.upper()) or {}
        quote = _quote_from_realtime_payload(code, payload)
        if quote is not None:
            quotes[code] = quote

    return quotes, {
        "requested": len(symbols),
        "resolved": len(quotes),
        "missing": max(len(symbols) - len(quotes), 0),
        "use_cache": use_cache,
        "symbols": symbols,
    }


@router.get(
    "/daily-signal",
    summary="获取每日 ETF 轮动手动调仓建议",
    description=(
        "返回 ``scripts.daily_etf_signal.generate_plan`` 的完整计划字段："
        "current_weights / target_weights / adjusted_weights / suggestions / "
        "risk_reasons。该接口只读、默认使用实时行情更新持仓现价，但不调用任何券商或下单接口。"
    ),
)
def get_daily_signal(
    threshold_weight: float = Query(
        default=0.03,
        ge=0.0,
        le=1.0,
        description="低于该权重差异的标的不会触发买卖建议（仅生成 hold）。",
    ),
    quote_source: str = Query(
        default="live",
        pattern="^(live|synthetic)$",
        description="live=用实时行情刷新持仓现价；synthetic=使用截图种子的确定性行情。",
    ),
    use_cache: bool = Query(
        default=True,
        description="live 模式下是否允许使用实时行情缓存；手动刷新可传 false。",
    ),
) -> dict[str, Any]:
    if quote_source == "synthetic":
        plan = daily_etf_signal.generate_plan(threshold_weight=threshold_weight)
        plan["quote_source"] = "synthetic"
        plan["live_quote_status"] = {
            "requested": 0,
            "resolved": 0,
            "missing": 0,
            "use_cache": use_cache,
        }
        return {"success": True, "data": plan}

    seed_holdings = daily_etf_signal.load_default_holdings()
    live_quotes, live_status = _load_live_quotes(use_cache=use_cache)
    if live_quotes:
        holdings = daily_etf_signal.apply_quotes_to_holdings(seed_holdings, live_quotes)
        quote_map = daily_etf_signal.load_default_quotes(holdings)
        quote_map.update(live_quotes)
        plan = daily_etf_signal.generate_plan(
            holdings=holdings,
            quotes=quote_map,
            threshold_weight=threshold_weight,
            quotes_as_of=max(
                (quote.timestamp for quote in live_quotes.values() if quote.timestamp),
                default=None,
            ),
        )
        plan["quote_source"] = "live"
    else:
        plan = daily_etf_signal.generate_plan(threshold_weight=threshold_weight)
        plan["quote_source"] = "fallback_synthetic"
    plan["live_quote_status"] = live_status
    return {"success": True, "data": plan}
