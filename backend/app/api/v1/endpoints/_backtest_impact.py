"""Market-impact helpers used by the backtest endpoint.

Pulled out of ``endpoints/backtest.py`` because the curve-building and
scenario-default logic is self-contained (depends only on
``src.backtest.impact_model.estimate_market_impact_rate``) and was the
densest cluster of pure-compute code in that 2087-line module.

The functions remain underscore-prefixed: they are internal helpers
re-exported by ``endpoints/backtest.py`` for callsite stability.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from src.backtest.impact_model import estimate_market_impact_rate


def _market_impact_curve(
    *,
    scenario: Dict[str, Any],
    data: pd.DataFrame,
    sample_trade_values: List[float],
) -> List[Dict[str, Any]]:
    close_prices = pd.to_numeric(data.get("close"), errors="coerce").dropna()
    reference_price = float(close_prices.iloc[-1]) if not close_prices.empty else 100.0
    returns = close_prices.pct_change().replace([np.inf, -np.inf], np.nan)
    volatility_reference = float(returns.std()) if returns.dropna().size else 0.02
    if "volume" in data.columns:
        volumes = pd.to_numeric(data["volume"], errors="coerce").clip(lower=0)
        dollar_volume = (
            pd.to_numeric(data["close"], errors="coerce") * volumes
        ).replace([np.inf, -np.inf], np.nan)
        liquidity_reference = (
            float(dollar_volume.dropna().median())
            if dollar_volume.dropna().size
            else float(scenario["impact_reference_notional"])
        )
    else:
        liquidity_reference = float(scenario["impact_reference_notional"])
    liquidity_reference = max(
        liquidity_reference, float(scenario["impact_reference_notional"]), 1.0
    )

    rows: List[Dict[str, Any]] = []
    for trade_value in sample_trade_values:
        trade_notional = max(float(trade_value or 0.0), 0.0)
        impact = estimate_market_impact_rate(
            trade_notional,
            market_impact_bps=scenario["market_impact_bps"],
            model=scenario["market_impact_model"],
            avg_daily_notional=liquidity_reference,
            volatility=volatility_reference,
            impact_coefficient=scenario["impact_coefficient"],
            permanent_impact_bps=scenario["permanent_impact_bps"],
            reference_notional=scenario["impact_reference_notional"],
        )
        rows.append(
            {
                "trade_value": trade_notional,
                "reference_price": reference_price,
                "estimated_shares": (
                    round(float(trade_notional / reference_price), 4)
                    if reference_price > 0
                    else 0.0
                ),
                "market_impact_rate": round(float(impact["impact_rate"]), 6),
                "market_impact_bps": round(float(impact["impact_rate"]) * 10000, 2),
                "participation_rate": round(float(impact["participation_rate"]), 4),
                "estimated_cost": round(
                    float(trade_notional * float(impact["impact_rate"])), 2
                ),
            }
        )
    return rows


def _default_market_impact_scenarios(request: Any) -> List[Dict[str, Any]]:
    """Build the four canonical impact scenarios.

    ``request`` is duck-typed: any object exposing ``impact_reference_notional``,
    ``market_impact_bps``, ``impact_coefficient`` and ``permanent_impact_bps``
    attributes. Concretely it is the ``MarketImpactAnalysisRequest`` Pydantic
    schema defined in the backtest endpoint module.
    """
    return [
        {
            "label": "无冲击基线",
            "market_impact_model": "constant",
            "market_impact_bps": 0.0,
            "impact_reference_notional": request.impact_reference_notional,
            "impact_coefficient": 1.0,
            "permanent_impact_bps": 0.0,
        },
        {
            "label": "线性冲击",
            "market_impact_model": "linear",
            "market_impact_bps": max(float(request.market_impact_bps or 8.0), 8.0),
            "impact_reference_notional": request.impact_reference_notional,
            "impact_coefficient": max(float(request.impact_coefficient or 1.0), 1.0),
            "permanent_impact_bps": 0.0,
        },
        {
            "label": "平方根冲击",
            "market_impact_model": "sqrt",
            "market_impact_bps": max(float(request.market_impact_bps or 12.0), 12.0),
            "impact_reference_notional": request.impact_reference_notional,
            "impact_coefficient": max(float(request.impact_coefficient or 1.0), 1.15),
            "permanent_impact_bps": 0.0,
        },
        {
            "label": "Almgren-Chriss",
            "market_impact_model": "almgren_chriss",
            "market_impact_bps": max(float(request.market_impact_bps or 18.0), 18.0),
            "impact_reference_notional": request.impact_reference_notional,
            "impact_coefficient": max(float(request.impact_coefficient or 1.0), 1.2),
            "permanent_impact_bps": max(float(request.permanent_impact_bps or 4.0), 4.0),
        },
    ]
