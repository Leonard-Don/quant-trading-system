"""Execution market-impact helpers shared by backtesting engines."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable


SUPPORTED_MARKET_IMPACT_MODELS = {
    "constant",
    "linear",
    "sqrt",
    "almgren_chriss",
}


def normalize_market_impact_model(model: str | None) -> str:
    normalized = str(model or "constant").strip().lower()
    return normalized if normalized in SUPPORTED_MARKET_IMPACT_MODELS else "constant"


def estimate_market_impact_rate(
    trade_notional: float,
    *,
    market_impact_bps: float = 0.0,
    model: str = "constant",
    avg_daily_notional: float | None = None,
    volatility: float | None = None,
    impact_coefficient: float = 1.0,
    permanent_impact_bps: float = 0.0,
    reference_notional: float = 100_000.0,
) -> Dict[str, float | str]:
    notional = max(float(trade_notional or 0.0), 0.0)
    base_rate = max(float(market_impact_bps or 0.0), 0.0) / 10_000.0
    normalized_model = normalize_market_impact_model(model)
    coefficient = max(float(impact_coefficient or 1.0), 0.0)
    permanent_rate = max(float(permanent_impact_bps or 0.0), 0.0) / 10_000.0
    liquidity_proxy = max(
        float(avg_daily_notional or 0.0),
        float(reference_notional or 100_000.0),
        1.0,
    )
    participation_rate = min(notional / liquidity_proxy, 5.0) if notional > 0 else 0.0
    sigma = min(max(float(volatility or 0.02), 0.001), 1.0)

    if normalized_model == "linear":
        impact_rate = base_rate * coefficient * participation_rate
    elif normalized_model == "sqrt":
        impact_rate = base_rate * coefficient * math.sqrt(participation_rate)
    elif normalized_model == "almgren_chriss":
        temporary_rate = base_rate * max(coefficient, 0.25) * math.sqrt(participation_rate)
        volatility_adjustment = min(max(sigma / 0.02, 0.5), 3.0)
        impact_rate = (temporary_rate * volatility_adjustment) + (permanent_rate * participation_rate)
    else:
        impact_rate = base_rate

    impact_rate = min(max(float(impact_rate), 0.0), 0.25)
    return {
        "model": normalized_model,
        "impact_rate": impact_rate,
        "participation_rate": participation_rate,
        "liquidity_proxy": liquidity_proxy,
        "volatility_estimate": sigma,
    }


def summarize_execution_costs(trades: Iterable[Dict[str, Any]]) -> Dict[str, float | int | str | None]:
    trade_rows = list(trades or [])
    total_market_impact_cost = 0.0
    total_slippage_cost = 0.0
    total_notional = 0.0
    max_impact_rate = 0.0
    weighted_impact_rate = 0.0
    model = None

    for trade in trade_rows:
        notional = abs(float(trade.get("price", 0) or 0.0) * float(trade.get("shares", 0) or 0.0))
        market_impact_cost = float(trade.get("estimated_market_impact_cost", 0.0) or 0.0)
        slippage_cost = float(trade.get("estimated_total_slippage_cost", 0.0) or 0.0)
        impact_rate = float(trade.get("market_impact_rate", 0.0) or 0.0)
        model = model or trade.get("impact_model")

        total_notional += notional
        total_market_impact_cost += market_impact_cost
        total_slippage_cost += slippage_cost
        weighted_impact_rate += impact_rate * notional
        max_impact_rate = max(max_impact_rate, impact_rate)

    average_impact_rate = (weighted_impact_rate / total_notional) if total_notional > 0 else 0.0
    return {
        "impact_model": model,
        "trade_count": len(trade_rows),
        "total_notional": total_notional,
        "estimated_market_impact_cost": total_market_impact_cost,
        "estimated_total_slippage_cost": total_slippage_cost,
        "average_market_impact_rate": average_impact_rate,
        "max_market_impact_rate": max_impact_rate,
    }
