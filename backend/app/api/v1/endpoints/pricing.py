"""
资产定价研究 API 端点
提供因子模型分析、内在价值估值和定价差异分析接口
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import logging

from src.analytics.asset_pricing import AssetPricingEngine
from src.analytics.valuation_model import ValuationModel
from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter()

# 请求模型
class PricingRequest(BaseModel):
    symbol: str = Field(..., description="股票代码，如 AAPL")
    period: str = Field(default="1y", description="分析周期: 6mo, 1y, 2y, 3y, 5y")

class ValuationRequest(BaseModel):
    symbol: str = Field(..., description="股票代码")

# 单例实例
_pricing_engine = None
_valuation_model = None
_gap_analyzer = None


def _get_pricing_engine():
    global _pricing_engine
    if _pricing_engine is None:
        _pricing_engine = AssetPricingEngine()
    return _pricing_engine


def _get_valuation_model():
    global _valuation_model
    if _valuation_model is None:
        _valuation_model = ValuationModel()
    return _valuation_model


def _get_gap_analyzer():
    global _gap_analyzer
    if _gap_analyzer is None:
        _gap_analyzer = PricingGapAnalyzer()
    return _gap_analyzer


@router.post("/factor-model")
async def factor_model_analysis(request: PricingRequest):
    """
    因子模型分析（CAPM + Fama-French 三因子）
    
    返回 Alpha、Beta、因子暴露度、R² 等指标
    """
    try:
        engine = _get_pricing_engine()
        result = engine.analyze(request.symbol, request.period)
        return result
    except Exception as e:
        logger.error(f"因子模型分析失败 {request.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/valuation")
async def valuation_analysis(request: ValuationRequest):
    """
    内在价值估值分析（DCF + 可比估值法）
    
    返回 DCF 估值、可比估值、公允价值区间
    """
    try:
        model = _get_valuation_model()
        result = model.analyze(request.symbol)
        return result
    except Exception as e:
        logger.error(f"估值分析失败 {request.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gap-analysis")
async def gap_analysis(request: PricingRequest):
    """
    定价差异分析（核心端点）
    
    整合因子模型和估值模型，分析市价 vs 内在价值的偏差及驱动因素
    """
    try:
        analyzer = _get_gap_analyzer()
        result = analyzer.analyze(request.symbol, request.period)
        return result
    except Exception as e:
        logger.error(f"定价差异分析失败 {request.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/benchmark-factors")
async def get_benchmark_factors():
    """
    获取当前市场因子数据快照
    
    返回最新的 Fama-French 三因子和市场指标
    """
    try:
        from src.analytics.asset_pricing import _fetch_ff_factors
        import pandas as pd
        
        ff = _fetch_ff_factors("6mo")
        
        if ff.empty:
            return {"error": "无法获取因子数据", "factors": {}}

        # 最近一个月的因子统计
        recent = ff.tail(21)  # ~1个月交易日
        
        factors = {}
        for col in ["Mkt-RF", "SMB", "HML", "RF"]:
            if col in recent.columns:
                series = recent[col]
                factors[col] = {
                    "mean_daily": round(float(series.mean()), 6),
                    "mean_annual": round(float(series.mean() * 252), 4),
                    "std_daily": round(float(series.std()), 6),
                    "latest": round(float(series.iloc[-1]), 6),
                    "cumulative_1m": round(float((1 + series).prod() - 1), 4)
                }

        return {
            "period": "recent_1m",
            "data_points": len(recent),
            "factors": factors,
            "last_date": str(recent.index[-1].date()) if len(recent) > 0 else None
        }
        
    except Exception as e:
        logger.error(f"获取因子数据失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
