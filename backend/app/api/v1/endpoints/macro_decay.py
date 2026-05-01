"""Macro structural-decay radar helpers and API endpoint."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from fastapi import APIRouter

router = APIRouter()


AXIS_DISPLAY_LABELS = {
    "people": "人的维度",
    "policy_execution": "政策执行",
    "evidence": "证据冲突",
    "input_reliability": "输入可靠性",
    "factor_pressure": "宏观因子压力",
}


def _to_float(value: Any, default: float = 0.0) -> float:
    """Return a bounded float for loose API dictionaries."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(number, 1.0))


def _status_for_score(score: float) -> str:
    """Map a normalized axis score to a radar status label."""
    if score >= 0.6:
        return "critical"
    if score >= 0.4:
        return "watch"
    return "stable"


def _axis(key: str, score: float, summary: str = "") -> Dict[str, Any]:
    """Build a normalized structural-decay radar axis."""
    bounded_score = round(_to_float(score), 4)
    return {
        "key": key,
        "label": AXIS_DISPLAY_LABELS[key],
        "score": bounded_score,
        "status": _status_for_score(bounded_score),
        "summary": summary,
    }


def _label_score(label: str, mapping: Mapping[str, float], default: float = 0.0) -> float:
    """Resolve a qualitative label into a bounded numeric score."""
    normalized = str(label or "").strip().lower()
    return _to_float(mapping.get(normalized, default))


def _people_axis(overview: Mapping[str, Any]) -> Dict[str, Any]:
    people = overview.get("people_layer_summary") or {}
    score = _to_float(people.get("avg_fragility_score"))
    fragile_count = int(people.get("fragile_company_count") or len(people.get("fragile_companies") or []))
    if fragile_count:
        score = max(score, min(1.0, 0.52 + fragile_count * 0.07))
    score = max(
        score,
        _label_score(
            people.get("label"),
            {
                "stable": 0.16,
                "watch": 0.48,
                "fragile": 0.66,
                "critical": 0.78,
            },
        ),
    )
    return _axis("people", score, str(people.get("summary") or ""))


def _policy_axis(overview: Mapping[str, Any]) -> Dict[str, Any]:
    policy = overview.get("department_chaos_summary") or {}
    department_count = int(policy.get("department_count") or 0)
    chaotic_count = int(policy.get("chaotic_department_count") or 0)
    chaos_ratio = chaotic_count / department_count if department_count else 0.0
    score = max(
        _to_float(policy.get("avg_chaos_score")),
        min(1.0, 0.48 + chaos_ratio * 0.32) if chaotic_count else 0.0,
        _label_score(
            policy.get("label"),
            {
                "stable": 0.12,
                "watch": 0.46,
                "chaotic": 0.68,
                "critical": 0.78,
            },
        ),
    )
    return _axis("policy_execution", score, str(policy.get("summary") or ""))


def _evidence_axis(overview: Mapping[str, Any]) -> Dict[str, Any]:
    evidence = overview.get("evidence_summary") or {}
    source_health = evidence.get("policy_source_health_summary") or {}
    conflict_score = _label_score(
        evidence.get("conflict_level"),
        {
            "none": 0.08,
            "low": 0.24,
            "medium": 0.48,
            "high": 0.74,
            "critical": 0.84,
        },
    )
    source_score = _label_score(
        source_health.get("label"),
        {
            "healthy": 0.08,
            "mixed": 0.36,
            "watch": 0.44,
            "fragile": 0.62,
            "fallback-heavy": 0.64,
        },
    )
    return _axis("evidence", max(conflict_score, source_score), str(evidence.get("summary") or source_health.get("reason") or ""))


def _reliability_axis(overview: Mapping[str, Any]) -> Dict[str, Any]:
    reliability = overview.get("input_reliability_summary") or {}
    score = _label_score(
        reliability.get("label"),
        {
            "robust": 0.08,
            "healthy": 0.12,
            "mixed": 0.36,
            "watch": 0.46,
            "fragile": 0.68,
            "fallback-heavy": 0.7,
        },
    )
    return _axis("input_reliability", score, str(reliability.get("summary") or ""))


