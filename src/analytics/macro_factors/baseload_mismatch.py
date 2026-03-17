"""
物理基荷错配因子。
"""

from __future__ import annotations

from typing import Any, Dict, List

from .base_factor import MacroFactor


class BaseloadMismatchFactor(MacroFactor):
    """衡量算力需求与能源/物流供给之间的张力。"""

    name = "baseload_mismatch"
    default_threshold = 0.18

    def compute(self, data_context: Dict[str, Any]):
        supply_signal = data_context.get("signals", {}).get("supply_chain", {})
        macro_signal = data_context.get("signals", {}).get("macro_hf", {})

        investment_activity = float(
            supply_signal.get("dimensions", {})
            .get("investment_activity", {})
            .get("score", 0.0)
        )
        project_pipeline = float(
            supply_signal.get("dimensions", {})
            .get("project_pipeline", {})
            .get("score", 0.0)
        )
        logistics_score = float(
            macro_signal.get("dimensions", {})
            .get("logistics", {})
            .get("score", 0.0)
        )
        inventory_score = float(
            macro_signal.get("dimensions", {})
            .get("inventory", {})
            .get("score", 0.0)
        )
        trade_score = float(
            macro_signal.get("dimensions", {})
            .get("trade", {})
            .get("score", 0.0)
        )

        demand_pressure = max(0.0, investment_activity) * 0.55 + max(0.0, trade_score) * 0.45
        supply_relief = max(0.0, project_pipeline) * 0.45 + max(0.0, inventory_score) * 0.35 + max(0.0, -logistics_score) * 0.20
        mismatch_value = max(-1.0, min(1.0, demand_pressure - supply_relief))
        confidence = min(1.0, 0.45 + macro_signal.get("confidence", 0.0) * 0.3 + supply_signal.get("confidence", 0.0) * 0.25)

        history = [
            float(record.normalized_score)
            for record in data_context.get("records", [])
            if getattr(record.category, "value", "") in {
                "commodity_inventory",
                "port_congestion",
                "bidding",
            }
        ] or [0.0, 0.06, 0.09, 0.14]

        return self._build_result(
            value=mismatch_value,
            history=history,
            confidence=confidence,
            metadata={
                "demand_pressure": round(demand_pressure, 4),
                "supply_relief": round(supply_relief, 4),
                "inventory_score": round(inventory_score, 4),
                "logistics_score": round(logistics_score, 4),
            },
        )
