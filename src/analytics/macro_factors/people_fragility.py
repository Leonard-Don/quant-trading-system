"""People fragility macro factor."""

from __future__ import annotations

from typing import Any, Dict, List

from .base_factor import MacroFactor


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class PeopleFragilityFactor(MacroFactor):
    """Elevates people-layer fragility into the formal macro factor engine."""

    name = "people_fragility"
    default_threshold = 0.22

    def compute(self, data_context: Dict[str, Any]):
        people_signal = data_context.get("signals", {}).get("people_layer", {}) or {}
        watchlist = people_signal.get("watchlist") or []
        avg_fragility = _safe_float(people_signal.get("avg_fragility_score"))
        avg_quality = _safe_float(people_signal.get("avg_quality_score"))
        fragile_company_count = int(people_signal.get("fragile_company_count", 0) or 0)
        company_count = int(people_signal.get("company_count", 0) or len(watchlist) or 0)
        fragile_ratio = fragile_company_count / max(company_count, 1)
        strongest_fragility = max(
            [_safe_float(item.get("people_fragility_score")) for item in watchlist] or [0.0]
        )
        source_mode_counts = (people_signal.get("source_mode_summary") or {}).get("counts", {}) or {}
        curated_ratio = _safe_float(source_mode_counts.get("curated", 0)) / max(
            sum(int(value) for value in source_mode_counts.values()) or 1,
            1,
        )

        factor_value = max(
            -1.0,
            min(
                1.0,
                avg_fragility * 0.42
                + strongest_fragility * 0.28
                + fragile_ratio * 0.18
                + curated_ratio * 0.08
                - avg_quality * 0.16,
            ),
        )
        confidence = min(
            0.95,
            _safe_float(people_signal.get("confidence"), 0.45) * 0.6
            + min(company_count / 10.0, 1.0) * 0.2
            + (1.0 - min(curated_ratio, 1.0)) * 0.2,
        )
        history = [
            float(record.normalized_score)
            for record in data_context.get("records", [])
            if getattr(record.category, "value", "") in {"executive_governance", "insider_flow", "hiring"}
        ] or [0.05, 0.08, 0.12, 0.16]

        return self._build_result(
            value=factor_value,
            history=history,
            confidence=confidence,
            metadata={
                "avg_fragility_score": round(avg_fragility, 4),
                "avg_quality_score": round(avg_quality, 4),
                "fragile_company_count": fragile_company_count,
                "company_count": company_count,
                "strongest_fragility_score": round(strongest_fragility, 4),
                "curated_ratio": round(curated_ratio, 4),
            },
        )
