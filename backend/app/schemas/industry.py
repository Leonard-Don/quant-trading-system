"""
行业分析 Schema 定义
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class IndustryRankResponse(BaseModel):
    """行业排名响应"""
    rank: int = Field(..., description="排名")
    industry_name: str = Field(..., description="行业名称")
    score: float = Field(..., description="综合得分")
    momentum: float = Field(0, description="动量指标")
    change_pct: float = Field(0, description="涨跌幅")
    money_flow: float = Field(0, description="资金流向")
    flow_strength: float = Field(0, description="资金强度")
    industryVolatility: float = Field(0, description="行业区间波动率(%)")
    industryVolatilitySource: str = Field("unavailable", description="行业波动率来源: historical_index/stock_dispersion/amplitude_proxy/turnover_rate_proxy/change_proxy/unavailable")
    stock_count: int = Field(0, description="成分股数量")
    total_market_cap: float = Field(0, description="总市值")
    marketCapSource: str = Field("unknown", description="行业市值来源: akshare_metadata/sina_stock_sum/sina_proxy_stock_sum/snapshot_*/estimated_*")
    mini_trend: List[float] = Field(default_factory=list, description="近5日相对走势火花线数据")
    score_breakdown: List[Dict[str, Any]] = Field(default_factory=list, description="后端统一评分拆解数据")


class StockResponse(BaseModel):
    """股票信息响应"""
    symbol: str = Field(..., description="股票代码")
    name: str = Field("", description="股票名称")
    rank: int = Field(0, description="行业内排名")
    total_score: float = Field(0, description="综合得分")
    scoreStage: Optional[str] = Field(None, description="评分阶段: quick(快速评分) 或 full(完整评分)")
    market_cap: Optional[float] = Field(None, description="市值")
    pe_ratio: Optional[float] = Field(None, description="市盈率")
    change_pct: Optional[float] = Field(None, description="涨跌幅")
    money_flow: Optional[float] = Field(None, description="主力净流入")
    turnover_rate: Optional[float] = Field(None, description="换手率")
    industry: str = Field("", description="所属行业")


class LeaderStockResponse(BaseModel):
    """龙头股推荐响应"""
    symbol: str = Field(..., description="股票代码")
    name: str = Field("", description="股票名称")
    industry: str = Field("", description="所属行业")
    score_type: Optional[str] = Field(None, description="评分类型: core(综合评分) 或 hot(动量评分)")
    global_rank: int = Field(0, description="全局排名")
    industry_rank: int = Field(0, description="行业内排名")
    total_score: float = Field(0, description="综合得分")
    market_cap: float = Field(0, description="市值")
    pe_ratio: float = Field(0, description="市盈率")
    change_pct: float = Field(0, description="涨跌幅")
    dimension_scores: Dict[str, Any] = Field(default_factory=dict, description="各维度得分")
    mini_trend: List[float] = Field(default_factory=list, description="近期价格走势火花线数据")


class LeaderDetailResponse(BaseModel):
    """龙头股详细信息响应"""
    symbol: str = Field(..., description="股票代码")
    name: str = Field("", description="股票名称")
    total_score: float = Field(0, description="综合得分")
    score_type: Optional[str] = Field(None, description="评分类型: core(综合评分) 或 hot(动量评分)")
    dimension_scores: Dict[str, Any] = Field(default_factory=dict, description="各维度得分")
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="原始数据")
    technical_analysis: Dict[str, Any] = Field(default_factory=dict, description="技术分析")
    price_data: List[Dict[str, Any]] = Field(default_factory=list, description="价格数据")


class HeatmapDataItem(BaseModel):
    """热力图数据项"""
    name: str = Field(..., description="行业名称")
    value: float = Field(..., description="涨跌幅")
    total_score: float = Field(0, description="综合得分")
    size: float = Field(0, description="市值/成交额")
    stockCount: int = Field(0, description="成分股数量")
    moneyFlow: float = Field(0, description="资金流向")
    turnoverRate: float = Field(0, description="换手率")
    industryVolatility: float = Field(0, description="行业区间波动率(%)")
    industryVolatilitySource: str = Field("unavailable", description="行业波动率来源: historical_index/stock_dispersion/amplitude_proxy/turnover_rate_proxy/change_proxy/unavailable")
    netInflowRatio: float = Field(0, description="主力净流入占比")
    leadingStock: Optional[str] = Field(None, description="领涨股")
    sizeSource: str = Field("estimated", description="热力图尺寸口径: live/snapshot/proxy/estimated，与 marketCapSource 类别保持一致")
    marketCapSource: str = Field("unknown", description="行业市值来源: akshare_metadata/sina_stock_sum/sina_proxy_stock_sum/snapshot_*/estimated_*")
    marketCapSnapshotAgeHours: Optional[float] = Field(None, description="快照市值距今小时数，仅 snapshot_* 来源时存在")
    marketCapSnapshotIsStale: bool = Field(False, description="快照市值是否超过新鲜度阈值")
    valuationSource: str = Field("unavailable", description="估值来源: akshare_sw/tencent_leader_proxy/unavailable")
    valuationQuality: str = Field("unavailable", description="估值质量: industry_level/leader_proxy/unavailable")
    dataSources: List[str] = Field(default_factory=list, description="该行业记录使用到的数据源")
    # THS 增强字段
    industryIndex: float = Field(0, description="行业指数点位")
    totalInflow: float = Field(0, description="总流入资金（亿元）")
    totalOutflow: float = Field(0, description="总流出资金（亿元）")
    leadingStockChange: float = Field(0, description="领涨股涨跌幅（%），1日特有")
    leadingStockPrice: float = Field(0, description="领涨股当前股价（元），1日特有")
    # AKShare 估值增强字段
    pe_ttm: Optional[float] = Field(None, description="滚动市盈率(PE TTM)")
    pb: Optional[float] = Field(None, description="市净率(PB)")
    dividend_yield: Optional[float] = Field(None, description="静态股息率(%)")



class HeatmapResponse(BaseModel):
    """热力图响应"""
    industries: List[HeatmapDataItem] = Field(default_factory=list, description="行业数据")
    max_value: float = Field(0, description="最大值")
    min_value: float = Field(0, description="最小值")
    update_time: str = Field(..., description="更新时间")


class HeatmapHistoryItem(BaseModel):
    """热力图历史快照"""
    snapshot_id: str = Field(..., description="快照ID")
    days: int = Field(..., description="分析周期（天）")
    captured_at: str = Field(..., description="服务端记录时间")
    update_time: str = Field(..., description="快照更新时间")
    max_value: float = Field(0, description="最大值")
    min_value: float = Field(0, description="最小值")
    industries: List[HeatmapDataItem] = Field(default_factory=list, description="行业数据")


class HeatmapHistoryResponse(BaseModel):
    """热力图历史响应"""
    items: List[HeatmapHistoryItem] = Field(default_factory=list, description="历史快照列表")


class IndustryTrendPoint(BaseModel):
    """行业趋势序列点"""
    date: str = Field(..., description="日期")
    open: Optional[float] = Field(None, description="开盘价")
    high: Optional[float] = Field(None, description="最高价")
    low: Optional[float] = Field(None, description="最低价")
    close: Optional[float] = Field(None, description="收盘价")
    volume: Optional[float] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交额")
    change_pct: Optional[float] = Field(None, description="相对前一交易日涨跌幅")


class IndustryTrendResponse(BaseModel):
    """行业趋势响应"""
    industry_name: str = Field(..., description="行业名称")
    stock_count: int = Field(0, description="成分股数量")
    expected_stock_count: int = Field(0, description="预期成分股数量")
    total_market_cap: float = Field(0, description="总市值")
    avg_pe: float = Field(0, description="平均市盈率")
    industry_volatility: float = Field(0, description="行业区间波动率(%)")
    industry_volatility_source: str = Field("unavailable", description="行业波动率来源")
    period_days: int = Field(30, description="周期天数")
    period_change_pct: float = Field(0, description="周期内行业涨跌幅")
    period_money_flow: float = Field(0, description="周期内资金流向")
    top_gainers: List[Dict[str, Any]] = Field(default_factory=list, description="涨幅前5")
    top_losers: List[Dict[str, Any]] = Field(default_factory=list, description="跌幅前5")
    rise_count: int = Field(0, description="上涨股票数")
    fall_count: int = Field(0, description="下跌股票数")
    flat_count: int = Field(0, description="平盘股票数")
    stock_coverage_ratio: float = Field(0, description="成分股覆盖率")
    change_coverage_ratio: float = Field(0, description="涨跌幅覆盖率")
    market_cap_coverage_ratio: float = Field(0, description="市值覆盖率")
    pe_coverage_ratio: float = Field(0, description="市盈率覆盖率")
    total_market_cap_fallback: bool = Field(False, description="总市值是否回退到行业聚合口径")
    avg_pe_fallback: bool = Field(False, description="平均市盈率是否回退到行业聚合口径")
    market_cap_source: str = Field("unknown", description="市值来源")
    valuation_source: str = Field("unavailable", description="估值来源")
    valuation_quality: str = Field("unavailable", description="估值质量")
    trend_series: List[IndustryTrendPoint] = Field(default_factory=list, description="行业指数趋势序列")
    degraded: bool = Field(False, description="是否为降级数据")
    note: Optional[str] = Field(None, description="降级或补充说明")
    update_time: str = Field(..., description="更新时间")


class ClusterResponse(BaseModel):
    """聚类分析响应"""
    clusters: Dict[int, List[str]] = Field(default_factory=dict, description="各簇行业列表")
    hot_cluster: int = Field(-1, description="热门簇索引")
    cluster_stats: Dict[int, Dict[str, Any]] = Field(default_factory=dict, description="各簇统计")
    points: List[Dict[str, Any]] = Field(default_factory=list, description="聚类散点数据")
    selected_cluster_count: int = Field(0, description="自动选择的聚类数")
    silhouette_score: Optional[float] = Field(None, description="最佳聚类轮廓系数")
    cluster_candidates: Dict[int, float] = Field(default_factory=dict, description="候选聚类数的轮廓系数")


class IndustryRotationResponse(BaseModel):
    """行业轮动对比响应"""
    industries: List[str] = Field(default_factory=list, description="对比行业列表")
    periods: List[int] = Field(default_factory=list, description="统计周期")
    data: List[Dict[str, Any]] = Field(default_factory=list, description="轮动数据")
    update_time: str = Field(..., description="更新时间")


class IndustryStockBuildStatusResponse(BaseModel):
    industry_name: str = Field(..., description="行业名称")
    top_n: int = Field(..., description="返回条数")
    status: str = Field(..., description="构建状态: idle/building/ready/failed")
    rows: int = Field(0, description="已构建条数")
    message: Optional[str] = Field(None, description="状态说明")
    updated_at: str = Field(..., description="状态更新时间")


class IndustryPreferencesResponse(BaseModel):
    watchlist_industries: List[str] = Field(default_factory=list, description="观察列表")
    saved_views: List[Dict[str, Any]] = Field(default_factory=list, description="保存视图")
    alert_thresholds: Dict[str, float] = Field(default_factory=dict, description="行业提醒阈值")
