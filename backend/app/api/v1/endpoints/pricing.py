"""
资产定价研究 API 端点
提供因子模型分析、内在价值估值和定价差异分析接口
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
import logging
from functools import lru_cache

from src.analytics.asset_pricing import AssetPricingEngine
from src.analytics.valuation_model import ValuationModel
from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer
from .pricing_support import (
    build_benchmark_factors_payload,
    build_screener_response,
    build_sensitivity_overrides,
    peer_candidate_pool,
    run_screening,
    search_symbol_suggestions,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# 请求模型
class PricingRequest(BaseModel):
    symbol: str = Field(..., description="股票代码，如 AAPL")
    period: str = Field(default="1y", description="分析周期: 6mo, 1y, 2y, 3y, 5y")

class ValuationRequest(BaseModel):
    symbol: str = Field(..., description="股票代码")


class ValuationSensitivityRequest(BaseModel):
    symbol: str = Field(..., description="股票代码")
    wacc: float | None = Field(default=None, description="覆盖 WACC")
    initial_growth: float | None = Field(default=None, description="覆盖初始增长率")
    terminal_growth: float | None = Field(default=None, description="覆盖终值增长率")
    fcf_margin: float | None = Field(default=None, description="覆盖现金流转化率")
    dcf_weight: float | None = Field(default=None, description="覆盖 DCF 权重")
    comparable_weight: float | None = Field(default=None, description="覆盖可比估值权重")


class PricingScreenerRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=25, description="候选股票代码列表")
    period: str = Field(default="1y", description="分析周期: 6mo, 1y, 2y, 3y, 5y")
    limit: int = Field(default=10, ge=1, le=25, description="返回前 N 个结果")
    max_workers: int = Field(default=4, ge=1, le=8, description="并行执行数")

@lru_cache(maxsize=1)
def _get_pricing_engine():
    return AssetPricingEngine()


@lru_cache(maxsize=1)
def _get_valuation_model():
    return ValuationModel()


@lru_cache(maxsize=1)
def _get_gap_analyzer():
    return PricingGapAnalyzer()


def _run_pricing_action(label: str, symbol: str, action):
    try:
        return action()
    except Exception as exc:
        logger.error("%s失败 %s: %s", label, symbol, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/factor-model")
async def factor_model_analysis(
    request: PricingRequest,
    engine: AssetPricingEngine = Depends(_get_pricing_engine),
):
    """
    因子模型分析（CAPM + Fama-French 三因子）
    
    返回 Alpha、Beta、因子暴露度、R² 等指标
    """
    return _run_pricing_action(
        "因子模型分析",
        request.symbol,
        lambda: engine.analyze(request.symbol, request.period),
    )


@router.post("/valuation")
async def valuation_analysis(
    request: ValuationRequest,
    model: ValuationModel = Depends(_get_valuation_model),
):
    """
    内在价值估值分析（DCF + 可比估值法）
    
    返回 DCF 估值、可比估值、公允价值区间
    """
    return _run_pricing_action(
        "估值分析",
        request.symbol,
        lambda: model.analyze(request.symbol),
    )


@router.post("/valuation-sensitivity")
async def valuation_sensitivity_analysis(
    request: ValuationSensitivityRequest,
    model: ValuationModel = Depends(_get_valuation_model),
):
    """
    DCF 敏感性分析

    允许覆盖折现率、增长率、终值增长率和估值权重，返回新的估值结果与敏感性矩阵。
    """
    overrides = build_sensitivity_overrides(request.model_dump())
    return _run_pricing_action(
        "估值敏感性分析",
        request.symbol,
        lambda: model.build_sensitivity_analysis(request.symbol, overrides=overrides),
    )


@router.post("/gap-analysis")
async def gap_analysis(
    request: PricingRequest,
    analyzer: PricingGapAnalyzer = Depends(_get_gap_analyzer),
):
    """
    定价差异分析（核心端点）
    
    整合因子模型和估值模型，分析市价 vs 内在价值的偏差及驱动因素
    """
    return _run_pricing_action(
        "定价差异分析",
        request.symbol,
        lambda: analyzer.analyze(request.symbol, request.period),
    )


@router.post("/screener")
async def pricing_screener(
    request: PricingScreenerRequest,
    analyzer: PricingGapAnalyzer = Depends(_get_gap_analyzer),
):
    """
    定价候选池筛选

    对一组标的运行定价差异分析，并按机会分排序返回。
    """
    return _run_pricing_action(
        "定价筛选",
        ",".join(request.symbols),
        lambda: build_screener_response(
            run_screening(analyzer, request.symbols, request.period, request.limit, request.max_workers)
        ),
    )


@router.get("/symbol-suggestions")
async def pricing_symbol_suggestions(
    q: str = Query(default="", min_length=0, max_length=50),
    limit: int = Query(default=8, ge=1, le=20),
):
    """
    股票代码/公司名搜索建议
    """
    return search_symbol_suggestions(q, limit)


@router.get("/gap-history")
async def pricing_gap_history(
    symbol: str = Query(..., min_length=1, max_length=12),
    period: str = Query(default="1y"),
    points: int = Query(default=60, ge=12, le=180),
    analyzer: PricingGapAnalyzer = Depends(_get_gap_analyzer),
):
    """历史偏差时间序列，用于观察均值回归和情绪演化。"""
    normalized_symbol = symbol.upper()
    return _run_pricing_action(
        "历史偏差序列构建",
        normalized_symbol,
        lambda: analyzer.build_gap_history(normalized_symbol, period, points),
    )


@router.get("/peers")
async def pricing_peer_comparison(
    symbol: str = Query(..., min_length=1, max_length=12),
    limit: int = Query(default=5, ge=1, le=10),
    analyzer: PricingGapAnalyzer = Depends(_get_gap_analyzer),
):
    """同行估值对比，优先从扩展研究股票池中选择更接近的同行。"""
    target_symbol = symbol.upper()
    candidate_symbols = list(peer_candidate_pool(target_symbol))
    return _run_pricing_action(
        "同行估值对比",
        target_symbol,
        lambda: analyzer.build_peer_comparison(target_symbol, candidate_symbols, limit),
    )


@router.get("/benchmark-factors")
async def get_benchmark_factors():
    """
    获取当前市场因子数据快照
    
    返回最新的 Fama-French 三因子和市场指标
    """
    from src.analytics.asset_pricing import _fetch_ff_factors

    return _run_pricing_action(
        "获取因子数据",
        "benchmark",
        lambda: build_benchmark_factors_payload(_fetch_ff_factors("6mo")),
    )
