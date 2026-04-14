"""Quant Lab endpoints for advanced research extensions."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.core.task_queue import task_queue_manager
from backend.app.services.quant_lab import quant_lab_service

router = APIRouter()
logger = logging.getLogger(__name__)


class StrategyOptimizationRequest(BaseModel):
    symbol: str
    strategy: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    parameter_grid: Optional[Dict[str, List[Any]]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_capital: float = 10000
    commission: float = 0.001
    slippage: float = 0.001
    density: int = 3
    optimization_metric: str = "sharpe_ratio"
    optimization_method: str = "grid"
    optimization_budget: Optional[int] = None
    run_walk_forward: bool = True
    train_period: int = 126
    test_period: int = 42
    step_size: int = 21
    monte_carlo_simulations: int = 150


class RiskCenterRequest(BaseModel):
    symbols: List[str]
    weights: Optional[List[float]] = None
    period: str = "1y"


class TradingJournalUpdateRequest(BaseModel):
    notes: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    strategy_lifecycle: List[Dict[str, Any]] = Field(default_factory=list)


class AlertOrchestrationUpdateRequest(BaseModel):
    composite_rules: List[Dict[str, Any]] = Field(default_factory=list)
    channels: List[Dict[str, Any]] = Field(default_factory=list)
    module_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    history_entry: Optional[Dict[str, Any]] = None
    history_updates: List[Dict[str, Any]] = Field(default_factory=list)


class AlertEventPublishRequest(BaseModel):
    source_module: str = "manual"
    rule_name: str
    symbol: str = ""
    severity: str = "info"
    message: str = ""
    condition_summary: str = ""
    condition: Optional[str] = None
    trigger_value: Optional[float] = None
    threshold: Optional[float] = None
    rule_ids: List[str] = Field(default_factory=list)
    notify_channels: List[str] = Field(default_factory=list)
    create_workbench_task: bool = False
    workbench_task_type: str = "cross_market"
    workbench_status: str = "new"
    persist_event_record: bool = True
    cascade_actions: List[Dict[str, Any]] = Field(default_factory=list)


class ValuationLabRequest(BaseModel):
    symbol: str
    period: str = "1y"
    peer_symbols: List[str] = Field(default_factory=list)
    peer_limit: int = Field(default=6, ge=2, le=12)


class IndustryRotationLabRequest(BaseModel):
    start_date: str
    end_date: str
    rebalance_freq: str = "monthly"
    top_industries: int = 3
    stocks_per_industry: int = 3
    weight_method: str = "equal"
    initial_capital: float = 1_000_000
    commission: float = 0.001
    slippage: float = 0.001


class FactorExpressionRequest(BaseModel):
    symbol: str
    expression: str = "rank(close / sma(close, 20)) + rank(volume / sma(volume, 20))"
    period: str = "1y"
    preview_rows: int = Field(default=30, ge=5, le=120)


def _raise_500(label: str, exc: Exception) -> None:
    logger.error("%s failed: %s", label, exc, exc_info=True)
    raise HTTPException(status_code=500, detail=str(exc)) from exc


def _submit_async_quant_task(task_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    task = task_queue_manager.submit(
        name=task_name,
        payload={
            **payload,
            "task_origin": "quant_lab",
        },
        backend="auto",
    )
    return {
        "task": task,
        "execution_backend": task.get("execution_backend"),
        "message": "quant task queued",
    }


@router.post("/optimizer", summary="策略参数自动优化器")
async def run_strategy_optimizer(request: StrategyOptimizationRequest):
    try:
        return quant_lab_service.optimize_strategy(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("strategy optimizer", exc)


@router.post("/optimizer/async", summary="异步提交策略参数优化任务")
async def queue_strategy_optimizer(request: StrategyOptimizationRequest):
    try:
        return _submit_async_quant_task("quant_strategy_optimizer", request.model_dump())
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("queue strategy optimizer", exc)


@router.post("/risk-center", summary="风险分析与归因中心")
async def run_risk_center(request: RiskCenterRequest):
    try:
        return quant_lab_service.analyze_risk_center(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("risk center", exc)


@router.post("/risk-center/async", summary="异步提交风险归因任务")
async def queue_risk_center(request: RiskCenterRequest):
    try:
        return _submit_async_quant_task("quant_risk_center", request.model_dump())
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("queue risk center", exc)


@router.get("/trading-journal", summary="交易日志与绩效追踪")
async def get_trading_journal(profile_id: Optional[str] = Query(default=None)):
    try:
        return quant_lab_service.get_trading_journal(profile_id=profile_id)
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("trading journal", exc)


@router.put("/trading-journal", summary="更新交易日志扩展信息")
async def update_trading_journal(
    payload: TradingJournalUpdateRequest,
    profile_id: Optional[str] = Query(default=None),
):
    try:
        return quant_lab_service.update_trading_journal(payload.model_dump(), profile_id=profile_id)
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("update trading journal", exc)


@router.get("/alerts", summary="智能告警编排中心")
async def get_alert_orchestration(profile_id: Optional[str] = Query(default=None)):
    try:
        return quant_lab_service.get_alert_orchestration(profile_id=profile_id)
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("alert orchestration", exc)


@router.put("/alerts", summary="更新智能告警编排")
async def update_alert_orchestration(
    payload: AlertOrchestrationUpdateRequest,
    profile_id: Optional[str] = Query(default=None),
):
    try:
        return quant_lab_service.update_alert_orchestration(payload.model_dump(), profile_id=profile_id)
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("update alert orchestration", exc)


@router.post("/alerts/publish", summary="发布统一告警事件并执行级联动作")
async def publish_alert_event(
    payload: AlertEventPublishRequest,
    profile_id: Optional[str] = Query(default=None),
):
    try:
        return quant_lab_service.publish_alert_event(payload.model_dump(), profile_id=profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("publish alert event", exc)


@router.get("/data-quality", summary="数据质量可观测平台")
async def get_data_quality():
    try:
        return quant_lab_service.get_data_quality()
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("data quality", exc)


@router.post("/valuation-lab", summary="估值历史与多模型集成")
async def run_valuation_lab(request: ValuationLabRequest):
    try:
        return quant_lab_service.analyze_valuation_lab(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("valuation lab", exc)


@router.post("/valuation-lab/async", summary="异步提交估值实验任务")
async def queue_valuation_lab(request: ValuationLabRequest):
    try:
        return _submit_async_quant_task("quant_valuation_lab", request.model_dump())
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("queue valuation lab", exc)


@router.post("/industry-rotation", summary="行业轮动量化策略")
async def run_industry_rotation_lab(request: IndustryRotationLabRequest):
    try:
        return quant_lab_service.run_industry_rotation_lab(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("industry rotation lab", exc)


@router.post("/industry-rotation/async", summary="异步提交行业轮动任务")
async def queue_industry_rotation_lab(request: IndustryRotationLabRequest):
    try:
        return _submit_async_quant_task("quant_industry_rotation", request.model_dump())
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("queue industry rotation lab", exc)


@router.post("/factor-expression", summary="自定义因子表达式")
async def evaluate_factor_expression(request: FactorExpressionRequest):
    try:
        return quant_lab_service.evaluate_factor_expression(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("factor expression", exc)


@router.post("/factor-expression/async", summary="异步提交自定义因子表达式任务")
async def queue_factor_expression(request: FactorExpressionRequest):
    try:
        return _submit_async_quant_task("quant_factor_expression", request.model_dump())
    except Exception as exc:  # pragma: no cover - safety net
        _raise_500("queue factor expression", exc)
