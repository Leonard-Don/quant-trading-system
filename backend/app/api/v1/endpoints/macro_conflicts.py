from __future__ import annotations

from typing import Any, Dict, List


def build_conflict_summary(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
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


def build_conflict_trend(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
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
    recent_summary = build_conflict_summary(recent)
    previous_summary = build_conflict_summary(previous)
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
