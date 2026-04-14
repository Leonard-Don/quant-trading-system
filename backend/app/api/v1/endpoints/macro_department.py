"""
部门级政策混乱度归因。
"""

from __future__ import annotations

from statistics import mean
from typing import Any, Dict, List


DEPARTMENT_LABELS = {
    "ndrc": "发改委",
    "nea": "能源局",
    "miit": "工信部",
    "mof": "财政部",
    "pboc": "央行",
    "csrc": "证监会",
    "local": "地方政府",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _department_from_record(record: Any) -> str:
    raw = getattr(record, "raw_value", {}) if record is not None else {}
    source = str(getattr(record, "source", "") or "")
    explicit = ""
    if isinstance(raw, dict):
        explicit = str(raw.get("department") or raw.get("agency") or raw.get("source_key") or "").strip().lower()
    if explicit:
        return explicit
    if ":" in source:
        return source.split(":", 1)[1].strip().lower() or "unknown"
    return source.strip().lower() or "unknown"


def _department_label(key: str) -> str:
    return DEPARTMENT_LABELS.get(key, key.upper() if key else "未知部门")


def _sign(value: float) -> int:
    if value > 0.12:
        return 1
    if value < -0.12:
        return -1
    return 0


def _reversal_count(values: List[float]) -> int:
    signs = [_sign(value) for value in values if _sign(value) != 0]
    if len(signs) < 2:
        return 0
    return sum(1 for previous, current in zip(signs, signs[1:]) if previous != current)


def _avg_step_change(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    return mean(abs(current - previous) for previous, current in zip(values, values[1:]))


def _build_department_row(department: str, records: List[Any]) -> Dict[str, Any]:
    ordered = sorted(records, key=lambda item: getattr(item, "timestamp", None), reverse=True)
    chronological = list(reversed(ordered))
    policy_shifts = [
        _safe_float(getattr(record, "raw_value", {}).get("policy_shift", 0.0))
        for record in chronological
        if isinstance(getattr(record, "raw_value", {}), dict)
    ]
    will_values = [
        _safe_float(getattr(record, "raw_value", {}).get("will_intensity", 0.0))
        for record in chronological
        if isinstance(getattr(record, "raw_value", {}), dict)
    ]
    reversal_count = _reversal_count(policy_shifts)
    reversal_rate = reversal_count / max(len(policy_shifts) - 1, 1)
    avg_abs_shift = mean(abs(value) for value in policy_shifts) if policy_shifts else 0.0
    avg_will = mean(will_values) if will_values else 0.0
    will_volatility = _avg_step_change(will_values)
    policy_volatility = _avg_step_change(policy_shifts)
    latest_raw = getattr(ordered[0], "raw_value", {}) if ordered else {}
    latest_title = latest_raw.get("title", "") if isinstance(latest_raw, dict) else ""
    chaos_score = min(
        1.0,
        avg_abs_shift * 0.32
        + reversal_rate * 0.28
        + avg_will * 0.22
        + min(1.0, will_volatility) * 0.1
        + min(1.0, policy_volatility) * 0.08,
    )
    label = "chaotic" if chaos_score >= 0.62 else "watch" if chaos_score >= 0.38 else "stable"
    reason_parts = []
    if reversal_count:
        reason_parts.append(f"方向反复 {reversal_count} 次")
    if avg_will >= 0.65:
        reason_parts.append(f"长官意志 {avg_will:.2f}")
    if avg_abs_shift >= 0.45:
        reason_parts.append(f"政策转向强度 {avg_abs_shift:.2f}")
    if not reason_parts:
        reason_parts.append("政策节奏暂未出现显著混乱")

    return {
        "department": department,
        "department_label": _department_label(department),
        "record_count": len(ordered),
        "chaos_score": round(chaos_score, 4),
        "label": label,
        "avg_abs_policy_shift": round(avg_abs_shift, 4),
        "avg_will_intensity": round(avg_will, 4),
        "policy_reversal_count": reversal_count,
        "policy_reversal_rate": round(reversal_rate, 4),
        "will_volatility": round(will_volatility, 4),
        "policy_volatility": round(policy_volatility, 4),
        "latest_title": latest_title,
        "latest_source": getattr(ordered[0], "source", "") if ordered else "",
        "reason": "，".join(reason_parts),
    }


def build_department_chaos_summary(context: Dict[str, Any]) -> Dict[str, Any]:
    policy_execution_signal = (context.get("signals", {}) or {}).get("policy_execution", {}) or {}
    if policy_execution_signal.get("department_board"):
        departments = list(policy_execution_signal.get("department_board") or [])
        departments.sort(key=lambda item: (item.get("chaos_score", 0.0), item.get("record_count", 0)), reverse=True)
        chaotic_departments = [item for item in departments if item.get("label") == "chaotic"]
        avg_score = mean([_safe_float(item.get("chaos_score")) for item in departments]) if departments else 0.0
        return {
            "label": "chaotic" if chaotic_departments else "watch" if avg_score >= 0.32 else "stable",
            "summary": policy_execution_signal.get("summary")
            or (
                f"当前跟踪 {len(departments)} 个政策主体，"
                f"{len(chaotic_departments)} 个进入高混乱区，平均混乱度 {avg_score:.2f}。"
            ),
            "department_count": len(departments),
            "chaotic_department_count": len(chaotic_departments),
            "avg_chaos_score": round(avg_score, 4),
            "top_departments": departments[:5],
            "source": "policy_execution_provider",
            "source_mode_summary": policy_execution_signal.get("source_mode_summary", {}),
        }

    records = [
        record
        for record in context.get("records", [])
        if getattr(getattr(record, "category", None), "value", "") == "policy"
    ]
    grouped: Dict[str, List[Any]] = {}
    for record in records:
        department = _department_from_record(record)
        grouped.setdefault(department, []).append(record)

    departments = [
        _build_department_row(department, rows)
        for department, rows in grouped.items()
        if rows
    ]
    departments.sort(key=lambda item: (item["chaos_score"], item["record_count"]), reverse=True)
    top_departments = departments[:5]
    chaotic_departments = [item for item in departments if item["label"] == "chaotic"]
    avg_score = mean([item["chaos_score"] for item in departments]) if departments else 0.0
    label = "chaotic" if chaotic_departments else "watch" if avg_score >= 0.32 else "stable"

    return {
        "label": label,
        "summary": (
            f"当前跟踪 {len(departments)} 个政策主体，"
            f"{len(chaotic_departments)} 个进入高混乱区，平均混乱度 {avg_score:.2f}。"
            if departments
            else "暂缺部门级政策记录。"
        ),
        "department_count": len(departments),
        "chaotic_department_count": len(chaotic_departments),
        "avg_chaos_score": round(avg_score, 4),
        "top_departments": top_departments,
        "source": "policy_radar_department_attribution",
    }
