"""Pure helper functions extracted from ``endpoints/industry.py``.

These are stateless utilities (sparkline normalisation, lifecycle
classification, calendar-event templates, cosine similarity, byte-size
formatting, pydantic-to-dict adapter). They have **no** module-level
state and **no** dependencies on the industry-analyzer / leader-scorer
singletons, so they make the cleanest first split out of the
3349-line endpoint module.

The functions remain underscore-prefixed and are re-imported by
``endpoints/industry.py`` so callsite paths are unchanged.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any


def _normalize_sparkline_points(points: list[float], max_points: int = 20) -> list[float]:
    normalized: list[float] = []
    for point in points or []:
        try:
            value = float(point)
        except (TypeError, ValueError):
            continue
        if value > 0:
            normalized.append(round(value, 3))
    if len(normalized) <= max_points:
        return normalized
    step = max(1, len(normalized) // max_points)
    sampled = normalized[::step][:max_points]
    if sampled[-1] != normalized[-1]:
        sampled[-1] = normalized[-1]
    return sampled


def _classify_industry_lifecycle(row: dict[str, Any]) -> dict[str, Any]:
    score = float(row.get("score") or row.get("total_score") or 0)
    momentum = float(row.get("momentum") or 0)
    change_pct = float(row.get("change_pct") or 0)
    flow = float(row.get("money_flow") or row.get("flow_strength") or 0)
    volatility = abs(float(row.get("industry_volatility") or 0))

    if score >= 75 and momentum > 0 and flow >= 0:
        stage = "成长期"
        confidence = min(0.95, 0.55 + score / 200)
    elif score >= 60 and abs(momentum) <= 8 and volatility < 8:
        stage = "成熟期"
        confidence = min(0.9, 0.5 + score / 220)
    elif change_pct < -3 or momentum < -8:
        stage = "衰退期"
        confidence = min(0.9, 0.55 + abs(momentum) / 50)
    else:
        stage = "导入期"
        confidence = 0.55

    return {
        "stage": stage,
        "confidence": round(float(confidence), 3),
        "drivers": {
            "score": round(score, 3),
            "momentum": round(momentum, 3),
            "change_pct": round(change_pct, 3),
            "money_flow": round(flow, 3),
            "volatility": round(volatility, 3),
        },
    }


def _build_industry_events(industry_name: str) -> list[dict[str, Any]]:
    now = datetime.now()
    base_events = [
        {"name": "财报密集披露窗口", "offset_days": 14, "type": "earnings", "impact": "fundamental"},
        {"name": "月度宏观/行业数据窗口", "offset_days": 20, "type": "macro_data", "impact": "demand"},
        {"name": "政策/监管观察窗口", "offset_days": 35, "type": "policy", "impact": "valuation"},
    ]
    if any(keyword in industry_name for keyword in ("新能源", "光伏", "电池", "汽车")):
        base_events.append(
            {"name": "新能源产业链价格与装机数据", "offset_days": 10, "type": "industry_data", "impact": "margin"}
        )
    if any(keyword in industry_name for keyword in ("半导体", "芯片", "人工智能", "软件")):
        base_events.append(
            {"name": "科技产品发布/供应链景气跟踪", "offset_days": 21, "type": "product_cycle", "impact": "growth"}
        )
    return [
        {
            "date": (now + timedelta(days=item["offset_days"])).strftime("%Y-%m-%d"),
            "title": item["name"],
            "event_type": item["type"],
            "expected_impact": item["impact"],
            "industry_name": industry_name,
        }
        for item in base_events
    ]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _model_to_dict(model: Any) -> Any:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return model


def _format_storage_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"
