"""
市场深度解析与 provider 适配层。
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        numeric = float(value)
        if numeric != numeric:
            return default
        return numeric
    except (TypeError, ValueError):
        return default


def build_synthetic_orderbook(symbol: str, quote: Dict[str, Any], levels: int = 5) -> Dict[str, Any]:
    price = _safe_float(quote.get("price") or quote.get("last") or quote.get("close"))
    if price is None or price <= 0:
        return {"bids": [], "asks": [], "symbol": symbol}

    safe_levels = max(1, min(int(levels or 5), 50))
    spread = max(price * 0.0008, 0.01)
    volume = max(int(_safe_float(quote.get("volume"), 1000) or 1000), 1000)
    bids: List[Dict[str, Any]] = []
    asks: List[Dict[str, Any]] = []

    for index in range(safe_levels):
        step = index + 1
        bids.append({
            "level": step,
            "price": round(price - spread * step, 4),
            "size": int(volume / (80 * step)),
        })
        asks.append({
            "level": step,
            "price": round(price + spread * step, 4),
            "size": int(volume / (85 * step)),
        })

    return {
        "symbol": symbol,
        "bids": bids,
        "asks": asks,
        "synthetic_mid": round(price, 4),
        "synthetic_spread": round(spread * 2, 4),
    }


def _derive_quote_proxy_orderbook(
    symbol: str,
    quote: Dict[str, Any],
    *,
    levels: int,
    provider_name: str,
) -> Optional[Dict[str, Any]]:
    price = _safe_float(quote.get("price") or quote.get("last") or quote.get("close"))
    bid = _safe_float(quote.get("bid"))
    ask = _safe_float(quote.get("ask"))
    if price is None and bid is None and ask is None:
        return None

    mid = price
    if mid is None and bid is not None and ask is not None:
        mid = (bid + ask) / 2
    if mid is None:
        mid = bid or ask
    if mid is None or mid <= 0:
        return None

    bid = bid if bid is not None and bid > 0 else mid * 0.9995
    ask = ask if ask is not None and ask > 0 else mid * 1.0005
    base_spread = max(ask - bid, mid * 0.0004, 0.01)
    safe_levels = max(1, min(int(levels or 10), 50))
    volume = max(int(_safe_float(quote.get("volume"), 5000) or 5000), 1000)

    bids: List[Dict[str, Any]] = []
    asks: List[Dict[str, Any]] = []
    for index in range(safe_levels):
        step = index + 1
        decay = max(0.2, 1.0 - (index * 0.08))
        level_spread = base_spread * max(1.0, step * 0.9)
        bids.append({
            "level": step,
            "price": round(bid - (level_spread * index), 4),
            "size": int(volume / (45 * step) * decay),
        })
        asks.append({
            "level": step,
            "price": round(ask + (level_spread * index), 4),
            "size": int(volume / (48 * step) * decay),
        })

    return {
        "symbol": symbol,
        "source": provider_name,
        "bids": bids,
        "asks": asks,
        "quote_proxy_mid": round(mid, 4),
        "quote_proxy_spread": round(base_spread, 4),
    }


def _normalize_side(rows: Any, side: str, levels: int) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(rows, list):
        return normalized

    for index, row in enumerate(rows[:levels]):
        if isinstance(row, dict):
            price = _safe_float(row.get("price") or row.get("px"))
            size = _safe_float(row.get("size") or row.get("quantity") or row.get("qty") or row.get("volume"))
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            price = _safe_float(row[0])
            size = _safe_float(row[1])
        else:
            continue
        if price is None or size is None:
            continue
        normalized.append({
            "level": int(row.get("level") or index + 1) if isinstance(row, dict) else index + 1,
            "price": round(price, 4),
            "size": int(size),
            "side": side,
        })
    return normalized


def normalize_orderbook_payload(
    symbol: str,
    payload: Dict[str, Any],
    *,
    levels: int,
    source: str,
    mode: str,
) -> Dict[str, Any]:
    bids = _normalize_side(payload.get("bids") or payload.get("bid"), "bid", levels)
    asks = _normalize_side(payload.get("asks") or payload.get("ask"), "ask", levels)

    best_bid = bids[0]["price"] if bids else None
    best_ask = asks[0]["price"] if asks else None
    mid_price = None
    if best_bid is not None and best_ask is not None:
        mid_price = round((best_bid + best_ask) / 2, 4)

    bid_notional = sum(float(item["price"]) * float(item["size"]) for item in bids)
    ask_notional = sum(float(item["price"]) * float(item["size"]) for item in asks)
    total_depth = bid_notional + ask_notional
    imbalance = None
    if total_depth > 0:
        imbalance = round((bid_notional - ask_notional) / total_depth, 4)

    spread = None
    if best_bid is not None and best_ask is not None:
        spread = round(best_ask - best_bid, 4)

    for row in bids + asks:
        row["notional"] = round(float(row["price"]) * float(row["size"]), 2)

    return {
        "symbol": symbol,
        "source": source,
        "mode": mode,
        "level2_supported": mode == "provider_level2",
        "bids": bids,
        "asks": asks,
        "metrics": {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid_price,
            "spread": spread,
            "spread_bps": round((spread / mid_price) * 10000, 2) if spread is not None and mid_price not in (None, 0) else None,
            "bid_notional": round(bid_notional, 2),
            "ask_notional": round(ask_notional, 2),
            "depth_imbalance": imbalance,
            "levels_loaded": max(len(bids), len(asks)),
        },
    }


def resolve_market_depth(
    symbol: str,
    *,
    levels: int,
    provider_factory: Any,
    quote_loader: Callable[[str], Dict[str, Any]],
) -> Dict[str, Any]:
    safe_levels = max(1, min(int(levels or 10), 50))
    providers = list(getattr(provider_factory, "providers", {}).items()) if provider_factory is not None else []
    provider_candidates: List[Dict[str, Any]] = []

    best_payload: Optional[Dict[str, Any]] = None
    best_priority: Tuple[int, int] = (999, 999)

    for rank, (provider_name, provider) in enumerate(providers):
        started_at = time.perf_counter()
        supports_level2 = callable(getattr(provider, "get_order_book", None)) and provider.supports_capability("order_book")
        quote_proxy_supported = callable(getattr(provider, "get_latest_quote", None))
        candidate = {
            "provider": provider_name,
            "supports_level2": supports_level2,
            "supports_quote_proxy": quote_proxy_supported,
            "status": "unavailable",
            "mode": None,
            "latency_ms": None,
            "detail": None,
        }

        try:
            if supports_level2:
                payload = provider.get_order_book(symbol, levels=safe_levels) or {}
                normalized = normalize_orderbook_payload(
                    symbol,
                    payload,
                    levels=safe_levels,
                    source=provider_name,
                    mode="provider_level2",
                )
                if normalized["bids"] or normalized["asks"]:
                    candidate["status"] = "available"
                    candidate["mode"] = "provider_level2"
                    candidate["detail"] = "provider exposed get_order_book"
                    if (0, rank) < best_priority:
                        best_payload = normalized
                        best_priority = (0, rank)
                else:
                    candidate["status"] = "empty"
                    candidate["detail"] = "provider returned empty depth"

            if best_payload is None and quote_proxy_supported:
                quote = provider.get_latest_quote(symbol) or {}
                if "error" not in quote:
                    proxy_payload = _derive_quote_proxy_orderbook(
                        symbol,
                        quote,
                        levels=safe_levels,
                        provider_name=provider_name,
                    )
                    if proxy_payload:
                        normalized = normalize_orderbook_payload(
                            symbol,
                            proxy_payload,
                            levels=safe_levels,
                            source=provider_name,
                            mode="provider_quote_proxy",
                        )
                        candidate["status"] = "available"
                        candidate["mode"] = "provider_quote_proxy"
                        candidate["detail"] = "quote-derived ladder from provider quote"
                        if (1, rank) < best_priority:
                            best_payload = normalized
                            best_priority = (1, rank)
                    elif candidate["status"] == "unavailable":
                        candidate["status"] = "empty"
                        candidate["detail"] = "provider quote missing bid/ask and price context"
                elif candidate["status"] == "unavailable":
                    candidate["status"] = "error"
                    candidate["detail"] = str(quote.get("error") or "quote loader failed")[:120]
        except Exception as exc:  # pragma: no cover - network/provider variance
            candidate["status"] = "error"
            candidate["detail"] = str(exc)[:120]
        finally:
            candidate["latency_ms"] = round((time.perf_counter() - started_at) * 1000, 2)
            provider_candidates.append(candidate)

    if best_payload is None:
        fallback_quote = quote_loader(symbol) or {}
        synthetic = build_synthetic_orderbook(symbol, fallback_quote, levels=safe_levels)
        best_payload = normalize_orderbook_payload(
            symbol,
            synthetic,
            levels=safe_levels,
            source=str(fallback_quote.get("source") or "synthetic_quote_proxy"),
            mode="synthetic_quote_proxy",
        )

    metrics = best_payload.get("metrics") or {}
    diagnostics = {
        "message": {
            "provider_level2": "Provider exposes native Level 2 order book.",
            "provider_quote_proxy": "No native Level 2 feed found; built depth ladder from provider quote fields.",
            "synthetic_quote_proxy": "No provider depth feed is configured; returned synthetic quote-derived depth for continuity.",
        }.get(best_payload.get("mode"), "Market depth diagnostics unavailable."),
        "is_synthetic": best_payload.get("mode") != "provider_level2",
        "provider_candidates": provider_candidates,
        "provider_count": len(provider_candidates),
        "best_provider": best_payload.get("source"),
        "spread_bps": metrics.get("spread_bps"),
        "depth_imbalance": metrics.get("depth_imbalance"),
        "levels_loaded": metrics.get("levels_loaded"),
    }

    return {
        **best_payload,
        "diagnostics": diagnostics,
    }
