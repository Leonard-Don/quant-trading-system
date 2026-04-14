"""Policy execution disorder macro factor."""

from __future__ import annotations

from typing import Any, Dict

from .base_factor import MacroFactor


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class PolicyExecutionDisorderFactor(MacroFactor):
    """Captures department-level reversals, thin coverage and execution lag."""

    name = "policy_execution_disorder"
    default_threshold = 0.18

    def compute(self, data_context: Dict[str, Any]):
        policy_signal = data_context.get("signals", {}).get("policy_execution", {}) or {}
        departments = policy_signal.get("department_board") or []
        avg_score = _safe_float(policy_signal.get("score"))
        top_department_score = max([_safe_float(item.get("chaos_score")) for item in departments] or [0.0])
        chaos_ratio = _safe_float(policy_signal.get("chaotic_department_count")) / max(
            _safe_float(policy_signal.get("department_count"), len(departments) or 1),
            1.0,
        )
        degraded_ratio = len(policy_signal.get("degraded_departments") or []) / max(len(departments), 1)
        lagging_ratio = len(policy_signal.get("lagging_departments") or []) / max(len(departments), 1)
        source_mode_counts = (policy_signal.get("source_mode_summary") or {}).get("counts", {}) or {}
        derived_ratio = _safe_float(source_mode_counts.get("derived", 0)) / max(
            sum(int(value) for value in source_mode_counts.values()) or 1,
            1,
        )

        factor_value = max(
            -1.0,
            min(
                1.0,
                avg_score * 0.36
                + top_department_score * 0.24
                + chaos_ratio * 0.18
                + degraded_ratio * 0.14
                + lagging_ratio * 0.08
                + derived_ratio * 0.05,
            ),
        )
        confidence = min(
            0.94,
            _safe_float(policy_signal.get("confidence"), 0.45) * 0.65
            + min(len(departments) / 8.0, 1.0) * 0.15
            + (1.0 - min(derived_ratio, 1.0)) * 0.2,
        )
        history = [
            float(record.normalized_score)
            for record in data_context.get("records", [])
            if getattr(record.category, "value", "") == "policy_execution"
        ] or [0.04, 0.07, 0.11, 0.15]

        return self._build_result(
            value=factor_value,
            history=history,
            confidence=confidence,
            metadata={
                "department_count": int(policy_signal.get("department_count", len(departments)) or 0),
                "chaotic_department_count": int(policy_signal.get("chaotic_department_count", 0) or 0),
                "top_department_score": round(top_department_score, 4),
                "degraded_ratio": round(degraded_ratio, 4),
                "lagging_ratio": round(lagging_ratio, 4),
                "derived_ratio": round(derived_ratio, 4),
            },
        )
