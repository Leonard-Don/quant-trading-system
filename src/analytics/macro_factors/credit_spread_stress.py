"""
信用利差压力因子。
"""

from __future__ import annotations

from typing import Any, Dict

from .base_factor import MacroFactor


class CreditSpreadStressFactor(MacroFactor):
    """用波动率、物流摩擦和贸易走弱近似信用利差扩张压力。"""

    name = "credit_spread_stress"
    default_threshold = 0.16

    def compute(self, data_context: Dict[str, Any]):
        indicators = data_context.get("market_indicators", {}) or {}
        macro_signal = data_context.get("signals", {}).get("macro_hf", {}) or {}
        logistics_score = float(macro_signal.get("dimensions", {}).get("logistics", {}).get("score", 0.0))
        trade_score = float(macro_signal.get("dimensions", {}).get("trade", {}).get("score", 0.0))
        inventory_score = float(macro_signal.get("dimensions", {}).get("inventory", {}).get("score", 0.0))
        vix_pressure = _normalize_vix(indicators.get("vix"))

        factor_value = max(
            -1.0,
            min(
                1.0,
                vix_pressure * 0.45 + max(logistics_score, 0.0) * 0.25 + max(-trade_score, 0.0) * 0.2 + max(inventory_score, 0.0) * 0.1,
            ),
        )
        confidence = min(
            1.0,
            0.42
            + (0.2 if indicators.get("vix") is not None else 0.0)
            + float(macro_signal.get("confidence", 0.0)) * 0.28,
        )

        history = [0.0, 0.04, 0.08, 0.14]
        return self._build_result(
            value=factor_value,
            history=history,
            confidence=confidence,
            metadata={
                "vix": indicators.get("vix"),
                "logistics_score": round(logistics_score, 4),
                "trade_score": round(trade_score, 4),
                "inventory_score": round(inventory_score, 4),
            },
        )


def _normalize_vix(value: Any) -> float:
    if value is None:
        return 0.0
    numeric = float(value)
    return max(-1.0, min(1.0, (numeric - 18.0) / 14.0))
