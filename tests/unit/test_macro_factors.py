from datetime import datetime

from src.analytics.macro_factors import FactorCombiner, build_default_registry
from src.data.alternative.base_alt_provider import AltDataCategory, AltDataRecord


def _record(category: AltDataCategory, score: float, raw_value=None):
    return AltDataRecord(
        timestamp=datetime(2026, 3, 17, 0, 0, 0),
        source="test",
        category=category,
        raw_value=raw_value or {},
        normalized_score=score,
        confidence=0.7,
    )


def test_macro_factor_registry_and_combiner():
    context = {
        "signals": {
            "policy_radar": {
                "strength": 0.6,
                "confidence": 0.7,
                "industry_signals": {
                    "AI算力": {"avg_impact": 0.5},
                    "电网": {"avg_impact": -0.2},
                },
            },
            "supply_chain": {
                "record_count": 6,
                "alert_count": 2,
                "confidence": 0.65,
                "dimensions": {
                    "investment_activity": {"score": 0.55},
                    "project_pipeline": {"score": 0.2},
                    "talent_structure": {"score": 0.45},
                },
            },
            "macro_hf": {
                "confidence": 0.6,
                "dimensions": {
                    "inventory": {"score": 0.25},
                    "trade": {"score": 0.35},
                    "logistics": {"score": 0.1},
                },
            },
        },
        "records": [
            _record(AltDataCategory.POLICY, 0.3),
            _record(AltDataCategory.HIRING, 0.5, {"dilution_ratio": 1.8}),
            _record(AltDataCategory.BIDDING, 0.4),
            _record(AltDataCategory.COMMODITY_INVENTORY, 0.25),
            _record(AltDataCategory.PORT_CONGESTION, 0.1),
        ],
    }

    registry = build_default_registry()
    results = registry.compute_all(context)
    combined = FactorCombiner().combine(results)

    factor_names = {result.name for result in results}
    assert len(results) == 6
    assert {"bureaucratic_friction", "tech_dilution", "baseload_mismatch", "rate_curve_pressure", "credit_spread_stress", "fx_mismatch"} <= factor_names
    assert combined["signal"] in {-1, 0, 1}
    assert combined["score"] != 0
    assert all("metadata" in result.to_dict() for result in results)
