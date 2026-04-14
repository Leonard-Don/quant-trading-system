"""
系统级结构性衰败雷达。
"""

from __future__ import annotations

from typing import Any, Dict, List


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


def _axis(key: str, label: str, score: float, summary: str) -> Dict[str, Any]:
    score = _bounded(score)
    return {
        "key": key,
        "label": label,
        "score": round(score, 4),
        "status": "critical" if score >= 0.68 else "watch" if score >= 0.42 else "stable",
        "summary": summary,
    }


def _factor_intensity(factor: Dict[str, Any]) -> float:
    z_score = abs(_safe_float(factor.get("z_score")))
    value = abs(_safe_float(factor.get("value")))
    confidence = _safe_float(factor.get("confidence"), 0.5)
    return _bounded(max(z_score / 2.2, value) * (0.72 + min(confidence, 1.0) * 0.28))


def _factor_lookup(overview: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(factor.get("name") or ""): factor
        for factor in overview.get("factors", [])
        if isinstance(factor, dict)
    }


def _top_signal(key: str, label: str, score: float, detail: str, source: str) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "score": round(_bounded(score), 4),
        "detail": detail,
        "source": source,
    }


def build_structural_decay_radar(overview: Dict[str, Any]) -> Dict[str, Any]:
    people_summary = overview.get("people_layer_summary", {}) or {}
    department_summary = overview.get("department_chaos_summary", {}) or {}
    evidence_summary = overview.get("evidence_summary", {}) or {}
    input_reliability = overview.get("input_reliability_summary", {}) or {}
    factors = _factor_lookup(overview)

    watchlist = people_summary.get("watchlist") or []
    top_people_score = max(
        [_safe_float(item.get("people_fragility_score")) for item in watchlist] or [0.0]
    )
    avg_people_score = _safe_float(people_summary.get("avg_fragility_score"))
    fragile_ratio = _safe_float(people_summary.get("fragile_company_count")) / max(
        1.0,
        _safe_float(people_summary.get("fragile_company_count"))
        + _safe_float(people_summary.get("supportive_company_count"))
        + len(watchlist),
    )
    people_pressure = _bounded(max(avg_people_score, top_people_score * 0.92, fragile_ratio))

    departments = department_summary.get("top_departments") or []
    top_department_score = max([_safe_float(item.get("chaos_score")) for item in departments] or [0.0])
    governance_pressure = _bounded(
        max(
            _safe_float(department_summary.get("avg_chaos_score")),
            top_department_score * 0.9,
            _safe_float(department_summary.get("chaotic_department_count")) / max(
                1.0,
                _safe_float(department_summary.get("department_count")),
            ),
        )
    )

    tech_intensity = _factor_intensity(factors.get("tech_dilution", {}))
    credit_intensity = _factor_intensity(factors.get("credit_spread_stress", {}))
    people_factor_intensity = _factor_intensity(factors.get("people_fragility", {}))
    policy_execution_intensity = _factor_intensity(factors.get("policy_execution_disorder", {}))
    execution_pressure = _bounded(
        max(
            tech_intensity,
            credit_intensity * 0.78,
            people_pressure * 0.68,
            people_factor_intensity * 0.82,
            policy_execution_intensity * 0.74,
        )
    )

    bureaucratic_intensity = _factor_intensity(factors.get("bureaucratic_friction", {}))
    baseload_intensity = _factor_intensity(factors.get("baseload_mismatch", {}))
    physical_pressure = _bounded(
        max(
            bureaucratic_intensity * 0.84,
            baseload_intensity,
            governance_pressure * 0.7,
            policy_execution_intensity * 0.55,
        )
    )

    evidence_pressure = 0.0
    if evidence_summary.get("conflict_level") == "high":
        evidence_pressure += 0.28
    elif evidence_summary.get("conflict_level") == "medium":
        evidence_pressure += 0.18
    if input_reliability.get("label") == "fragile":
        evidence_pressure += 0.26
    elif input_reliability.get("label") == "watch":
        evidence_pressure += 0.14
    if (evidence_summary.get("policy_source_health_summary") or {}).get("label") == "fragile":
        evidence_pressure += 0.2
    evidence_pressure = _bounded(max(evidence_pressure, governance_pressure * 0.42))

    axes = [
        _axis(
            "people",
            "人的维度",
            people_pressure,
            people_summary.get("summary") or "人的维度暂未出现显著脆弱信号。",
        ),
        _axis(
            "governance",
            "政策治理",
            governance_pressure,
            department_summary.get("summary") or "部门级政策混乱暂未显著升温。",
        ),
        _axis(
            "execution",
            "执行失速",
            execution_pressure,
            "技术稀释、信用压力与组织质量共同刻画执行风险。",
        ),
        _axis(
            "physical",
            "物理约束",
            physical_pressure,
            "官僚摩擦与基荷错配共同刻画物理世界约束。",
        ),
        _axis(
            "evidence",
            "证据稳定",
            evidence_pressure,
            input_reliability.get("summary") or "证据链暂未出现明显断裂。",
        ),
    ]

    score = _bounded(
        people_pressure * 0.26
        + governance_pressure * 0.2
        + execution_pressure * 0.2
        + physical_pressure * 0.16
        + evidence_pressure * 0.18
    )
    critical_axis_count = len([axis for axis in axes if axis["status"] == "critical"])
    if score >= 0.68 or critical_axis_count >= 3:
        label = "decay_alert"
        display_label = "结构衰败警报"
        action_hint = "系统级人的维度、治理与执行证据已经共振，优先检查 Decay Watch 与防御/做空模板。"
    elif score >= 0.44 or critical_axis_count >= 1:
        label = "decay_watch"
        display_label = "衰败风险升温"
        action_hint = "结构性衰败信号进入观察区，适合优先复核人的维度与政策执行主体。"
    else:
        label = "stable"
        display_label = "结构暂稳"
        action_hint = "当前更像局部扰动，继续跟踪信号是否扩散。"

    signals: List[Dict[str, Any]] = [
        _top_signal("people", "人的维度", people_pressure, people_summary.get("summary", ""), "people_layer_summary"),
        _top_signal("governance", "政策治理", governance_pressure, department_summary.get("summary", ""), "department_chaos_summary"),
        _top_signal("execution", "执行失速", execution_pressure, "技术稀释/信用压力/组织质量综合压力", "macro_factors"),
        _top_signal("physical", "物理约束", physical_pressure, "基荷错配与官僚摩擦共同约束", "macro_factors"),
        _top_signal("evidence", "证据稳定", evidence_pressure, input_reliability.get("summary", ""), "input_reliability_summary"),
    ]
    signals.sort(key=lambda item: item["score"], reverse=True)

    return {
        "label": label,
        "display_label": display_label,
        "score": round(score, 4),
        "critical_axis_count": critical_axis_count,
        "axes": axes,
        "top_signals": signals[:4],
        "focus_companies": watchlist[:3],
        "focus_departments": departments[:3],
        "action_hint": action_hint,
        "source": "macro_decay_radar",
    }
