from __future__ import annotations

from typing import Any, Dict, List


def build_structural_decay(
    gap: Dict[str, Any],
    factor: Dict[str, Any],
    valuation: Dict[str, Any],
    people_layer: Dict[str, Any],
    alignment_meta: Dict[str, Any],
    confidence_meta: Dict[str, Any],
) -> Dict[str, Any]:
    score = 0.0
    components: List[Dict[str, Any]] = []
    category_scores = {
        "people": 0.0,
        "execution": 0.0,
        "valuation": 0.0,
        "evidence": 0.0,
    }
    evidence: List[str] = []

    def add_component(
        key: str,
        label: str,
        delta: float,
        detail: str,
        category: str,
        status: str = "positive",
    ) -> None:
        nonlocal score
        score += delta
        category_scores[category] = category_scores.get(category, 0.0) + delta
        components.append(
            {
                "key": key,
                "label": label,
                "delta": round(delta, 2),
                "status": status,
                "detail": detail,
            }
        )

    people_fragility = float(people_layer.get("people_fragility_score") or 0.0)
    people_quality = float(people_layer.get("people_quality_score") or 0.0)
    people_risk = people_layer.get("risk_level", "unknown")
    if people_fragility >= 0.68:
        add_component("people_fragility", "组织脆弱度", 0.28, "人的维度已进入高脆弱区间", "people")
        evidence.append("人的维度已进入高脆弱区间")
    elif people_fragility >= 0.48:
        add_component("people_fragility", "组织脆弱度", 0.16, "人的维度偏脆弱，需防范结构性走弱", "people")
        evidence.append("人的维度偏脆弱")
    elif people_quality >= 0.68 and people_risk == "low":
        add_component("people_fragility", "组织脆弱度", -0.08, "管理层质量与技术权威对长期执行形成支撑", "people", "negative")

    hiring_signal = people_layer.get("hiring_signal", {}) or {}
    dilution_ratio = float(hiring_signal.get("dilution_ratio") or 0.0)
    if dilution_ratio >= 1.6:
        add_component("hiring_dilution", "技术稀释", 0.14, f"招聘稀释度 {dilution_ratio:.2f}，组织重心向非技术侧偏移", "people")
        evidence.append(f"招聘稀释度 {dilution_ratio:.2f}")

    insider_flow = people_layer.get("insider_flow", {}) or {}
    insider_conviction = float(insider_flow.get("conviction_score") or 0.0)
    if insider_conviction <= -0.18:
        add_component("insider_flow", "内部人信号", 0.10, "内部人交易偏减持，管理层对安全边际背书偏弱", "people")
        evidence.append("内部人交易偏减持")

    capm_alpha = float((factor.get("capm", {}) or {}).get("alpha_pct") or 0.0)
    ff3_alpha = float((factor.get("fama_french", {}) or {}).get("alpha_pct") or 0.0)
    if capm_alpha <= -5 and ff3_alpha <= -3:
        add_component("execution_decay", "风险调整后执行", 0.18, "CAPM/FF3 alpha 持续为负，说明竞争与执行层面承压", "execution")
        evidence.append("风险调整后执行持续为负")
    elif capm_alpha <= -3 or ff3_alpha <= -3:
        add_component("execution_decay", "风险调整后执行", 0.1, "历史 alpha 偏弱，需警惕执行与竞争优势流失", "execution")
    elif capm_alpha >= 3 and ff3_alpha >= 2:
        add_component("execution_decay", "风险调整后执行", -0.06, "历史 alpha 仍有支撑，短期不构成明显衰败证据", "execution", "negative")

    gap_pct = float(gap.get("gap_pct") or 0.0)
    valuation_status = (valuation.get("valuation_status", {}) or {}).get("status", "")
    if gap_pct >= 20 and valuation_status in {"overvalued", "severely_overvalued"} and people_fragility >= 0.48:
        add_component("valuation_excess", "高估脆弱性", 0.16, "高估值叠加组织脆弱，容易在预期回落时形成结构性杀估值", "valuation")
        evidence.append("高估值叠加组织脆弱")
    elif gap_pct <= -20 and people_fragility >= 0.62:
        add_component("value_trap", "价值陷阱风险", 0.14, "表面低估但人的维度偏脆弱，需警惕价值陷阱", "valuation")
        evidence.append("低估背后可能存在价值陷阱")

    alignment_status = alignment_meta.get("status")
    if alignment_status == "conflict":
        add_component("evidence_conflict", "证据冲突", 0.14, "因子与估值结论冲突，市场对长期叙事的定价可能正在切换", "evidence")
        evidence.append("因子与估值结论冲突")
    elif alignment_status == "aligned":
        add_component("evidence_conflict", "证据冲突", -0.05, "因子与估值同向，暂未看到强烈的结构性分裂", "evidence", "negative")

    confidence_level = confidence_meta.get("level")
    if confidence_level == "low" and people_fragility >= 0.48:
        add_component("confidence_regime", "研究稳定性", 0.08, "当前证据本身不稳，需警惕这不是短期噪音而是结构劣化早期", "evidence")
    elif confidence_level == "high" and alignment_status == "aligned":
        add_component("confidence_regime", "研究稳定性", -0.04, "高置信度且证据同向，暂不支持过强的衰败判断", "evidence", "negative")

    score = max(0.0, min(score, 1.0))

    if score >= 0.72:
        label = "结构性衰败警报"
        action = "structural_short"
        reversibility = "低"
        horizon = "长期"
    elif score >= 0.5:
        label = "衰败风险上升"
        action = "structural_avoid"
        reversibility = "中低"
        horizon = "中长期"
    elif score >= 0.3:
        label = "持续观察"
        action = "watch"
        reversibility = "中"
        horizon = "中期"
    else:
        label = "暂未见结构性衰败"
        action = "stable"
        reversibility = "高"
        horizon = "待观察"

    dominant_failure_mode = max(category_scores.items(), key=lambda item: item[1])[0]
    dominant_failure_label = {
        "people": "组织与治理稀释",
        "execution": "竞争与执行失速",
        "valuation": "估值泡沫/价值陷阱",
        "evidence": "叙事与证据断裂",
    }.get(dominant_failure_mode, "待确认")

    summary = (
        f"{label}，主导失效模式偏向 {dominant_failure_label}。"
        if score >= 0.3
        else "当前更像阶段性波动，尚不足以直接判断为结构性衰败。"
    )

    return {
        "score": round(score, 2),
        "label": label,
        "action": action,
        "reversibility": reversibility,
        "horizon": horizon,
        "dominant_failure_mode": dominant_failure_mode,
        "dominant_failure_label": dominant_failure_label,
        "summary": summary,
        "evidence": evidence[:4],
        "components": components,
    }
