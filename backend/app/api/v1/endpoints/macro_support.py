from __future__ import annotations

from typing import Any, Dict

from src.data.alternative import get_alt_data_manager
from src.data.data_manager import DataManager

_market_data_manager = DataManager()

FACTOR_WEIGHTS = {
    "bureaucratic_friction": 0.86,
    "tech_dilution": 0.78,
    "people_fragility": 0.84,
    "policy_execution_disorder": 0.82,
    "baseload_mismatch": 0.98,
    "rate_curve_pressure": 0.74,
    "credit_spread_stress": 0.74,
    "fx_mismatch": 0.7,
}

FACTOR_EVIDENCE_MAP = {
    "bureaucratic_friction": {
        "categories": {"policy", "bidding", "env_assessment"},
        "signal_keys": {"policy_radar", "supply_chain"},
    },
    "tech_dilution": {
        "categories": {"hiring"},
        "signal_keys": {"supply_chain", "people_layer"},
    },
    "people_fragility": {
        "categories": {"executive_governance", "insider_flow", "hiring"},
        "signal_keys": {"people_layer"},
    },
    "policy_execution_disorder": {
        "categories": {"policy_execution", "policy"},
        "signal_keys": {"policy_execution", "policy_radar"},
    },
    "baseload_mismatch": {
        "categories": {"commodity_inventory", "port_congestion", "customs", "bidding"},
        "signal_keys": {"macro_hf", "supply_chain"},
    },
    "rate_curve_pressure": {
        "categories": {"policy", "customs"},
        "signal_keys": {"policy_radar", "macro_hf"},
    },
    "credit_spread_stress": {
        "categories": {"port_congestion", "customs", "commodity_inventory"},
        "signal_keys": {"macro_hf"},
    },
    "fx_mismatch": {
        "categories": {"customs", "commodity_inventory"},
        "signal_keys": {"macro_hf"},
    },
}

SOURCE_TIER_RULES = [
    ("policy_radar:ndrc", ("official", 1.0)),
    ("policy_radar:nea", ("official", 0.95)),
    ("policy_execution:ndrc", ("official", 0.98)),
    ("policy_execution:nea", ("official", 0.94)),
    ("people_layer:executive_governance", ("corporate_governance", 0.78)),
    ("people_layer:insider_flow", ("market_disclosure", 0.74)),
    ("people_layer:hiring_structure", ("corporate_signal", 0.72)),
    ("macro_hf", ("market", 0.88)),
    ("supply_chain:bidding", ("public_procurement", 0.84)),
    ("supply_chain:env_assessment", ("regulatory_filing", 0.86)),
    ("supply_chain:hiring", ("corporate_signal", 0.72)),
]


def build_macro_context(refresh: bool = False):
    manager = get_alt_data_manager()
    snapshot = manager.get_dashboard_snapshot(refresh=refresh)
    return {
        "snapshot_timestamp": snapshot.get("snapshot_timestamp"),
        "snapshot": snapshot,
        "signals": snapshot.get("signals", {}),
        "records": manager.get_records(timeframe="45d", limit=200),
        "market_indicators": _market_data_manager.get_market_indicators(),
        "provider_status": snapshot.get("providers", {}),
        "refresh_status": snapshot.get("refresh_status", {}),
        "data_freshness": snapshot.get("staleness", {}),
        "provider_health": snapshot.get("provider_health", {}),
        "source_mode_summary": snapshot.get("source_mode_summary", {}),
    }


def build_macro_trend(current_overview, previous_overview):
    if not previous_overview:
        return {
            "previous_snapshot_timestamp": None,
            "macro_score_delta": 0.0,
            "macro_signal_changed": False,
            "factor_deltas": {},
        }

    previous_factors = {
        factor.get("name"): factor for factor in (previous_overview.get("factors") or [])
    }
    factor_deltas = {}
    for factor in current_overview.get("factors", []):
        previous = previous_factors.get(factor.get("name"), {})
        factor_deltas[factor.get("name")] = {
            "value_delta": round(float(factor.get("value", 0) or 0) - float(previous.get("value", 0) or 0), 4),
            "z_score_delta": round(float(factor.get("z_score", 0) or 0) - float(previous.get("z_score", 0) or 0), 4),
            "signal_changed": int(factor.get("signal", 0) or 0) != int(previous.get("signal", 0) or 0),
            "previous_signal": int(previous.get("signal", 0) or 0),
            "previous_z_score": round(float(previous.get("z_score", 0) or 0), 4),
        }

    return {
        "previous_snapshot_timestamp": previous_overview.get("snapshot_timestamp"),
        "macro_score_delta": round(
            float(current_overview.get("macro_score", 0) or 0)
            - float(previous_overview.get("macro_score", 0) or 0),
            4,
        ),
        "macro_signal_changed": int(current_overview.get("macro_signal", 0) or 0)
        != int(previous_overview.get("macro_signal", 0) or 0),
        "factor_deltas": factor_deltas,
    }


