"""
利率曲线压力因子。
"""

from __future__ import annotations

from typing import Any, Dict

from .base_factor import MacroFactor


class RateCurvePressureFactor(MacroFactor):
    """用长端利率与波动率近似刻画估值贴现压力。"""

    name = "rate_curve_pressure"
    default_threshold = 0.16

    def compute(self, data_context: Dict[str, Any]):
        indicators = data_context.get("market_indicators", {}) or {}
        policy_signal = data_context.get("signals", {}).get("policy_radar", {}) or {}
        trade_score = float(
            data_context.get("signals", {})
            .get("macro_hf", {})
            .get("dimensions", {})
            .get("trade", {})
            .get("score", 0.0)
        )

        ten_year_yield = _normalize_yield(indicators.get("10y_yield"))
        vix_level = _normalize_vix(indicators.get("vix"))
        policy_strength = float(policy_signal.get("strength", 0.0))
        factor_value = max(
            -1.0,
            min(
                1.0,
                ten_year_yield * 0.55 + vix_level * 0.25 + max(policy_strength, 0.0) * 0.1 + max(-trade_score, 0.0) * 0.1,
            ),
        )
        confidence = min(
            1.0,
            0.45
            + (0.2 if indicators.get("10y_yield") is not None else 0.0)
            + (0.15 if indicators.get("vix") is not None else 0.0)
            + float(policy_signal.get("confidence", 0.0)) * 0.2,
        )

        history = [0.0, 0.06, 0.12, 0.18]
        return self._build_result(
            value=factor_value,
            history=history,
            confidence=confidence,
            metadata={
                "ten_year_yield": indicators.get("10y_yield"),
                "vix": indicators.get("vix"),
                "policy_strength": round(policy_strength, 4),
                "trade_score": round(trade_score, 4),
            },
        )


def _normalize_yield(value: Any) -> float:
    if value is None:
        return 0.0
    numeric = float(value)
    if abs(numeric) > 20:
        numeric = numeric / 10.0
    return max(-1.0, min(1.0, (numeric - 4.0) / 2.5))


def _normalize_vix(value: Any) -> float:
    if value is None:
        return 0.0
    numeric = float(value)
    return max(-1.0, min(1.0, (numeric - 18.0) / 14.0))
