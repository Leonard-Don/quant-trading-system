"""
资产定价研究 API 端点
提供因子模型分析、内在价值估值和定价差异分析接口
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import logging
from collections import OrderedDict
from functools import lru_cache

from src.analytics.asset_pricing import AssetPricingEngine
from src.analytics.valuation_model import ValuationModel
from src.analytics.pricing_gap_analyzer import PricingGapAnalyzer

logger = logging.getLogger(__name__)

router = APIRouter()

SYMBOL_CATALOG = [
    {"symbol": "AAPL", "name": "Apple", "group": "Mega Cap Tech", "market": "US", "aliases": ["苹果", "iphone", "consumer hardware"]},
    {"symbol": "MSFT", "name": "Microsoft", "group": "Mega Cap Tech", "market": "US", "aliases": ["微软", "azure", "office"]},
    {"symbol": "NVDA", "name": "NVIDIA", "group": "Semiconductor", "market": "US", "aliases": ["英伟达", "gpu", "ai chip"]},
    {"symbol": "AMZN", "name": "Amazon", "group": "Mega Cap Tech", "market": "US", "aliases": ["亚马逊", "aws", "ecommerce"]},
    {"symbol": "GOOGL", "name": "Alphabet", "group": "Mega Cap Tech", "market": "US", "aliases": ["谷歌", "google", "search", "youtube"]},
    {"symbol": "META", "name": "Meta Platforms", "group": "Mega Cap Tech", "market": "US", "aliases": ["facebook", "meta", "社交媒体"]},
    {"symbol": "TSLA", "name": "Tesla", "group": "EV", "market": "US", "aliases": ["特斯拉", "新能源车", "electric vehicle"]},
    {"symbol": "AMD", "name": "Advanced Micro Devices", "group": "Semiconductor", "market": "US", "aliases": ["超微半导体", "cpu", "gpu"]},
    {"symbol": "AVGO", "name": "Broadcom", "group": "Semiconductor", "market": "US", "aliases": ["博通", "network chip", "vmware"]},
    {"symbol": "NFLX", "name": "Netflix", "group": "Internet", "market": "US", "aliases": ["奈飞", "streaming", "视频流媒体"]},
    {"symbol": "PLTR", "name": "Palantir", "group": "Software", "market": "US", "aliases": ["帕兰提尔", "国防软件", "data platform"]},
    {"symbol": "SNOW", "name": "Snowflake", "group": "Software", "market": "US", "aliases": ["数据云", "data warehouse"]},
    {"symbol": "CRM", "name": "Salesforce", "group": "Software", "market": "US", "aliases": ["赛富时", "crm", "saas"]},
    {"symbol": "NOW", "name": "ServiceNow", "group": "Software", "market": "US", "aliases": ["workflow", "it service"]},
    {"symbol": "ORCL", "name": "Oracle", "group": "Software", "market": "US", "aliases": ["甲骨文", "database", "cloud infra"]},
    {"symbol": "ADBE", "name": "Adobe", "group": "Software", "market": "US", "aliases": ["奥多比", "creative cloud", "设计软件"]},
    {"symbol": "INTC", "name": "Intel", "group": "Semiconductor", "market": "US", "aliases": ["英特尔", "x86", "foundry"]},
    {"symbol": "QCOM", "name": "Qualcomm", "group": "Semiconductor", "market": "US", "aliases": ["高通", "mobile chip", "5g"]},
    {"symbol": "TXN", "name": "Texas Instruments", "group": "Semiconductor", "market": "US", "aliases": ["德州仪器", "analog chip", "工业芯片"]},
    {"symbol": "MU", "name": "Micron", "group": "Semiconductor", "market": "US", "aliases": ["美光", "memory", "dram"]},
    {"symbol": "ARM", "name": "Arm Holdings", "group": "Semiconductor", "market": "US", "aliases": ["arm", "ip chip", "芯片架构"]},
    {"symbol": "SHOP", "name": "Shopify", "group": "Software", "market": "US", "aliases": ["电商软件", "merchant platform"]},
    {"symbol": "UBER", "name": "Uber", "group": "Internet", "market": "US", "aliases": ["网约车", "mobility", "delivery"]},
    {"symbol": "ABNB", "name": "Airbnb", "group": "Internet", "market": "US", "aliases": ["爱彼迎", "travel platform", "住宿平台"]},
    {"symbol": "PYPL", "name": "PayPal", "group": "Fintech", "market": "US", "aliases": ["贝宝", "payment", "支付"]},
    {"symbol": "COIN", "name": "Coinbase", "group": "Fintech", "market": "US", "aliases": ["加密交易所", "crypto exchange"]},
    {"symbol": "JPM", "name": "JPMorgan Chase", "group": "Banks", "market": "US", "aliases": ["摩根大通", "bank", "银行"]},
    {"symbol": "GS", "name": "Goldman Sachs", "group": "Banks", "market": "US", "aliases": ["高盛", "investment bank", "投行"]},
    {"symbol": "MS", "name": "Morgan Stanley", "group": "Banks", "market": "US", "aliases": ["摩根士丹利", "wealth management"]},
    {"symbol": "BAC", "name": "Bank of America", "group": "Banks", "market": "US", "aliases": ["美国银行", "bank of america"]},
    {"symbol": "WFC", "name": "Wells Fargo", "group": "Banks", "market": "US", "aliases": ["富国银行"]},
    {"symbol": "UNH", "name": "UnitedHealth", "group": "Healthcare", "market": "US", "aliases": ["联合健康", "医保"]},
    {"symbol": "LLY", "name": "Eli Lilly", "group": "Healthcare", "market": "US", "aliases": ["礼来", "减肥药", "glp-1"]},
    {"symbol": "PFE", "name": "Pfizer", "group": "Healthcare", "market": "US", "aliases": ["辉瑞", "pharma"]},
    {"symbol": "MRK", "name": "Merck", "group": "Healthcare", "market": "US", "aliases": ["默沙东", "oncology"]},
    {"symbol": "JNJ", "name": "Johnson & Johnson", "group": "Healthcare", "market": "US", "aliases": ["强生", "medical devices"]},
    {"symbol": "COST", "name": "Costco", "group": "Consumer", "market": "US", "aliases": ["好市多", "warehouse retail"]},
    {"symbol": "WMT", "name": "Walmart", "group": "Consumer", "market": "US", "aliases": ["沃尔玛", "retail", "零售"]},
    {"symbol": "HD", "name": "Home Depot", "group": "Consumer", "market": "US", "aliases": ["家得宝", "home improvement"]},
    {"symbol": "NKE", "name": "Nike", "group": "Consumer", "market": "US", "aliases": ["耐克", "sportswear"]},
    {"symbol": "XOM", "name": "Exxon Mobil", "group": "Energy", "market": "US", "aliases": ["埃克森美孚", "oil major", "石油"]},
    {"symbol": "CVX", "name": "Chevron", "group": "Energy", "market": "US", "aliases": ["雪佛龙", "oil major"]},
    {"symbol": "SLB", "name": "Schlumberger", "group": "Energy", "market": "US", "aliases": ["油服", "oil service"]},
    {"symbol": "CAT", "name": "Caterpillar", "group": "Industrials", "market": "US", "aliases": ["卡特彼勒", "工程机械"]},
    {"symbol": "GE", "name": "GE Aerospace", "group": "Industrials", "market": "US", "aliases": ["通用电气", "aerospace"]},
    {"symbol": "DE", "name": "Deere", "group": "Industrials", "market": "US", "aliases": ["迪尔", "农机"]},
    {"symbol": "NEE", "name": "NextEra Energy", "group": "Utilities", "market": "US", "aliases": ["新能源公用事业", "utility"]},
    {"symbol": "DUK", "name": "Duke Energy", "group": "Utilities", "market": "US", "aliases": ["公用事业", "electric utility"]},
    {"symbol": "BABA", "name": "Alibaba", "group": "China ADR", "market": "US", "aliases": ["阿里巴巴", "电商", "cloud"]},
    {"symbol": "PDD", "name": "PDD Holdings", "group": "China ADR", "market": "US", "aliases": ["拼多多", "temu"]},
    {"symbol": "JD", "name": "JD.com", "group": "China ADR", "market": "US", "aliases": ["京东", "retail"]},
    {"symbol": "NIO", "name": "NIO", "group": "China EV", "market": "US", "aliases": ["蔚来"]},
    {"symbol": "XPEV", "name": "XPeng", "group": "China EV", "market": "US", "aliases": ["小鹏"]},
    {"symbol": "LI", "name": "Li Auto", "group": "China EV", "market": "US", "aliases": ["理想汽车"]},
]
POPULAR_SYMBOLS = SYMBOL_CATALOG[:12]
CATALOG_BY_SYMBOL = OrderedDict((item["symbol"], item) for item in SYMBOL_CATALOG)


def _searchable_tokens(item: dict) -> list[str]:
    values = [
        item.get("symbol", ""),
        item.get("name", ""),
        item.get("group", ""),
        item.get("market", ""),
        *(item.get("aliases") or []),
    ]
    tokens = []
    for value in values:
        normalized = str(value or "").strip().lower()
        if normalized:
            tokens.append(normalized)
    return tokens


@lru_cache(maxsize=256)
def _peer_candidate_pool(symbol: str) -> tuple[str, ...]:
    target_symbol = str(symbol or "").strip().upper()
    target_catalog = CATALOG_BY_SYMBOL.get(target_symbol, {})
    preferred_group = target_catalog.get("group", "")
    preferred_market = target_catalog.get("market", "")

    primary_candidates = [
        item["symbol"]
        for item in SYMBOL_CATALOG
        if item["symbol"] != target_symbol
        and (
            (preferred_group and item.get("group") == preferred_group)
            or (preferred_market and item.get("market") == preferred_market)
        )
    ]
    fallback_candidates = [
        item["symbol"]
        for item in SYMBOL_CATALOG
        if item["symbol"] != target_symbol and item["symbol"] not in primary_candidates
    ]
    return tuple([*primary_candidates, *fallback_candidates])

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


@router.post("/factor-model")
async def factor_model_analysis(
    request: PricingRequest,
    engine: AssetPricingEngine = Depends(_get_pricing_engine),
):
    """
    因子模型分析（CAPM + Fama-French 三因子）
    
    返回 Alpha、Beta、因子暴露度、R² 等指标
    """
    try:
        result = engine.analyze(request.symbol, request.period)
        return result
    except Exception as e:
        logger.error(f"因子模型分析失败 {request.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/valuation")
async def valuation_analysis(
    request: ValuationRequest,
    model: ValuationModel = Depends(_get_valuation_model),
):
    """
    内在价值估值分析（DCF + 可比估值法）
    
    返回 DCF 估值、可比估值、公允价值区间
    """
    try:
        result = model.analyze(request.symbol)
        return result
    except Exception as e:
        logger.error(f"估值分析失败 {request.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/valuation-sensitivity")
async def valuation_sensitivity_analysis(
    request: ValuationSensitivityRequest,
    model: ValuationModel = Depends(_get_valuation_model),
):
    """
    DCF 敏感性分析

    允许覆盖折现率、增长率、终值增长率和估值权重，返回新的估值结果与敏感性矩阵。
    """
    try:
        overrides = {
            key: value
            for key, value in request.model_dump().items()
            if key != "symbol" and value is not None
        }
        return model.build_sensitivity_analysis(request.symbol, overrides=overrides)
    except Exception as e:
        logger.error("估值敏感性分析失败 %s: %s", request.symbol, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gap-analysis")
async def gap_analysis(
    request: PricingRequest,
    analyzer: PricingGapAnalyzer = Depends(_get_gap_analyzer),
):
    """
    定价差异分析（核心端点）
    
    整合因子模型和估值模型，分析市价 vs 内在价值的偏差及驱动因素
    """
    try:
        result = analyzer.analyze(request.symbol, request.period)
        return result
    except Exception as e:
        logger.error(f"定价差异分析失败 {request.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/screener")
async def pricing_screener(
    request: PricingScreenerRequest,
    analyzer: PricingGapAnalyzer = Depends(_get_gap_analyzer),
):
    """
    定价候选池筛选

    对一组标的运行定价差异分析，并按机会分排序返回。
    """
    try:
        try:
            result = analyzer.screen(request.symbols, request.period, request.limit, request.max_workers)
        except TypeError:
            result = analyzer.screen(request.symbols, request.period, request.limit)
        return {
            **result,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("定价筛选失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbol-suggestions")
async def pricing_symbol_suggestions(
    q: str = Query(default="", min_length=0, max_length=50),
    limit: int = Query(default=8, ge=1, le=20),
):
    """
    股票代码/公司名搜索建议
    """
    query = str(q or "").strip().lower()
    if not query:
        return {"data": POPULAR_SYMBOLS[:limit], "total": min(limit, len(POPULAR_SYMBOLS))}

    ranked = []
    for item in SYMBOL_CATALOG:
        symbol = item["symbol"].lower()
        name = item["name"].lower()
        group = item["group"].lower()
        aliases = [alias.lower() for alias in item.get("aliases", [])]
        tokens = [symbol, name, group, *aliases]
        if not any(query in token for token in tokens):
            continue
        rank = 0
        if symbol.startswith(query):
            rank += 8
        if name.startswith(query):
            rank += 6
        if any(alias.startswith(query) for alias in aliases):
            rank += 5
        if query == symbol:
            rank += 12
        if query == name:
            rank += 9
        if query in group:
            rank += 2
        rank += sum(1 for token in tokens if query in token)
        ranked.append((rank, item))

    matches = [item for _, item in sorted(ranked, key=lambda pair: (-pair[0], pair[1]["symbol"]))[:limit]]
    return {"data": matches, "total": len(matches)}


@router.get("/gap-history")
async def pricing_gap_history(
    symbol: str = Query(..., min_length=1, max_length=12),
    period: str = Query(default="1y"),
    points: int = Query(default=60, ge=12, le=180),
    analyzer: PricingGapAnalyzer = Depends(_get_gap_analyzer),
):
    """历史偏差时间序列，用于观察均值回归和情绪演化。"""
    try:
        return analyzer.build_gap_history(symbol.upper(), period, points)
    except Exception as e:
        logger.error("历史偏差序列构建失败 %s: %s", symbol, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/peers")
async def pricing_peer_comparison(
    symbol: str = Query(..., min_length=1, max_length=12),
    limit: int = Query(default=5, ge=1, le=10),
    analyzer: PricingGapAnalyzer = Depends(_get_gap_analyzer),
):
    """同行估值对比，优先从扩展研究股票池中选择更接近的同行。"""
    try:
        target_symbol = symbol.upper()
        candidate_symbols = list(_peer_candidate_pool(target_symbol))
        return analyzer.build_peer_comparison(target_symbol, candidate_symbols, limit)
    except Exception as e:
        logger.error("同行估值对比失败 %s: %s", symbol, e, exc_info=True)
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