def build_resonance_summary(overview: Dict[str, Any]) -> Dict[str, Any]:
    trend = overview.get("trend", {})
    factor_deltas = trend.get("factor_deltas", {})
    positive_cluster = []
    negative_cluster = []
    weakening = []
    precursor = []
    reversed_factors = []
    momentum_map = {}

    for factor in overview.get("factors", []):
        name = factor.get("name", "")
        z_score = float(factor.get("z_score", 0.0) or 0.0)
        signal = int(factor.get("signal", 0) or 0)
        delta_meta = factor_deltas.get(name, {})
        z_delta = float(delta_meta.get("z_score_delta", 0.0) or 0.0)
        signal_changed = bool(delta_meta.get("signal_changed"))
        metadata = factor.get("metadata", {})
        evidence_summary = metadata.get("evidence_summary", {})
        reversal_level = metadata.get("reversal_level", "none")
        precursor_level = metadata.get("reversal_precursor_level", "none")
        confirmation = evidence_summary.get("cross_confirmation_summary", {})
        dominant_direction = confirmation.get("dominant_direction", "neutral")
        recent_evidence = evidence_summary.get("recent_evidence") or []
        recent_score = float(recent_evidence[0].get("normalized_score", 0.0) or 0.0) if recent_evidence else 0.0
        previous_score = (
            float(recent_evidence[1].get("normalized_score", 0.0) or 0.0)
            if len(recent_evidence) > 1
            else recent_score
        )
        evidence_delta = round(recent_score - previous_score, 4)
        momentum_map[name] = {
            "dominant_direction": dominant_direction,
            "evidence_delta": evidence_delta,
            "recent_score": round(recent_score, 4),
            "previous_score": round(previous_score, 4),
        }

        if reversal_level in {"medium", "high"}:
            reversed_factors.append(name)
            continue

        if precursor_level in {"medium", "high"}:
            precursor.append(name)

        positive_strengthening = (
            (signal == 1 and (z_delta >= 0.12 or (signal_changed and z_score >= 0.5)))
            or (dominant_direction == "positive" and evidence_delta >= 0.12 and recent_score >= 0.4)
        )
        negative_strengthening = (
            (signal == -1 and (z_delta <= -0.12 or (signal_changed and z_score <= -0.5)))
            or (dominant_direction == "negative" and evidence_delta <= -0.12 and recent_score <= -0.4)
        )
        fading_positive = dominant_direction == "positive" and evidence_delta <= -0.1
        fading_negative = dominant_direction == "negative" and evidence_delta >= 0.1

        if positive_strengthening:
            positive_cluster.append(name)
        elif negative_strengthening:
            negative_cluster.append(name)
        elif (signal != 0 and abs(z_delta) >= 0.1) or fading_positive or fading_negative:
            weakening.append(name)

    if len(reversed_factors) >= 1:
        label = "reversal_cluster"
        reason = "至少一个核心因子已经进入方向反转，当前宏观锚正在重定价"
    elif len(positive_cluster) >= 2:
        label = "bullish_cluster"
        reason = "多个宏观因子同时强化正向扭曲，形成上行共振"
    elif len(negative_cluster) >= 2:
        label = "bearish_cluster"
        reason = "多个宏观因子同时强化负向扭曲，形成下行共振"
    elif len(precursor) >= 2:
        label = "precursor_cluster"
        reason = "多个因子同时逼近反转临界区，应提高警惕"
    elif len(weakening) >= 2:
        label = "fading_cluster"
        reason = "多个因子同步衰减，共振正在减弱"
    else:
        label = "mixed"
        reason = "当前因子变化尚未形成明确共振"

    return {
        "label": label,
        "positive_cluster": positive_cluster,
        "negative_cluster": negative_cluster,
        "weakening": weakening,
        "precursor": precursor,
        "reversed_factors": reversed_factors,
        "factor_momentum": momentum_map,
        "reason": reason,
    }
