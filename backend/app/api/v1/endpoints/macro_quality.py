"""
宏观证据质量、置信度与输入可靠度评估 helpers。
"""

from __future__ import annotations

from typing import Any, Dict, List

from .macro_support import FACTOR_WEIGHTS


def build_policy_source_health_summary(
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


def calculate_confidence_penalty(evidence_summary: Dict[str, Any]) -> Dict[str, Any]:
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


def calculate_confidence_support_bonus(evidence_summary: Dict[str, Any]) -> Dict[str, Any]:
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


def build_coverage_summary(
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


def build_stability_summary(records: List[Any]) -> Dict[str, Any]:
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


def build_lag_summary(evidence_summary: Dict[str, Any]) -> Dict[str, Any]:
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


def build_concentration_summary(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
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


def build_source_drift_summary(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
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


def build_source_gap_summary(records: List[Any]) -> Dict[str, Any]:
    ordered = sorted(
        [record for record in records if getattr(record, "timestamp", None) is not None],
        key=lambda item: item.timestamp,
    )
    if len(ordered) < 2:
        return {
            "label": "stable",
            "latest_gap_hours": 0.0,
            "baseline_gap_hours": 0.0,
            "reason": "样本不足，默认无明显断流",
        }

    if len(ordered) == 2:
        latest_gap = round(
            max((ordered[1].timestamp - ordered[0].timestamp).total_seconds() / 3600, 0.0),
            2,
        )
        baseline_gap = 24.0
        if latest_gap >= 168:
            label = "broken"
            reason = "仅有两条样本且最近间隔已明显超出常规更新节奏，疑似出现来源断流"
        elif latest_gap >= 72:
            label = "stretching"
            reason = "仅有两条样本且最近间隔明显拉长，应关注来源是否正在断流"
        else:
            label = "stable"
            reason = "当前样本较少，但最近间隔仍处于可接受范围"
        return {
            "label": label,
            "latest_gap_hours": latest_gap,
            "baseline_gap_hours": baseline_gap,
            "reason": reason,
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


def build_cross_confirmation_summary(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
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


def build_reversal_summary(records: List[Any]) -> Dict[str, Any]:
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


def build_reversal_precursor_summary(reversal_summary: Dict[str, Any]) -> Dict[str, Any]:
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


def build_consistency_summary(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
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


def build_source_dominance_summary(evidence_items: List[Dict[str, Any]]) -> Dict[str, Any]:
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
    if label == "reversed":
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


def apply_conflict_penalty(overview: Dict[str, Any]) -> Dict[str, Any]:
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
        penalty_meta = calculate_confidence_penalty(evidence_summary)
        bonus_meta = calculate_confidence_support_bonus(evidence_summary)
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


def build_input_reliability_summary(overview: Dict[str, Any]) -> Dict[str, Any]:
    factors = overview.get("factors", []) or []
    confidence_adjustment = overview.get("confidence_adjustment", {}) or {}
    evidence_summary = overview.get("evidence_summary", {}) or {}
    confidence = float(overview.get("confidence", 0.0) or 0.0)
    total_factors = len(factors) or 1

    issue_counts = {
        "blind_spot": int(confidence_adjustment.get("blind_spot_factor_count", 0) or 0),
        "unstable": int(confidence_adjustment.get("unstable_factor_count", 0) or 0),
        "lagging": int(confidence_adjustment.get("lagging_factor_count", 0) or 0),
        "concentrated": int(confidence_adjustment.get("concentrated_factor_count", 0) or 0),
        "drifting": int(confidence_adjustment.get("drifting_factor_count", 0) or 0),
        "broken_flow": int(confidence_adjustment.get("broken_flow_factor_count", 0) or 0),
        "dominance_shift": int(confidence_adjustment.get("dominance_shift_factor_count", 0) or 0),
        "inconsistent": int(confidence_adjustment.get("inconsistent_factor_count", 0) or 0),
        "reversing": int(confidence_adjustment.get("reversing_factor_count", 0) or 0),
        "precursor": int(confidence_adjustment.get("precursor_factor_count", 0) or 0),
        "policy_source_fragile": int(confidence_adjustment.get("policy_source_fragile_factor_count", 0) or 0),
    }
    support_counts = {
        "confirmed": int(confidence_adjustment.get("confirmed_factor_count", 0) or 0),
        "boosted": int(confidence_adjustment.get("boosted_factor_count", 0) or 0),
    }
    total_issue_hits = sum(issue_counts.values())
    dominant_issues = [name for name, count in issue_counts.items() if count > 0]
    dominant_issues.sort(key=lambda name: (-issue_counts[name], name))
    dominant_supports = [name for name, count in support_counts.items() if count > 0]
    dominant_supports.sort(key=lambda name: (-support_counts[name], name))

    freshness_label = evidence_summary.get("freshness_label", "stale")
    conflict_level = evidence_summary.get("conflict_level", "none")
    policy_source_health = (evidence_summary.get("policy_source_health_summary") or {}).get("label", "unknown")

    if (
        confidence < 0.5
        or total_issue_hits >= max(3, total_factors)
        or conflict_level == "high"
        or policy_source_health == "fragile"
        or freshness_label in {"stale", "aging"}
        or issue_counts["broken_flow"] > 0
    ):
        label = "fragile"
        posture = "当前宏观输入更适合先复核来源与证据质量，再用于定价判断。"
    elif (
        confidence < 0.7
        or total_issue_hits >= 1
        or conflict_level in {"medium", "low"}
        or policy_source_health == "watch"
        or freshness_label in {"recent", "aging"}
    ):
        label = "watch"
        posture = "当前宏观输入更适合作为研究排序与提示信号，不宜单独当作强定价锚。"
    else:
        label = "robust"
        posture = "当前宏观输入整体可靠度较好，可作为较强研究锚，但仍应结合具体资产上下文。"

    risk_score = max(
        0.0,
        min(
            1.0,
            round(
                confidence
                - min(0.35, total_issue_hits * 0.025)
                + min(0.15, sum(support_counts.values()) * 0.02),
                4,
            ),
        ),
    )

    issue_labels = {
        "blind_spot": "输入盲区",
        "unstable": "时序不稳",
        "lagging": "时效偏旧",
        "concentrated": "证据集中",
        "drifting": "来源退化",
        "broken_flow": "来源断流",
        "dominance_shift": "主导权切换",
        "inconsistent": "结论分歧",
        "reversing": "方向反转",
        "precursor": "反转前兆",
        "policy_source_fragile": "政策源脆弱",
    }
    support_labels = {
        "confirmed": "跨源确认",
        "boosted": "高质量加成",
    }
    issue_text = "、".join(issue_labels[name] for name in dominant_issues[:3]) if dominant_issues else ""
    support_text = "、".join(support_labels[name] for name in dominant_supports[:2]) if dominant_supports else ""

    if label == "fragile":
        lead = f"当前输入可靠度偏脆弱，主要风险来自 {issue_text or '多项证据质量问题'}。"
    elif label == "watch":
        lead = f"当前输入可靠度需要持续观察，主要受 {issue_text or '局部证据质量波动'} 影响。"
    else:
        lead = f"当前输入可靠度整体稳健，主要支撑来自 {support_text or '较稳定的证据结构'}。"

    reason_parts = [
        f"effective confidence {confidence:.2f}",
        f"freshness {freshness_label}",
    ]
    if conflict_level != "none":
        reason_parts.append(f"conflict {conflict_level}")
    if policy_source_health != "unknown":
        reason_parts.append(f"policy source {policy_source_health}")
    if issue_text:
        reason_parts.append(f"风险 {issue_text}")
    if support_text:
        reason_parts.append(f"支撑 {support_text}")

    return {
        "label": label,
        "score": risk_score,
        "lead": lead,
        "posture": posture,
        "reason": " · ".join(reason_parts),
        "issue_factor_hits": total_issue_hits,
        "support_factor_hits": sum(support_counts.values()),
        "dominant_issue_labels": [issue_labels[name] for name in dominant_issues[:4]],
        "dominant_support_labels": [support_labels[name] for name in dominant_supports[:3]],
    }
