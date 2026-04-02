"""
宏观证据采集与摘要 helpers。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from src.data.alternative.entity_resolution import aggregate_entities, resolve_entity

from .macro_conflicts import build_conflict_summary, build_conflict_trend
from .macro_quality import (
    build_concentration_summary,
    build_consistency_summary,
    build_coverage_summary,
    build_cross_confirmation_summary,
    build_lag_summary,
    build_policy_source_health_summary,
    build_reversal_precursor_summary,
    build_reversal_summary,
    build_source_dominance_summary,
    build_source_drift_summary,
    build_source_gap_summary,
    build_stability_summary,
)
from .macro_support import FACTOR_EVIDENCE_MAP, SOURCE_TIER_RULES


def record_headline(record) -> str:
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


def record_excerpt(record) -> str:
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


def record_facts(record) -> Dict[str, Any]:
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


def build_freshness_meta(timestamp: datetime) -> Dict[str, Any]:
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


def infer_source_tier(source: str) -> Dict[str, Any]:
    normalized = str(source or "").lower()
    for prefix, (tier, trust_score) in SOURCE_TIER_RULES:
        if normalized.startswith(prefix):
            return {"tier": tier, "trust_score": trust_score}
    return {"tier": "derived", "trust_score": 0.65}


def build_factor_evidence(
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
            record_headline(record),
        )
        freshness = build_freshness_meta(record.timestamp)
        source_meta = infer_source_tier(record.source)
        evidence_rows.append(
            {
                "timestamp": record.timestamp.isoformat(),
                "source": record.source,
                "category": record.category.value,
                "headline": record_headline(record),
                "excerpt": record_excerpt(record),
                "facts": record_facts(record),
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
    conflict_summary = build_conflict_summary(evidence_rows)
    conflict_trend = build_conflict_trend(evidence_rows)
    coverage_summary = build_coverage_summary(categories, signal_keys, ordered, signal_evidence)
    stability_summary = build_stability_summary(ordered)
    lag_summary = build_lag_summary({
        "recent_evidence": recent_evidence,
        "freshness_label": recent_evidence[0]["freshness_label"] if recent_evidence else "stale",
    })
    concentration_summary = build_concentration_summary(evidence_rows)
    source_drift_summary = build_source_drift_summary(evidence_rows)
    source_gap_summary = build_source_gap_summary(ordered)
    cross_confirmation_summary = build_cross_confirmation_summary(evidence_rows)
    source_dominance_summary = build_source_dominance_summary(evidence_rows)
    consistency_summary = build_consistency_summary(evidence_rows)
    reversal_summary = build_reversal_summary(ordered)
    reversal_precursor_summary = build_reversal_precursor_summary(reversal_summary)
    policy_source_health_summary = build_policy_source_health_summary(context, signal_keys)

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
                        record_headline(record),
                    ).get("canonical", ""),
                    "entity_type": resolve_entity(
                        getattr(record, "raw_value", {}),
                        getattr(record, "tags", []),
                        record_headline(record),
                    ).get("entity_type", ""),
                }
                for record in ordered[: limit * 3]
            ],
            limit=4,
        ),
        "official_source_count": len([source for source in sources if infer_source_tier(source)["tier"] == "official"]),
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


def build_overall_evidence(context: Dict[str, Any]) -> Dict[str, Any]:
    records = context.get("records", [])
    ordered = sorted(records, key=lambda item: getattr(item, "timestamp", None), reverse=True)
    sources = sorted({getattr(record, "source", "") for record in ordered if getattr(record, "source", "")})
    freshness = build_freshness_meta(ordered[0].timestamp) if ordered else {"label": "stale"}
    evidence_rows = []
    for record in ordered[:16]:
        entity = resolve_entity(
            getattr(record, "raw_value", {}),
            getattr(record, "tags", []),
            record_headline(record),
        )
        evidence_rows.append(
            {
                "source": record.source,
                "category": record.category.value,
                "headline": record_headline(record),
                "canonical_entity": entity.get("canonical", ""),
                "entity_type": entity.get("entity_type", ""),
                "normalized_score": round(float(record.normalized_score), 4),
                "confidence": round(float(record.confidence), 4),
            }
        )
    conflict_summary = build_conflict_summary(evidence_rows)
    conflict_trend = build_conflict_trend(evidence_rows)
    policy_source_health_summary = build_policy_source_health_summary(context, {"policy_radar"})
    return {
        "record_count": len(ordered),
        "source_count": len(sources),
        "latest_timestamp": ordered[0].timestamp.isoformat() if ordered else "",
        "top_sources": sources[:8],
        "official_source_count": len([source for source in sources if infer_source_tier(source)["tier"] == "official"]),
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
