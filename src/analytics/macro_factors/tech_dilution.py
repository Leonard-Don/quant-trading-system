"""
技术高管稀释度因子。
"""

from __future__ import annotations

from typing import Any, Dict, List

from .base_factor import MacroFactor


class TechDilutionFactor(MacroFactor):
    """从招聘结构中提炼技术稀释信号。"""

    name = "tech_dilution"
    default_threshold = 0.15

    def compute(self, data_context: Dict[str, Any]):
        supply_signal = data_context.get("signals", {}).get("supply_chain", {})
        dimensions = supply_signal.get("dimensions", {})
        talent_structure = float(dimensions.get("talent_structure", {}).get("score", 0.0))
        alert_count = float(supply_signal.get("alert_count", 0))
        alert_ratio = alert_count / max(1, float(supply_signal.get("record_count", 1)))
        hiring_records = [
            record
            for record in data_context.get("records", [])
            if getattr(record.category, "value", "") == "hiring"
        ]

        max_dilution_ratio = 0.0
        for record in hiring_records:
            raw_value = getattr(record, "raw_value", {})
            if isinstance(raw_value, dict):
                max_dilution_ratio = max(
                    max_dilution_ratio,
                    float(raw_value.get("dilution_ratio", 0.0)),
                )

        dilution_pressure = min(1.0, max(0.0, (max_dilution_ratio - 1.0) / 2.0))
        factor_value = max(
            -1.0,
            min(
                1.0,
                dilution_pressure * 0.6 + max(talent_structure, 0.0) * 0.25 + alert_ratio * 0.15,
            ),
        )
        confidence = min(1.0, 0.4 + min(0.4, len(hiring_records) * 0.03) + alert_ratio * 0.2)

        history = [
            float(record.normalized_score)
            for record in hiring_records
        ] or [0.0, 0.05, 0.08, 0.12]

        return self._build_result(
            value=factor_value,
            history=history,
            confidence=confidence,
            metadata={
                "max_dilution_ratio": round(max_dilution_ratio, 4),
                "alert_count": int(alert_count),
                "talent_structure_score": round(talent_structure, 4),
            },
        )
