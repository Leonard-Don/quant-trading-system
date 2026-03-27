"""
宏观错误定价因子 API。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List

from fastapi import APIRouter, HTTPException, Query

from src.analytics.macro_factors import FactorCombiner, MacroHistoryStore, build_default_registry
from src.data.alternative import get_alt_data_manager
from src.data.alternative.entity_resolution import aggregate_entities, resolve_entity

logger = logging.getLogger(__name__)
router = APIRouter()

_registry = build_default_registry()
_combiner = FactorCombiner()
_history_store = MacroHistoryStore()

FACTOR_WEIGHTS = {
    "bureaucratic_friction": 1.0,
    "tech_dilution": 0.9,
    "baseload_mismatch": 1.1,
}


def _build_context(refresh: bool = False):
    manager = get_alt_data_manager()
    snapshot = manager.get_dashboard_snapshot(refresh=refresh)
    return {
        "snapshot_timestamp": snapshot.get("snapshot_timestamp"),
        "signals": snapshot.get("signals", {}),
        "records": manager.get_records(timeframe="30d", limit=200),
        "provider_status": snapshot.get("providers", {}),
        "refresh_status": snapshot.get("refresh_status", {}),
        "data_freshness": snapshot.get("staleness", {}),
        "provider_health": snapshot.get("provider_health", {}),
    }


def _build_macro_trend(current_overview, previous_overview):
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


def _build_resonance_summary(overview: Dict[str, Any]) -> Dict[str, Any]:
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


FACTOR_EVIDENCE_MAP = {
    "bureaucratic_friction": {
        "categories": {"policy", "bidding", "env_assessment"},
        "signal_keys": {"policy_radar", "supply_chain"},
    },
    "tech_dilution": {
        "categories": {"hiring"},
        "signal_keys": {"supply_chain"},
    },
    "baseload_mismatch": {
        "categories": {"commodity_inventory", "port_congestion", "customs", "bidding"},
        "signal_keys": {"macro_hf", "supply_chain"},
    },
}

SOURCE_TIER_RULES = [
    ("policy_radar:ndrc", ("official", 1.0)),
    ("policy_radar:nea", ("official", 0.95)),
    ("macro_hf", ("market", 0.88)),
    ("supply_chain:bidding", ("public_procurement", 0.84)),
    ("supply_chain:env_assessment", ("regulatory_filing", 0.86)),
    ("supply_chain:hiring", ("corporate_signal", 0.72)),
]


def _record_headline(record) -> str:
    raw = getattr(record, "raw_value", {})
    if isinstance(raw, dict):
        return (
            raw.get("title")
            or raw.get("company")
            or raw.get("ticker")
            or raw.get("source_name")
            or getattr(record, "source", "")
        )
    return getattr(record, "source", "")


def _record_excerpt(record) -> str:
    raw = getattr(record, "raw_value", {})
    category = getattr(getattr(record, "category", None), "value", "")
    if not isinstance(raw, dict):
        return ""
    if category == "policy":
        return (
            f"policy_shift={float(raw.get('policy_shift', 0.0)):.2f}; "
            f"will_intensity={float(raw.get('will_intensity', 0.0)):.2f}"
        )
    if category == "hiring":
        return (
            f"{raw.get('company', raw.get('ticker', ''))} "
            f"dilution_ratio={float(raw.get('dilution_ratio', 0.0)):.2f}; "
            f"signal={raw.get('signal', 'neutral')}"
        ).strip()
    if category == "bidding":
        return f"{raw.get('industry', raw.get('industry_id', ''))} amount={raw.get('amount', 0)}"
    return str(raw.get("summary") or raw.get("title") or raw.get("message") or "")[:160]


def _record_facts(record) -> Dict[str, Any]:
    raw = getattr(record, "raw_value", {})
    category = getattr(getattr(record, "category", None), "value", "")
    if not isinstance(raw, dict):
        return {}
    if category == "policy":
        return {
            "policy_shift": round(float(raw.get("policy_shift", 0.0) or 0.0), 4),
            "will_intensity": round(float(raw.get("will_intensity", 0.0) or 0.0), 4),
        }
    if category == "hiring":
        return {
            "company": raw.get("company", ""),
            "dilution_ratio": round(float(raw.get("dilution_ratio", 0.0) or 0.0), 4),
            "signal": raw.get("signal", ""),
        }
    if category == "bidding":
        return {
            "industry": raw.get("industry", "") or raw.get("industry_id", ""),
            "amount": raw.get("amount", 0),
        }
    return {key: raw.get(key) for key in list(raw.keys())[:3]}


def _build_freshness_meta(timestamp: datetime) -> Dict[str, Any]:
    age_hours = max((datetime.now() - timestamp).total_seconds() / 3600, 0.0)
    if age_hours <= 24:
        label = "fresh"
        weight = 1.0
    elif age_hours <= 24 * 3:
        label = "recent"
        weight = 0.75
    elif age_hours <= 24 * 7:
        label = "aging"
        weight = 0.5
    else:
        label = "stale"
        weight = 0.25
    return {
        "age_hours": round(age_hours, 2),
        "label": label,
        "weight": weight,
    }


def _infer_source_tier(source: str) -> Dict[str, Any]:
    normalized = str(source or "").lower()
    for prefix, (tier, trust_score) in SOURCE_TIER_RULES:
        if normalized.startswith(prefix):
            return {"tier": tier, "trust_score": trust_score}
    return {"tier": "derived", "trust_score": 0.65}


def _build_factor_evidence(
    factor_name: str,
    context: Dict[str, Any],
    limit: int = 3,
) -> Dict[str, Any]:
    evidence_config = FACTOR_EVIDENCE_MAP.get(factor_name, {})
    categories = set(evidence_config.get("categories", set()))
    signal_keys = set(evidence_config.get("signal_keys", set()))
    records = [
        record
        for record in context.get("records", [])
        if getattr(getattr(record, "category", None), "value", "") in categories
    ]
    ordered = sorted(records, key=lambda item: getattr(item, "timestamp", None), reverse=True)
    sources = sorted({getattr(record, "source", "") for record in ordered if getattr(record, "source", "")})

    signal_evidence = []
    for key in signal_keys:
        signal = context.get("signals", {}).get(key, {})
        if signal:
            signal_evidence.append(
                {
                    "signal": key,
                    "strength": round(float(signal.get("strength", 0.0) or 0.0), 4),
                    "confidence": round(float(signal.get("confidence", 0.0) or 0.0), 4),
                    "record_count": int(signal.get("record_count", 0) or 0),
                }
            )

    evidence_rows = []
    for record in ordered[: max(limit * 3, limit)]:
        entity = resolve_entity(
            getattr(record, "raw_value", {}),
            getattr(record, "tags", []),
            _record_headline(record),
        )
        freshness = _build_freshness_meta(record.timestamp)
        source_meta = _infer_source_tier(record.source)
        evidence_rows.append(
            {
                "timestamp": record.timestamp.isoformat(),
                "source": record.source,
                "category": record.category.value,
                "headline": _record_headline(record),
                "excerpt": _record_excerpt(record),
                "facts": _record_facts(record),
                "canonical_entity": entity.get("canonical", ""),
                "entity_type": entity.get("entity_type", ""),
                "source_tier": source_meta["tier"],
                "trust_score": source_meta["trust_score"],
                "age_hours": freshness["age_hours"],
                "freshness_label": freshness["label"],
                "freshness_weight": freshness["weight"],
                "normalized_score": round(float(record.normalized_score), 4),
                "confidence": round(float(record.confidence), 4),
            }
        )
    recent_evidence = evidence_rows[:limit]

    weighted_score = round(
        sum(
            float(item.get("trust_score", 0.0))
            * float(item.get("freshness_weight", 0.0))
            * float(item.get("confidence", 0.0))
            for item in evidence_rows
        ),
        4,
    )
    conflict_summary = _build_conflict_summary(evidence_rows)
    conflict_trend = _build_conflict_trend(evidence_rows)
    coverage_summary = _build_coverage_summary(categories, signal_keys, ordered, signal_evidence)
    stability_summary = _build_stability_summary(ordered)
    lag_summary = _build_lag_summary({"recent_evidence": recent_evidence, "freshness_label": recent_evidence[0]["freshness_label"] if recent_evidence else "stale"})
    concentration_summary = _build_concentration_summary(evidence_rows)
    source_drift_summary = _build_source_drift_summary(evidence_rows)
    source_gap_summary = _build_source_gap_summary(ordered)
    cross_confirmation_summary = _build_cross_confirmation_summary(evidence_rows)
    source_dominance_summary = _build_source_dominance_summary(evidence_rows)
    consistency_summary = _build_consistency_summary(evidence_rows)
    reversal_summary = _build_reversal_summary(ordered)
    reversal_precursor_summary = _build_reversal_precursor_summary(reversal_summary)
    policy_source_health_summary = _build_policy_source_health_summary(context, signal_keys)

    return {
        "source_count": len(sources),
        "sources": sources[:6],
        "record_count": len(ordered),
        "categories": sorted(categories),
        "latest_timestamp": ordered[0].timestamp.isoformat() if ordered else "",
        "recent_evidence": recent_evidence,
        "signal_evidence": signal_evidence,
        "top_entities": aggregate_entities(
            [
                {
                    "timestamp": record.timestamp.isoformat(),
                    "canonical_entity": resolve_entity(
                        getattr(record, "raw_value", {}),
                        getattr(record, "tags", []),
                        _record_headline(record),
                    ).get("canonical", ""),
                    "entity_type": resolve_entity(
                        getattr(record, "raw_value", {}),
                        getattr(record, "tags", []),
                        _record_headline(record),
                    ).get("entity_type", ""),
                }
                for record in ordered[: limit * 3]
            ],
            limit=4,
        ),
        "official_source_count": len([source for source in sources if _infer_source_tier(source)["tier"] == "official"]),
        "weighted_evidence_score": weighted_score,
        "freshness_label": recent_evidence[0]["freshness_label"] if recent_evidence else "stale",
        "conflict_count": conflict_summary["conflict_count"],
        "conflict_level": conflict_summary["conflict_level"],
        "conflicts": conflict_summary["conflicts"],
        "conflict_trend": conflict_trend["trend"],
        "conflict_trend_reason": conflict_trend["reason"],
        "recent_conflict_count": conflict_trend["recent_conflict_count"],
        "previous_conflict_count": conflict_trend["previous_conflict_count"],
        "coverage_summary": coverage_summary,
        "stability_summary": stability_summary,
        "lag_summary": lag_summary,
        "concentration_summary": concentration_summary,
        "source_drift_summary": source_drift_summary,
        "source_gap_summary": source_gap_summary,
        "cross_confirmation_summary": cross_confirmation_summary,
        "source_dominance_summary": source_dominance_summary,
        "consistency_summary": consistency_summary,
        "reversal_summary": reversal_summary,
        "reversal_precursor_summary": reversal_precursor_summary,
        "policy_source_health_summary": policy_source_health_summary,
    }


def _build_overall_evidence(context: Dict[str, Any]) -> Dict[str, Any]:
    records = context.get("records", [])
    ordered = sorted(records, key=lambda item: getattr(item, "timestamp", None), reverse=True)
    sources = sorted({getattr(record, "source", "") for record in ordered if getattr(record, "source", "")})
    freshness = _build_freshness_meta(ordered[0].timestamp) if ordered else {"label": "stale"}
    evidence_rows = []
    for record in ordered[:16]:
        entity = resolve_entity(
            getattr(record, "raw_value", {}),
            getattr(record, "tags", []),
            _record_headline(record),
        )
        source_meta = _infer_source_tier(record.source)
        evidence_rows.append(
            {
                "source": record.source,
                "category": record.category.value,
                "headline": _record_headline(record),
                "canonical_entity": entity.get("canonical", ""),
                "entity_type": entity.get("entity_type", ""),
                "normalized_score": round(float(record.normalized_score), 4),
                "confidence": round(float(record.confidence), 4),
            }
        )
    conflict_summary = _build_conflict_summary(evidence_rows)
    conflict_trend = _build_conflict_trend(evidence_rows)
    policy_source_health_summary = _build_policy_source_health_summary(context, {"policy_radar"})
    return {
        "record_count": len(ordered),
        "source_count": len(sources),
        "latest_timestamp": ordered[0].timestamp.isoformat() if ordered else "",
        "top_sources": sources[:8],
        "official_source_count": len([source for source in sources if _infer_source_tier(source)["tier"] == "official"]),
        "freshness_label": freshness["label"],
        "conflict_count": conflict_summary["conflict_count"],
        "conflict_level": conflict_summary["conflict_level"],
        "conflicts": conflict_summary["conflicts"],
        "conflict_trend": conflict_trend["trend"],
        "conflict_trend_reason": conflict_trend["reason"],
        "recent_conflict_count": conflict_trend["recent_conflict_count"],
        "previous_conflict_count": conflict_trend["previous_conflict_count"],
        "policy_source_health_summary": policy_source_health_summary,
    }


def _build_policy_source_health_summary(
    context: Dict[str, Any],
    signal_keys: set[str],
) -> Dict[str, Any]:
    if "policy_radar" not in signal_keys:
        return {"label": "unknown", "reason": "", "sources": [], "fragile_sources": [], "watch_sources": []}

    signal = context.get("signals", {}).get("policy_radar", {}) or {}
    source_health = signal.get("source_health", {}) or {}
    if not source_health:
        return {"label": "unknown", "reason": "", "sources": [], "fragile_sources": [], "watch_sources": []}

    fragile_sources = sorted([name for name, meta in source_health.items() if meta.get("level") == "fragile"])
    watch_sources = sorted([name for name, meta in source_health.items() if meta.get("level") == "watch"])
    healthy_sources = sorted([name for name, meta in source_health.items() if meta.get("level") == "healthy"])
    avg_full_text_ratio = (
        sum(float(meta.get("full_text_ratio", 0.0) or 0.0) for meta in source_health.values()) / len(source_health)
        if source_health
        else 0.0
    )

    if fragile_sources:
        label = "fragile"
        reason = f"正文抓取脆弱源 {', '.join(fragile_sources[:3])}"
    elif watch_sources or avg_full_text_ratio < 0.7:
        label = "watch"
        if watch_sources:
            reason = f"正文抓取需关注 {', '.join(watch_sources[:3])}"
        else:
            reason = f"平均正文覆盖偏低 {round(avg_full_text_ratio * 100, 1)}%"
    else:
        label = "healthy"
        reason = f"主要政策源正文覆盖稳定，健康源 {', '.join(healthy_sources[:3])}"

    return {
        "label": label,
        "reason": reason,
        "sources": sorted(source_health.keys()),
        "fragile_sources": fragile_sources,
        "watch_sources": watch_sources,
        "healthy_sources": healthy_sources,
        "avg_full_text_ratio": round(avg_full_text_ratio, 4),
        "details": source_health,
    }


def _calculate_confidence_penalty(evidence_summary: Dict[str, Any]) -> Dict[str, Any]:
    conflict_level = evidence_summary.get("conflict_level", "none")
    conflict_trend = evidence_summary.get("conflict_trend", "stable")
    strongest_conflict = (evidence_summary.get("conflicts") or [{}])[0]
    source_pattern = strongest_conflict.get("source_pattern", "")
    stability_summary = evidence_summary.get("stability_summary", {})
    lag_summary = evidence_summary.get("lag_summary", {})
    concentration_summary = evidence_summary.get("concentration_summary", {})
    source_drift_summary = evidence_summary.get("source_drift_summary", {})
    source_gap_summary = evidence_summary.get("source_gap_summary", {})
    source_dominance_summary = evidence_summary.get("source_dominance_summary", {})
    consistency_summary = evidence_summary.get("consistency_summary", {})
    reversal_summary = evidence_summary.get("reversal_summary", {})
    reversal_precursor_summary = evidence_summary.get("reversal_precursor_summary", {})
    policy_source_health_summary = evidence_summary.get("policy_source_health_summary", {})

    penalty = 0.0
    reasons = []
    if conflict_level == "low":
        penalty += 0.06
    elif conflict_level == "medium":
        penalty += 0.14
    elif conflict_level == "high":
        penalty += 0.24

    if source_pattern == "official_vs_derived":
        penalty += 0.04
        reasons.append("官方源与派生源冲突")
    elif source_pattern == "official_split":
        penalty += 0.08
        reasons.append("官方源内部冲突")
    elif source_pattern == "derived_split":
        penalty += 0.02
        reasons.append("派生源内部冲突")

    if conflict_trend == "rising":
        penalty += 0.05
        reasons.append("证据分裂正在加剧")
    elif conflict_trend == "easing":
        penalty += 0.02
        reasons.append("证据分裂仍未完全收敛")

    if stability_summary.get("label") == "unstable":
        penalty += 0.07
        reasons.append("因子时序抖动过大")
    elif stability_summary.get("label") == "choppy":
        penalty += 0.03
        reasons.append("因子近期波动偏大")

    if lag_summary.get("level") == "high":
        penalty += 0.08
        reasons.append("关键证据已经过时")
    elif lag_summary.get("level") == "medium":
        penalty += 0.04
        reasons.append("关键证据正在失去时效")
    elif lag_summary.get("level") == "low":
        penalty += 0.015
        reasons.append("关键证据开始老化")

    if concentration_summary.get("label") == "high":
        penalty += 0.05
        reasons.append("证据过度集中")
    elif concentration_summary.get("label") == "medium":
        penalty += 0.025
        reasons.append("证据来源偏集中")

    if source_drift_summary.get("label") == "degrading":
        penalty += 0.05
        reasons.append("来源结构正在退化")

    if source_gap_summary.get("label") == "broken":
        penalty += 0.06
        reasons.append("证据流疑似断档")
    elif source_gap_summary.get("label") == "stretching":
        penalty += 0.03
        reasons.append("证据更新节奏放缓")

    if source_dominance_summary.get("label") == "rotating":
        penalty += 0.03
        reasons.append("来源主导权正在切换")
    elif source_dominance_summary.get("label") == "derived_dominant":
        penalty += 0.035
        reasons.append("当前结论主要由派生源主导")

    if consistency_summary.get("label") == "divergent":
        penalty += 0.04
        reasons.append("多源对结论强弱判断分歧较大")

    if reversal_summary.get("label") == "reversed":
        penalty += 0.06
        reasons.append("因子主方向已经反转")
    elif reversal_summary.get("label") == "fading":
        penalty += 0.025
        reasons.append("因子原有方向正在衰减")

    if reversal_precursor_summary.get("label") == "high":
        penalty += 0.03
        reasons.append("因子已逼近反转临界区")
    elif reversal_precursor_summary.get("label") == "medium":
        penalty += 0.015
        reasons.append("因子存在反转前兆")

    if policy_source_health_summary.get("label") == "fragile":
        penalty += 0.06
        reasons.append("政策源正文抓取脆弱")
    elif policy_source_health_summary.get("label") == "watch":
        penalty += 0.03
        reasons.append("政策源正文覆盖下降")

    penalty = min(round(penalty, 4), 0.4)
    if not reasons:
        reasons.append("证据一致性良好")
    return {
        "penalty": penalty,
        "reason": "；".join(reasons),
    }


def _calculate_confidence_support_bonus(evidence_summary: Dict[str, Any]) -> Dict[str, Any]:
    bonus = 0.0
    reasons = []
    coverage_summary = evidence_summary.get("coverage_summary", {})
    cross_confirmation_summary = evidence_summary.get("cross_confirmation_summary", {})
    consistency_summary = evidence_summary.get("consistency_summary", {})
    policy_source_health_summary = evidence_summary.get("policy_source_health_summary", {})

    if evidence_summary.get("conflict_level", "none") == "none":
        bonus += 0.03
        reasons.append("证据一致性良好")

    if int(evidence_summary.get("official_source_count", 0) or 0) >= 1:
        bonus += 0.04
        reasons.append("存在官方源支持")

    if float(evidence_summary.get("weighted_evidence_score", 0.0) or 0.0) >= 0.9:
        bonus += 0.03
        reasons.append("加权证据分较高")

    freshness_label = evidence_summary.get("freshness_label", "stale")
    if freshness_label == "fresh":
        bonus += 0.03
        reasons.append("证据新鲜度高")
    elif freshness_label == "recent":
        bonus += 0.015
        reasons.append("证据仍较新")

    coverage_ratio = float(coverage_summary.get("overall_coverage_ratio", 0.0) or 0.0)
    if coverage_ratio >= 0.8:
        bonus += 0.03
        reasons.append("关键维度覆盖充分")
    elif coverage_ratio >= 0.55:
        bonus += 0.015
        reasons.append("关键维度覆盖尚可")

    if cross_confirmation_summary.get("label") == "strong":
        bonus += 0.04
        reasons.append("同向结论已获跨源独立确认")
    elif cross_confirmation_summary.get("label") == "moderate":
        bonus += 0.02
        reasons.append("同向结论已有跨源侧证")

    if consistency_summary.get("label") == "strong":
        bonus += 0.02
        reasons.append("多源对结论强弱判断一致")
    elif consistency_summary.get("label") == "moderate":
        bonus += 0.01
        reasons.append("多源对结论强弱大体一致")

    if policy_source_health_summary.get("label") == "healthy":
        bonus += 0.02
        reasons.append("政策源正文覆盖稳定")

    bonus = min(round(bonus, 4), 0.15)
    if not reasons:
        reasons.append("缺少足够的正向证据强化")
    return {
        "bonus": bonus,
        "reason": "；".join(reasons),
    }


def _build_coverage_summary(
    categories: set,
    signal_keys: set,
    records: List[Any],
    signal_evidence: List[Dict[str, Any]],
) -> Dict[str, Any]:
    expected_categories = sorted(categories)
    covered_categories = sorted({
        getattr(getattr(record, "category", None), "value", "")
        for record in records
        if getattr(getattr(record, "category", None), "value", "") in categories
    })
    expected_signals = sorted(signal_keys)
    covered_signals = sorted({
        item.get("signal", "")
        for item in signal_evidence
        if item.get("signal") and int(item.get("record_count", 0) or 0) > 0
    })

    category_ratio = (
        round(len(covered_categories) / len(expected_categories), 4)
        if expected_categories else 1.0
    )
    signal_ratio = (
        round(len(covered_signals) / len(expected_signals), 4)
        if expected_signals else 1.0
    )
    overall_ratio = round((category_ratio + signal_ratio) / 2, 4)

    if overall_ratio >= 0.8:
        label = "strong"
    elif overall_ratio >= 0.55:
        label = "partial"
    elif overall_ratio > 0:
        label = "thin"
    else:
        label = "sparse"

    return {
        "expected_categories": expected_categories,
        "covered_categories": covered_categories,
        "missing_categories": [item for item in expected_categories if item not in covered_categories],
        "category_coverage_ratio": category_ratio,
        "expected_signals": expected_signals,
        "covered_signals": covered_signals,
        "missing_signals": [item for item in expected_signals if item not in covered_signals],
        "signal_coverage_ratio": signal_ratio,
        "overall_coverage_ratio": overall_ratio,
        "coverage_label": label,
    }


def _build_stability_summary(records: List[Any]) -> Dict[str, Any]:
    ordered = sorted(
        [record for record in records if getattr(record, "timestamp", None) is not None],
        key=lambda item: item.timestamp,
    )
    scores = [round(float(record.normalized_score or 0.0), 4) for record in ordered]
    if len(scores) < 2:
        return {
            "label": "stable",
            "avg_abs_delta": 0.0,
            "max_abs_delta": 0.0,
            "sign_flip_count": 0,
            "reason": "样本不足，默认稳定",
        }

    deltas = [abs(scores[index] - scores[index - 1]) for index in range(1, len(scores))]
    avg_abs_delta = round(sum(deltas) / len(deltas), 4)
    max_abs_delta = round(max(deltas), 4)

    sign_flip_count = 0
    previous_sign = 0
    for score in scores:
        if score >= 0.18:
            current_sign = 1
        elif score <= -0.18:
            current_sign = -1
        else:
            current_sign = 0
        if previous_sign and current_sign and current_sign != previous_sign:
            sign_flip_count += 1
        if current_sign:
            previous_sign = current_sign

    if sign_flip_count >= 2 or avg_abs_delta >= 0.45 or max_abs_delta >= 0.8:
        label = "unstable"
        reason = "近期分数跳变过大，且存在明显来回摆动"
    elif sign_flip_count >= 1 or avg_abs_delta >= 0.25 or max_abs_delta >= 0.45:
        label = "choppy"
        reason = "近期分数波动偏大，稳定性一般"
    else:
        label = "stable"
        reason = "近期分数变化平稳，可作为较稳定锚点"

    return {
        "label": label,
        "avg_abs_delta": avg_abs_delta,
        "max_abs_delta": max_abs_delta,
        "sign_flip_count": sign_flip_count,
        "reason": reason,
    }


def _build_lag_summary(evidence_summary: Dict[str, Any]) -> Dict[str, Any]:
    latest = (evidence_summary.get("recent_evidence") or [{}])[0]
    age_hours = float(latest.get("age_hours", 0.0) or 0.0)
    freshness_label = latest.get("freshness_label") or evidence_summary.get("freshness_label", "stale")

    if freshness_label == "fresh":
        level = "none"
        reason = "关键证据仍然新鲜，时效性良好"
    elif freshness_label == "recent":
        level = "low"
        reason = "关键证据开始变旧，应关注后续更新"
    elif freshness_label == "aging":
        level = "medium"
        reason = "关键证据已进入衰减期，定价时效明显下降"
    else:
        level = "high"
        reason = "关键证据已经陈旧，可能失去定价时效"

    return {
        "level": level,
        "age_hours": round(age_hours, 2),
        "freshness_label": freshness_label,
        "reason": reason,
    }


def _build_concentration_summary(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not evidence_items:
        return {
            "top_source": "",
            "top_source_share": 0.0,
            "top_entity": "",
            "top_entity_share": 0.0,
            "label": "low",
            "reason": "证据分布相对均衡",
        }

    total = len(evidence_items)
    source_counts: Dict[str, int] = {}
    entity_counts: Dict[str, int] = {}
    for item in evidence_items:
        source = item.get("source") or "unknown"
        entity = item.get("canonical_entity") or item.get("category") or "unknown"
        source_counts[source] = source_counts.get(source, 0) + 1
        entity_counts[entity] = entity_counts.get(entity, 0) + 1

    top_source, top_source_count = max(source_counts.items(), key=lambda pair: pair[1])
    top_entity, top_entity_count = max(entity_counts.items(), key=lambda pair: pair[1])
    top_source_share = round(top_source_count / total, 4)
    top_entity_share = round(top_entity_count / total, 4)

    if top_source_share >= 0.9 or top_entity_share >= 0.9:
        label = "high"
        reason = "证据高度集中在单一来源或单一实体上，存在单点偏置风险"
    elif top_source_share >= 0.7 or top_entity_share >= 0.75:
        label = "medium"
        reason = "证据分布偏集中，解读时需防止单源放大"
    else:
        label = "low"
        reason = "证据分布相对分散"

    return {
        "top_source": top_source,
        "top_source_share": top_source_share,
        "top_entity": top_entity,
        "top_entity_share": top_entity_share,
        "label": label,
        "reason": reason,
    }


def _build_source_drift_summary(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(evidence_items) < 2:
        return {
            "label": "stable",
            "recent_official_share": 0.0,
            "previous_official_share": 0.0,
            "recent_derived_share": 0.0,
            "previous_derived_share": 0.0,
            "reason": "样本不足，默认来源结构稳定",
        }

    midpoint = max(len(evidence_items) // 2, 1)
    recent = evidence_items[:midpoint]
    previous = evidence_items[midpoint:]
    if not previous:
        previous = recent

    def _share(rows: List[Dict[str, Any]], tier: str) -> float:
        if not rows:
            return 0.0
        return round(
            sum(1 for item in rows if item.get("source_tier") == tier) / len(rows),
            4,
        )

    recent_official = _share(recent, "official")
    previous_official = _share(previous, "official")
    recent_derived = _share(recent, "derived")
    previous_derived = _share(previous, "derived")

    official_drop = round(previous_official - recent_official, 4)
    derived_rise = round(recent_derived - previous_derived, 4)

    if official_drop >= 0.4 and derived_rise >= 0.25:
        label = "degrading"
        reason = "近期来源结构从官方/硬源明显退化到派生源支撑"
    elif recent_official - previous_official >= 0.3 and previous_derived - recent_derived >= 0.2:
        label = "improving"
        reason = "近期来源结构向官方/硬源回升"
    else:
        label = "stable"
        reason = "近期来源结构没有明显漂移"

    return {
        "label": label,
        "recent_official_share": recent_official,
        "previous_official_share": previous_official,
        "recent_derived_share": recent_derived,
        "previous_derived_share": previous_derived,
        "reason": reason,
    }


def _build_source_gap_summary(records: List[Any]) -> Dict[str, Any]:
    ordered = sorted(
        [record for record in records if getattr(record, "timestamp", None) is not None],
        key=lambda item: item.timestamp,
    )
    if len(ordered) < 3:
        return {
            "label": "stable",
            "latest_gap_hours": 0.0,
            "baseline_gap_hours": 0.0,
            "reason": "样本不足，默认无明显断流",
        }

    gap_hours = []
    for index in range(1, len(ordered)):
        gap = (ordered[index].timestamp - ordered[index - 1].timestamp).total_seconds() / 3600
        gap_hours.append(max(gap, 0.0))

    latest_gap = round(gap_hours[-1], 2)
    baseline_gaps = gap_hours[:-1] or gap_hours
    baseline_gap = round(sum(baseline_gaps) / len(baseline_gaps), 2)

    if latest_gap >= max(baseline_gap * 3, 72):
        label = "broken"
        reason = "最近证据更新间隔明显拉长，疑似出现来源断流"
    elif latest_gap >= max(baseline_gap * 2, 48):
        label = "stretching"
        reason = "最近证据更新开始变慢，应关注是否进入断流前兆"
    else:
        label = "stable"
        reason = "证据更新节奏稳定"

    return {
        "label": label,
        "latest_gap_hours": latest_gap,
        "baseline_gap_hours": baseline_gap,
        "reason": reason,
    }


def _build_cross_confirmation_summary(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    confirming_items = [
        item for item in evidence_items
        if abs(float(item.get("normalized_score", 0.0) or 0.0)) >= 0.18
        and float(item.get("confidence", 0.0) or 0.0) >= 0.55
    ]
    if not confirming_items:
        return {
            "label": "none",
            "dominant_direction": "neutral",
            "confirming_source_tiers": [],
            "confirming_categories": [],
            "confirming_source_count": 0,
            "reason": "缺少足够强的独立证据确认",
        }

    positive_score = sum(
        float(item.get("normalized_score", 0.0) or 0.0)
        for item in confirming_items
        if float(item.get("normalized_score", 0.0) or 0.0) > 0
    )
    negative_score = sum(
        abs(float(item.get("normalized_score", 0.0) or 0.0))
        for item in confirming_items
        if float(item.get("normalized_score", 0.0) or 0.0) < 0
    )
    dominant_direction = "positive" if positive_score >= negative_score else "negative"
    aligned_items = [
        item for item in confirming_items
        if (dominant_direction == "positive" and float(item.get("normalized_score", 0.0) or 0.0) > 0)
        or (dominant_direction == "negative" and float(item.get("normalized_score", 0.0) or 0.0) < 0)
    ]

    source_tiers = sorted({item.get("source_tier", "") for item in aligned_items if item.get("source_tier")})
    categories = sorted({item.get("category", "") for item in aligned_items if item.get("category")})
    sources = sorted({item.get("source", "") for item in aligned_items if item.get("source")})

    if len(source_tiers) >= 3 or (len(source_tiers) >= 2 and len(categories) >= 3):
        label = "strong"
        reason = "同向结论已被多类来源独立确认"
    elif len(source_tiers) >= 2 or len(categories) >= 2 or len(sources) >= 2:
        label = "moderate"
        reason = "同向结论已获得跨源侧证确认"
    else:
        label = "weak"
        reason = "当前结论主要依赖单一来源链条"

    return {
        "label": label,
        "dominant_direction": dominant_direction,
        "confirming_source_tiers": source_tiers,
        "confirming_categories": categories,
        "confirming_source_count": len(sources),
        "reason": reason,
    }


def _build_reversal_summary(records: List[Any]) -> Dict[str, Any]:
    ordered = sorted(
        [record for record in records if getattr(record, "timestamp", None) is not None],
        key=lambda item: item.timestamp,
    )
    if len(ordered) < 3:
        return {
            "label": "stable",
            "previous_direction": "neutral",
            "recent_direction": "neutral",
            "previous_avg_score": 0.0,
            "recent_avg_score": 0.0,
            "reason": "样本不足，无法判断方向反转",
        }

    midpoint = max(len(ordered) // 2, 1)
    previous_scores = [float(record.normalized_score or 0.0) for record in ordered[:midpoint]]
    recent_scores = [float(record.normalized_score or 0.0) for record in ordered[midpoint:]] or previous_scores

    previous_avg = round(sum(previous_scores) / len(previous_scores), 4) if previous_scores else 0.0
    recent_avg = round(sum(recent_scores) / len(recent_scores), 4) if recent_scores else 0.0

    def _direction(score: float) -> str:
        if score >= 0.18:
            return "positive"
        if score <= -0.18:
            return "negative"
        return "neutral"

    previous_direction = _direction(previous_avg)
    recent_direction = _direction(recent_avg)

    if previous_direction in {"positive", "negative"} and recent_direction in {"positive", "negative"} and previous_direction != recent_direction:
        label = "reversed"
        reason = "因子近期主方向已经发生反转"
    elif previous_direction in {"positive", "negative"} and recent_direction == "neutral":
        label = "fading"
        reason = "因子原有方向正在显著减弱"
    elif previous_direction == "neutral" and recent_direction in {"positive", "negative"}:
        label = "emerging"
        reason = "因子开始形成新的明确方向"
    else:
        label = "stable"
        reason = "因子主方向暂时稳定"

    return {
        "label": label,
        "previous_direction": previous_direction,
        "recent_direction": recent_direction,
        "previous_avg_score": previous_avg,
        "recent_avg_score": recent_avg,
        "reason": reason,
    }


def _build_reversal_precursor_summary(reversal_summary: Dict[str, Any]) -> Dict[str, Any]:
    previous_direction = reversal_summary.get("previous_direction", "neutral")
    recent_direction = reversal_summary.get("recent_direction", "neutral")
    previous_avg = abs(float(reversal_summary.get("previous_avg_score", 0.0) or 0.0))
    recent_avg = abs(float(reversal_summary.get("recent_avg_score", 0.0) or 0.0))

    if previous_direction in {"positive", "negative"} and recent_direction == previous_direction:
        weakening_ratio = round((previous_avg - recent_avg) / previous_avg, 4) if previous_avg > 0 else 0.0
        if recent_avg <= 0.22 and weakening_ratio >= 0.45:
            return {
                "label": "high",
                "weakening_ratio": weakening_ratio,
                "distance_to_zero": round(recent_avg, 4),
                "reason": "因子仍未翻向，但已快速逼近零轴，存在较强反转前兆",
            }
        if recent_avg <= 0.3 and weakening_ratio >= 0.3:
            return {
                "label": "medium",
                "weakening_ratio": weakening_ratio,
                "distance_to_zero": round(recent_avg, 4),
                "reason": "因子主方向明显衰减，正在接近反转临界区",
            }

    return {
        "label": "none",
        "weakening_ratio": 0.0,
        "distance_to_zero": round(recent_avg, 4),
        "reason": "暂未观察到明显反转前兆",
    }


def _build_consistency_summary(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    confirming = [
        item for item in evidence_items
        if abs(float(item.get("normalized_score", 0.0) or 0.0)) >= 0.18
        and float(item.get("confidence", 0.0) or 0.0) >= 0.55
    ]
    if len(confirming) < 2:
        return {
            "label": "unknown",
            "dominant_direction": "neutral",
            "dispersion": 0.0,
            "avg_strength": 0.0,
            "reason": "样本不足，无法判断结论强弱一致度",
        }

    positive_score = sum(
        float(item.get("normalized_score", 0.0) or 0.0)
        for item in confirming
        if float(item.get("normalized_score", 0.0) or 0.0) > 0
    )
    negative_score = sum(
        abs(float(item.get("normalized_score", 0.0) or 0.0))
        for item in confirming
        if float(item.get("normalized_score", 0.0) or 0.0) < 0
    )
    dominant_direction = "positive" if positive_score >= negative_score else "negative"
    aligned = [
        item for item in confirming
        if (dominant_direction == "positive" and float(item.get("normalized_score", 0.0) or 0.0) > 0)
        or (dominant_direction == "negative" and float(item.get("normalized_score", 0.0) or 0.0) < 0)
    ]
    strengths = [abs(float(item.get("normalized_score", 0.0) or 0.0)) for item in aligned]
    if len(strengths) < 2:
        return {
            "label": "weak",
            "dominant_direction": dominant_direction,
            "dispersion": 0.0,
            "avg_strength": round(sum(strengths) / len(strengths), 4) if strengths else 0.0,
            "reason": "仅有单一强证据支撑，结论一致度有限",
        }

    dispersion = round(max(strengths) - min(strengths), 4)
    avg_strength = round(sum(strengths) / len(strengths), 4)
    if dispersion <= 0.18:
        label = "strong"
        reason = "多源不仅同向，而且对结论强弱判断高度一致"
    elif dispersion <= 0.35:
        label = "moderate"
        reason = "多源总体同向，但对结论强弱仍存在一定分歧"
    else:
        label = "divergent"
        reason = "虽然多源同向，但对结论强弱判断分歧较大"

    return {
        "label": label,
        "dominant_direction": dominant_direction,
        "dispersion": dispersion,
        "avg_strength": avg_strength,
        "reason": reason,
    }


def _build_source_dominance_summary(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not evidence_items:
        return {
            "recent_dominant_tier": "",
            "previous_dominant_tier": "",
            "recent_share": 0.0,
            "previous_share": 0.0,
            "label": "stable",
            "reason": "缺少证据，无法判断来源主导权",
        }

    midpoint = max(len(evidence_items) // 2, 1)
    recent = evidence_items[:midpoint]
    previous = evidence_items[midpoint:] or evidence_items[:midpoint]

    def _tier_weights(rows: List[Dict[str, Any]]) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for item in rows:
            tier = item.get("source_tier") or "derived"
            weight = (
                abs(float(item.get("normalized_score", 0.0) or 0.0))
                * float(item.get("confidence", 0.0) or 0.0)
                * float(item.get("freshness_weight", 1.0) or 1.0)
                * float(item.get("trust_score", 0.65) or 0.65)
            )
            totals[tier] = totals.get(tier, 0.0) + weight
        return totals

    recent_weights = _tier_weights(recent)
    previous_weights = _tier_weights(previous)
    recent_total = sum(recent_weights.values()) or 1.0
    previous_total = sum(previous_weights.values()) or 1.0
    recent_dominant, recent_weight = max(recent_weights.items(), key=lambda pair: pair[1])
    previous_dominant, previous_weight = max(previous_weights.items(), key=lambda pair: pair[1])
    recent_share = round(recent_weight / recent_total, 4)
    previous_share = round(previous_weight / previous_total, 4)

    if recent_dominant != previous_dominant:
        label = "rotating"
        reason = f"结论主导权已从 {previous_dominant} 切换到 {recent_dominant}"
    elif recent_dominant == "derived" and recent_share >= 0.6:
        label = "derived_dominant"
        reason = "当前结论主要由派生源主导，应降低对硬锚的依赖"
    elif recent_dominant == "official" and recent_share >= 0.5:
        label = "official_dominant"
        reason = "当前结论仍由官方/硬源主导"
    else:
        label = "stable"
        reason = "当前来源主导权没有明显变化"

    return {
        "recent_dominant_tier": recent_dominant,
        "previous_dominant_tier": previous_dominant,
        "recent_share": recent_share,
        "previous_share": previous_share,
        "label": label,
        "reason": reason,
    }


def _calculate_blind_spot_warning(
    evidence_summary: Dict[str, Any],
    effective_confidence: float,
) -> Dict[str, Any]:
    coverage_summary = evidence_summary.get("coverage_summary", {})
    concentration_summary = evidence_summary.get("concentration_summary", {})
    coverage_label = coverage_summary.get("coverage_label", "sparse")
    missing_categories = coverage_summary.get("missing_categories", [])
    conflict_level = evidence_summary.get("conflict_level", "none")

    if coverage_label == "thin" and (
        effective_confidence >= 0.4 or concentration_summary.get("label") == "high"
    ):
        level = "medium"
        warning = True
        reason = "关键维度覆盖偏薄，但当前有效置信度仍偏高"
    elif coverage_label == "sparse" and effective_confidence >= 0.4:
        level = "high"
        warning = True
        reason = "关键维度覆盖稀疏，当前判断存在明显输入盲区"
    elif coverage_label in {"thin", "sparse"} and conflict_level == "none" and effective_confidence >= 0.45:
        level = "medium"
        warning = True
        reason = "证据虽然一致，但覆盖不足，可能存在盲区型过度自信"
    else:
        level = "none"
        warning = False
        reason = "输入覆盖与当前有效置信度基本匹配"

    return {
        "warning": warning,
        "level": level,
        "reason": reason,
        "missing_categories": missing_categories[:4],
    }


def _calculate_stability_warning(
    evidence_summary: Dict[str, Any],
    effective_confidence: float,
) -> Dict[str, Any]:
    stability_summary = evidence_summary.get("stability_summary", {})
    label = stability_summary.get("label", "stable")
    if label == "unstable" and effective_confidence >= 0.3:
        return {
            "warning": True,
            "level": "high",
            "reason": "因子近期来回摆动明显，暂时不适合直接作为定价锚",
        }
    if label == "choppy" and effective_confidence >= 0.45:
        return {
            "warning": True,
            "level": "medium",
            "reason": "因子近期波动偏大，使用时应降低锚定权重",
        }
    return {
        "warning": False,
        "level": "none",
        "reason": "因子时序稳定性可接受",
    }


def _calculate_lag_warning(
    evidence_summary: Dict[str, Any],
    effective_confidence: float,
) -> Dict[str, Any]:
    lag_summary = evidence_summary.get("lag_summary", {})
    level = lag_summary.get("level", "none")
    if level == "high" and effective_confidence >= 0.25:
        return {
            "warning": True,
            "level": "high",
            "reason": "关键证据已经陈旧，当前定价判断可能明显滞后",
        }
    if level == "medium" and effective_confidence >= 0.4:
        return {
            "warning": True,
            "level": "medium",
            "reason": "关键证据正在老化，当前定价判断可能开始滞后",
        }
    return {
        "warning": False,
        "level": "none",
        "reason": "证据时效性可接受",
    }


def _calculate_concentration_warning(
    evidence_summary: Dict[str, Any],
    effective_confidence: float,
) -> Dict[str, Any]:
    concentration_summary = evidence_summary.get("concentration_summary", {})
    label = concentration_summary.get("label", "low")
    if label == "high" and effective_confidence >= 0.35:
        return {
            "warning": True,
            "level": "high",
            "reason": "当前判断过度依赖单一来源或单一实体，存在集中偏置风险",
        }
    if label == "medium" and effective_confidence >= 0.5:
        return {
            "warning": True,
            "level": "medium",
            "reason": "当前判断存在一定来源集中度，建议结合更多侧证使用",
        }
    return {
        "warning": False,
        "level": "none",
        "reason": "证据集中度可接受",
    }


def _calculate_source_drift_warning(
    evidence_summary: Dict[str, Any],
    effective_confidence: float,
) -> Dict[str, Any]:
    drift_summary = evidence_summary.get("source_drift_summary", {})
    label = drift_summary.get("label", "stable")
    if label == "degrading" and effective_confidence >= 0.3:
        return {
            "warning": True,
            "level": "high",
            "reason": "当前判断的来源基础正在退化，应重新审视因子可信度",
        }
    if label == "improving" and effective_confidence >= 0.25:
        return {
            "warning": False,
            "level": "positive",
            "reason": "当前判断的来源基础正在改善",
        }
    return {
        "warning": False,
        "level": "none",
        "reason": "来源结构稳定",
    }


def _calculate_source_gap_warning(
    evidence_summary: Dict[str, Any],
    effective_confidence: float,
) -> Dict[str, Any]:
    gap_summary = evidence_summary.get("source_gap_summary", {})
    label = gap_summary.get("label", "stable")
    if label == "broken" and effective_confidence >= 0.25:
        return {
            "warning": True,
            "level": "high",
            "reason": "证据流疑似断档，当前判断可能建立在过期更新节奏上",
        }
    if label == "stretching" and effective_confidence >= 0.35:
        return {
            "warning": True,
            "level": "medium",
            "reason": "证据更新节奏明显放缓，应警惕来源断流风险",
        }
    return {
        "warning": False,
        "level": "none",
        "reason": "证据流更新节奏可接受",
    }


def _calculate_source_dominance_warning(
    evidence_summary: Dict[str, Any],
    effective_confidence: float,
) -> Dict[str, Any]:
    dominance_summary = evidence_summary.get("source_dominance_summary", {})
    label = dominance_summary.get("label", "stable")
    if label == "rotating" and effective_confidence >= 0.3:
        return {
            "warning": True,
            "level": "medium",
            "reason": "来源主导权正在切换，当前结论的支撑结构并不稳定",
        }
    if label == "derived_dominant" and effective_confidence >= 0.3:
        return {
            "warning": True,
            "level": "high",
            "reason": "当前结论主要由派生源主导，应主动下调硬锚信任度",
        }
    return {
        "warning": False,
        "level": "none",
        "reason": "来源主导权结构稳定",
    }


def _calculate_consistency_warning(
    evidence_summary: Dict[str, Any],
    effective_confidence: float,
) -> Dict[str, Any]:
    consistency_summary = evidence_summary.get("consistency_summary", {})
    label = consistency_summary.get("label", "unknown")
    if label == "divergent" and effective_confidence >= 0.25:
        return {
            "warning": True,
            "level": "high",
            "reason": "虽然多源同向，但对结论强弱分歧很大，不宜直接当作强定价锚",
        }
    return {
        "warning": False,
        "level": "none",
        "reason": "多源对结论强弱判断基本一致",
    }


def _calculate_reversal_warning(
    evidence_summary: Dict[str, Any],
    effective_confidence: float,
) -> Dict[str, Any]:
    reversal_summary = evidence_summary.get("reversal_summary", {})
    label = reversal_summary.get("label", "stable")
    if label == "reversed" and effective_confidence >= 0.15:
        return {
            "warning": True,
            "level": "high",
            "reason": "因子主方向已经反转，旧定价锚很可能失效",
        }
    if label == "fading" and effective_confidence >= 0.25:
        return {
            "warning": True,
            "level": "medium",
            "reason": "因子原有方向正在减弱，应降低锚定权重",
        }
    return {
        "warning": False,
        "level": "none",
        "reason": "因子主方向稳定",
    }


def _calculate_reversal_precursor_warning(
    evidence_summary: Dict[str, Any],
    effective_confidence: float,
) -> Dict[str, Any]:
    precursor_summary = evidence_summary.get("reversal_precursor_summary", {})
    label = precursor_summary.get("label", "none")
    if label == "high" and effective_confidence >= 0.2:
        return {
            "warning": True,
            "level": "high",
            "reason": "因子尚未翻向，但已快速接近零轴，存在明显反转前兆",
        }
    if label == "medium" and effective_confidence >= 0.25:
        return {
            "warning": True,
            "level": "medium",
            "reason": "因子方向正在衰减，需警惕反转前兆",
        }
    return {
        "warning": False,
        "level": "none",
        "reason": "暂未观察到明显反转前兆",
    }


def _apply_conflict_penalty(overview: Dict[str, Any]) -> Dict[str, Any]:
    adjusted_confidence = 0.0
    total_weight = 0.0
    penalized_count = 0
    boosted_count = 0
    blind_spot_count = 0
    unstable_count = 0
    concentrated_count = 0
    lagging_count = 0
    drifting_count = 0
    broken_flow_count = 0
    confirmed_count = 0
    dominance_shift_count = 0
    inconsistent_count = 0
    reversing_count = 0
    precursor_count = 0
    policy_source_fragile_count = 0

    for factor in overview.get("factors", []):
        factor.setdefault("metadata", {})
        evidence_summary = factor["metadata"].get("evidence_summary", {})
        raw_confidence = round(float(factor.get("confidence", 0.0) or 0.0), 4)
        penalty_meta = _calculate_confidence_penalty(evidence_summary)
        bonus_meta = _calculate_confidence_support_bonus(evidence_summary)
        effective_confidence = min(
            1.0,
            max(0.0, round(raw_confidence - penalty_meta["penalty"] + bonus_meta["bonus"], 4)),
        )
        factor["metadata"]["raw_confidence"] = raw_confidence
        factor["metadata"]["confidence_penalty"] = penalty_meta["penalty"]
        factor["metadata"]["effective_confidence"] = effective_confidence
        factor["metadata"]["confidence_penalty_reason"] = penalty_meta["reason"]
        factor["metadata"]["confidence_support_bonus"] = bonus_meta["bonus"]
        factor["metadata"]["confidence_support_reason"] = bonus_meta["reason"]
        blind_spot_meta = _calculate_blind_spot_warning(evidence_summary, effective_confidence)
        factor["metadata"]["blind_spot_warning"] = blind_spot_meta["warning"]
        factor["metadata"]["blind_spot_level"] = blind_spot_meta["level"]
        factor["metadata"]["blind_spot_reason"] = blind_spot_meta["reason"]
        factor["metadata"]["blind_spot_missing_categories"] = blind_spot_meta["missing_categories"]
        stability_meta = _calculate_stability_warning(evidence_summary, effective_confidence)
        factor["metadata"]["stability_warning"] = stability_meta["warning"]
        factor["metadata"]["stability_level"] = stability_meta["level"]
        factor["metadata"]["stability_reason"] = stability_meta["reason"]
        concentration_meta = _calculate_concentration_warning(evidence_summary, effective_confidence)
        factor["metadata"]["concentration_warning"] = concentration_meta["warning"]
        factor["metadata"]["concentration_level"] = concentration_meta["level"]
        factor["metadata"]["concentration_reason"] = concentration_meta["reason"]
        drift_meta = _calculate_source_drift_warning(evidence_summary, effective_confidence)
        factor["metadata"]["source_drift_warning"] = drift_meta["warning"]
        factor["metadata"]["source_drift_level"] = drift_meta["level"]
        factor["metadata"]["source_drift_reason"] = drift_meta["reason"]
        gap_meta = _calculate_source_gap_warning(evidence_summary, effective_confidence)
        factor["metadata"]["source_gap_warning"] = gap_meta["warning"]
        factor["metadata"]["source_gap_level"] = gap_meta["level"]
        factor["metadata"]["source_gap_reason"] = gap_meta["reason"]
        dominance_meta = _calculate_source_dominance_warning(evidence_summary, effective_confidence)
        factor["metadata"]["source_dominance_warning"] = dominance_meta["warning"]
        factor["metadata"]["source_dominance_level"] = dominance_meta["level"]
        factor["metadata"]["source_dominance_reason"] = dominance_meta["reason"]
        consistency_meta = _calculate_consistency_warning(evidence_summary, effective_confidence)
        factor["metadata"]["consistency_warning"] = consistency_meta["warning"]
        factor["metadata"]["consistency_level"] = consistency_meta["level"]
        factor["metadata"]["consistency_reason"] = consistency_meta["reason"]
        reversal_meta = _calculate_reversal_warning(evidence_summary, effective_confidence)
        factor["metadata"]["reversal_warning"] = reversal_meta["warning"]
        factor["metadata"]["reversal_level"] = reversal_meta["level"]
        factor["metadata"]["reversal_reason"] = reversal_meta["reason"]
        precursor_meta = _calculate_reversal_precursor_warning(evidence_summary, effective_confidence)
        factor["metadata"]["reversal_precursor_warning"] = precursor_meta["warning"]
        factor["metadata"]["reversal_precursor_level"] = precursor_meta["level"]
        factor["metadata"]["reversal_precursor_reason"] = precursor_meta["reason"]
        lag_meta = _calculate_lag_warning(evidence_summary, effective_confidence)
        factor["metadata"]["lag_warning"] = lag_meta["warning"]
        factor["metadata"]["lag_level"] = lag_meta["level"]
        factor["metadata"]["lag_reason"] = lag_meta["reason"]
        policy_source_health = evidence_summary.get("policy_source_health_summary", {})
        factor["metadata"]["policy_source_warning"] = policy_source_health.get("label") in {"watch", "fragile"}
        factor["metadata"]["policy_source_level"] = policy_source_health.get("label", "unknown")
        factor["metadata"]["policy_source_reason"] = policy_source_health.get("reason", "")
        factor["confidence"] = effective_confidence

        if penalty_meta["penalty"] > 0:
            penalized_count += 1
        if bonus_meta["bonus"] > 0:
            boosted_count += 1
        if evidence_summary.get("cross_confirmation_summary", {}).get("label") in {"strong", "moderate"}:
            confirmed_count += 1
        if blind_spot_meta["warning"]:
            blind_spot_count += 1
        if stability_meta["warning"]:
            unstable_count += 1
        if concentration_meta["warning"]:
            concentrated_count += 1
        if drift_meta["warning"]:
            drifting_count += 1
        if gap_meta["warning"]:
            broken_flow_count += 1
        if dominance_meta["warning"]:
            dominance_shift_count += 1
        if consistency_meta["warning"]:
            inconsistent_count += 1
        if reversal_meta["warning"]:
            reversing_count += 1
        if precursor_meta["warning"]:
            precursor_count += 1
        if lag_meta["warning"]:
            lagging_count += 1
        if policy_source_health.get("label") in {"watch", "fragile"}:
            policy_source_fragile_count += 1

        weight = float(FACTOR_WEIGHTS.get(factor.get("name", ""), 1.0))
        total_weight += weight
        adjusted_confidence += effective_confidence * weight

    if overview.get("factors"):
        overview["confidence"] = round(adjusted_confidence / total_weight, 4) if total_weight else 0.0
        overview["confidence_adjustment"] = {
            "penalized_factor_count": penalized_count,
            "boosted_factor_count": boosted_count,
            "blind_spot_factor_count": blind_spot_count,
            "unstable_factor_count": unstable_count,
            "concentrated_factor_count": concentrated_count,
            "lagging_factor_count": lagging_count,
            "drifting_factor_count": drifting_count,
            "broken_flow_factor_count": broken_flow_count,
            "confirmed_factor_count": confirmed_count,
            "dominance_shift_factor_count": dominance_shift_count,
            "inconsistent_factor_count": inconsistent_count,
            "reversing_factor_count": reversing_count,
            "precursor_factor_count": precursor_count,
            "policy_source_fragile_factor_count": policy_source_fragile_count,
            "reason": "证据分裂会降低置信度，一致且高质量证据会提升置信度",
        }
    return overview


def _build_conflict_summary(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in evidence_items:
        target = item.get("canonical_entity") or item.get("category") or "unknown"
        grouped.setdefault(target, []).append(item)

    conflicts = []
    for target, items in grouped.items():
        positive = [
            item for item in items
            if float(item.get("normalized_score", 0.0) or 0.0) >= 0.18
            and float(item.get("confidence", 0.0) or 0.0) >= 0.55
        ]
        negative = [
            item for item in items
            if float(item.get("normalized_score", 0.0) or 0.0) <= -0.18
            and float(item.get("confidence", 0.0) or 0.0) >= 0.55
        ]
        if not positive or not negative:
            continue

        strongest_positive = max(positive, key=lambda item: float(item.get("normalized_score", 0.0) or 0.0))
        strongest_negative = min(negative, key=lambda item: float(item.get("normalized_score", 0.0) or 0.0))
        score_gap = round(
            float(strongest_positive.get("normalized_score", 0.0) or 0.0)
            - float(strongest_negative.get("normalized_score", 0.0) or 0.0),
            4,
        )
        positive_sources = sorted({item.get("source", "") for item in positive if item.get("source")})
        negative_sources = sorted({item.get("source", "") for item in negative if item.get("source")})
        positive_official = [
            item for item in positive
            if item.get("source_tier") == "official"
        ]
        negative_official = [
            item for item in negative
            if item.get("source_tier") == "official"
        ]
        if positive_official and negative_official:
            source_pattern = "official_split"
            source_pattern_label = "官方源内部冲突"
        elif (positive_official and negative) or (negative_official and positive):
            source_pattern = "official_vs_derived"
            source_pattern_label = "官方源与派生源冲突"
        else:
            source_pattern = "derived_split"
            source_pattern_label = "派生源内部冲突"
        conflicts.append(
            {
                "target": target,
                "target_type": strongest_positive.get("entity_type") or "category",
                "positive_sources": positive_sources,
                "negative_sources": negative_sources,
                "positive_official_count": len(positive_official),
                "negative_official_count": len(negative_official),
                "source_pattern": source_pattern,
                "source_pattern_label": source_pattern_label,
                "positive_headline": strongest_positive.get("headline", ""),
                "negative_headline": strongest_negative.get("headline", ""),
                "score_gap": score_gap,
                "evidence_count": len(items),
                "summary": (
                    f"{target} 同时存在正负信号，"
                    f"正向 {len(positive_sources)} 源 / 负向 {len(negative_sources)} 源"
                ),
            }
        )

    conflicts.sort(key=lambda item: (-float(item["score_gap"]), -int(item["evidence_count"]), item["target"]))
    if not conflicts:
        level = "none"
    elif any(float(item["score_gap"]) >= 0.9 for item in conflicts):
        level = "high"
    elif any(float(item["score_gap"]) >= 0.55 for item in conflicts):
        level = "medium"
    else:
        level = "low"
    return {
        "conflict_count": len(conflicts),
        "conflict_level": level,
        "conflicts": conflicts[:6],
    }


def _build_conflict_trend(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(evidence_items) < 2:
        return {
            "trend": "stable",
            "reason": "样本不足，默认稳定",
            "recent_conflict_count": 0,
            "previous_conflict_count": 0,
        }

    midpoint = max(len(evidence_items) // 2, 1)
    recent = evidence_items[:midpoint]
    previous = evidence_items[midpoint:]
    recent_summary = _build_conflict_summary(recent)
    previous_summary = _build_conflict_summary(previous)
    recent_gap = max([float(item.get("score_gap", 0.0) or 0.0) for item in recent_summary["conflicts"]] or [0.0])
    previous_gap = max([float(item.get("score_gap", 0.0) or 0.0) for item in previous_summary["conflicts"]] or [0.0])

    if recent_summary["conflict_count"] > previous_summary["conflict_count"] or recent_gap >= previous_gap + 0.15:
        trend = "rising"
        reason = "近期证据分裂比前期更强"
    elif recent_summary["conflict_count"] < previous_summary["conflict_count"] or recent_gap + 0.15 < previous_gap:
        trend = "easing"
        reason = "近期证据分裂较前期缓和"
    elif recent_summary["conflict_count"] == 0 and previous_summary["conflict_count"] == 0:
        trend = "stable"
        reason = "近期未检测到明显证据分裂"
    else:
        trend = "stable"
        reason = "近期证据分裂程度基本持平"

    return {
        "trend": trend,
        "reason": reason,
        "recent_conflict_count": recent_summary["conflict_count"],
        "previous_conflict_count": previous_summary["conflict_count"],
    }


@router.get("/overview", summary="宏观错误定价总览")
async def get_macro_overview(refresh: bool = Query(default=False)):
    try:
        context = _build_context(refresh=refresh)
        factor_results = _registry.compute_all(context)
        combined = _combiner.combine(
            factor_results,
            weights=FACTOR_WEIGHTS,
        )
        overview = {
            "snapshot_timestamp": context["snapshot_timestamp"],
            "macro_score": combined["score"],
            "macro_signal": combined["signal"],
            "confidence": combined["confidence"],
            "factors": combined["factors"],
            "providers": context["provider_status"],
            "provider_status": context["provider_status"],
            "refresh_status": context["refresh_status"],
            "data_freshness": context["data_freshness"],
            "provider_health": context["provider_health"],
            "signals": context["signals"],
            "evidence_summary": _build_overall_evidence(context),
        }
        for factor in overview["factors"]:
            factor.setdefault("metadata", {})
            factor["metadata"]["evidence_summary"] = _build_factor_evidence(factor.get("name", ""), context)
        overview = _apply_conflict_penalty(overview)
        previous = _history_store.get_previous_snapshot(context["snapshot_timestamp"])
        overview["trend"] = _build_macro_trend(overview, previous)
        overview["resonance_summary"] = _build_resonance_summary(overview)
        _history_store.append_snapshot(overview)
        overview["history_length"] = len(_history_store.list_snapshots(limit=1000))
        return overview
    except Exception as exc:
        logger.error("Failed to build macro overview: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history", summary="宏观错误定价历史", deprecated=True)
async def get_macro_history(limit: int = Query(default=30, ge=1, le=200)):
    try:
        records = _history_store.list_snapshots(limit=limit)
        return {
            "records": records,
            "count": len(records),
        }
    except Exception as exc:
        logger.error("Failed to fetch macro history: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
