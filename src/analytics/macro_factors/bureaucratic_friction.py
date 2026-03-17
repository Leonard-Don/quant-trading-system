"""
外行干预度因子。
"""

from __future__ import annotations

from typing import Any, Dict, List

from .base_factor import MacroFactor


class BureaucraticFrictionFactor(MacroFactor):
    """量化政策噪音和产业链扭曲的综合程度。"""

    name = "bureaucratic_friction"
    default_threshold = 0.2

    def compute(self, data_context: Dict[str, Any]):
        policy_signal = data_context.get("signals", {}).get("policy_radar", {})
        supply_signal = data_context.get("signals", {}).get("supply_chain", {})

        policy_strength = float(policy_signal.get("strength", 0.0))
        policy_confidence = float(policy_signal.get("confidence", 0.0))
        industry_dispersion = _industry_dispersion(
            policy_signal.get("industry_signals", {})
        )
        alert_ratio = _safe_ratio(
            supply_signal.get("alert_count", 0),
            supply_signal.get("record_count", 0),
        )
        investment_activity = float(
            supply_signal.get("dimensions", {})
            .get("investment_activity", {})
            .get("score", 0.0)
        )

        friction_value = max(
            -1.0,
            min(
                1.0,
                policy_strength * 0.35
                + industry_dispersion * 0.35
                + alert_ratio * 0.2
                + abs(investment_activity) * 0.1,
            ),
        )
        confidence = min(1.0, 0.45 + policy_confidence * 0.35 + alert_ratio * 0.2)

        history = _collect_history(
            data_context,
            "policy",
            default=[0.0, 0.1, 0.05, 0.15],
        )
        return self._build_result(
            value=friction_value,
            history=history,
            confidence=confidence,
            metadata={
                "policy_strength": round(policy_strength, 4),
                "industry_dispersion": round(industry_dispersion, 4),
                "alert_ratio": round(alert_ratio, 4),
            },
        )


def _industry_dispersion(industry_signals: Dict[str, Dict[str, Any]]) -> float:
    if not industry_signals:
        return 0.0
    scores = [abs(float(item.get("avg_impact", 0.0))) for item in industry_signals.values()]
    return sum(scores) / len(scores)


def _collect_history(
    data_context: Dict[str, Any],
    category: str,
    default: List[float],
) -> List[float]:
    records = data_context.get("records", [])
    values = [
        float(record.normalized_score)
        for record in records
        if getattr(record.category, "value", "") == category
    ]
    return values or default


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0