def _factor_pressure_axis(overview: Mapping[str, Any]) -> Dict[str, Any]:
    factors = overview.get("factors") or []
    pressures: List[float] = []
    for factor in factors:
        z_score = max(0.0, float(factor.get("z_score") or 0.0))
        value_score = _to_float(factor.get("value"))
        confidence = _to_float(factor.get("confidence"), default=1.0)
        normalized_z = min(1.0, z_score / 2.0)
        pressures.append(max(normalized_z, value_score) * max(confidence, 0.5))
    score = max(pressures, default=0.0)
    return _axis("factor_pressure", score, f"{len(pressures)} 个因子进入雷达输入。")


def _focus_companies(overview: Mapping[str, Any]) -> List[Dict[str, Any]]:
    people = overview.get("people_layer_summary") or {}
    candidates = list(people.get("watchlist") or people.get("fragile_companies") or [])
    return sorted(
        candidates,
        key=lambda item: float(item.get("people_fragility_score") or item.get("score") or 0.0),
        reverse=True,
    )[:5]


def _focus_departments(overview: Mapping[str, Any]) -> List[Dict[str, Any]]:
    policy = overview.get("department_chaos_summary") or {}
    candidates = list(policy.get("top_departments") or [])
    return sorted(
        candidates,
        key=lambda item: float(item.get("chaos_score") or item.get("score") or 0.0),
        reverse=True,
    )[:5]


def build_structural_decay_radar(overview: Dict[str, Any]) -> Dict[str, Any]:
    """Build a system-level structural-decay radar from macro overview signals.

    Args:
        overview: Macro overview payload containing people, policy execution,
            source reliability, and factor summaries.

    Returns:
        A normalized radar payload with label, score, axes, focus entities, and
        action guidance for cross-market research workflows.
    """
    axes = [
        _people_axis(overview),
        _policy_axis(overview),
        _evidence_axis(overview),
        _reliability_axis(overview),
        _factor_pressure_axis(overview),
    ]
    critical_axis_count = sum(1 for axis in axes if axis["status"] == "critical")
    watch_axis_count = sum(1 for axis in axes if axis["status"] == "watch")
    weighted_score = sum(float(axis["score"]) for axis in axes) / len(axes)
    pressure_bonus = min(0.14, critical_axis_count * 0.035 + watch_axis_count * 0.015)
    score = round(min(1.0, weighted_score + pressure_bonus), 4)

    if score >= 0.68 or critical_axis_count >= 3:
        label = "decay_alert"
        display_label = "结构衰败警报"
        action_hint = "人的维度、政策执行、证据可靠性或因子压力已形成共振，建议收缩风险预算并强化防御/对冲约束。"
        risk_budget_scale = 0.78
    elif score >= 0.44 or critical_axis_count >= 1 or watch_axis_count >= 2:
        label = "decay_watch"
        display_label = "结构衰败观察"
        action_hint = "系统级脆弱性正在升温，建议复核核心假设并降低风险加仓速度。"
        risk_budget_scale = 0.9
    else:
        label = "stable"
        display_label = "结构衰败稳定"
        action_hint = "暂未看到系统级负向共振，维持常规研究节奏。"
        risk_budget_scale = 1.0

    top_signals = sorted(axes, key=lambda axis: float(axis["score"]), reverse=True)[:3]
    return {
        "label": label,
        "display_label": display_label,
        "score": score,
        "critical_axis_count": critical_axis_count,
        "watch_axis_count": watch_axis_count,
        "risk_budget_scale": risk_budget_scale,
        "action_hint": action_hint,
        "axes": axes,
        "top_signals": top_signals,
        "focus_companies": _focus_companies(overview),
        "focus_departments": _focus_departments(overview),
    }


@router.post("/radar", summary="构建结构衰败雷达")
def structural_decay_radar(overview: Dict[str, Any]) -> Dict[str, Any]:
    """Return the structural-decay radar for a macro overview payload."""
    return build_structural_decay_radar(overview)
