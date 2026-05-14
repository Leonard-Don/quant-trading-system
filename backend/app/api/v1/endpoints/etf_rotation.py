"""ETF rotation — read-only HTTP surface for the daily manual trade plan.

This wraps :func:`scripts.daily_etf_signal.generate_plan` so the frontend can
render the same manual-only suggestions the CLI prints. The endpoint is
intentionally broker-agnostic: it does not contact any quote provider or
broker, and uses the deterministic screenshot seed shipped with the script.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

from scripts import daily_etf_signal

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/daily-signal",
    summary="获取每日 ETF 轮动手动调仓建议",
    description=(
        "返回 ``scripts.daily_etf_signal.generate_plan`` 的完整计划字段："
        "current_weights / target_weights / adjusted_weights / suggestions / "
        "risk_reasons。该接口只读、确定性、不调用任何券商或行情接口。"
    ),
)
def get_daily_signal(
    threshold_weight: float = Query(
        default=0.03,
        ge=0.0,
        le=1.0,
        description="低于该权重差异的标的不会触发买卖建议（仅生成 hold）。",
    ),
) -> dict[str, Any]:
    plan = daily_etf_signal.generate_plan(threshold_weight=threshold_weight)
    return {"success": True, "data": plan}
