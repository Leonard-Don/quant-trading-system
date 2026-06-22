# API参考文档

## 概述


    ## 公开量化交易研究 API

    ### 当前公开能力
    - 📊 **策略回测**: 主回测、历史复盘、组合优化与跨市场回测
    - 📈 **实时行情**: 多市场报价聚合、提醒命中记录、复盘快照与深度详情
    - 🔥 **行业热度**: 热力图、排行榜、龙头股分析与轮动观察
    - 🔌 **WebSocket 支持**: 实时报价推送与兼容层订阅确认接口
    - ⚡ **高性能后端**: 异步处理、缓存、诊断与健康检查

    ### API版本
    - **当前版本**: v5.0.0
    - **API版本**: v1
    - **最后更新**: 2026-05-02

    ### 认证
    当前版本无需认证，生产环境建议添加API密钥认证。

    ### 兼容说明
    - 实时提醒接口仍保留部分兼容字段，但系统侧工作台能力已迁移到本地私有仓。

    ### 限制
    - 请求频率: 100次/分钟
    - 数据范围: 最多5年历史数据
    - 并发回测: 最多10个
    

**版本**: 5.0.0

## 基础信息

- **基础URL**: `http://localhost:8000`
- **认证方式**: 无需认证（开发环境）
- **数据格式**: JSON
- **字符编码**: UTF-8

## API端点

### Market Data

#### GET /market-data/sources/health

**获取数据源健康状态**

Return normalized provider/source health without probing upstream APIs.

**响应: **

- **200**: Successful Response

---

#### POST /market-data/

**获取市场数据**

获取市场数据

**请求体: **

参考模型: `MarketDataRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

### Strategies

#### GET /strategies/

**获取所有可用策略**

获取系统中所有可用的交易策略
使用 lru_cache 缓存策略列表以提高性能

**响应: **

- **200**: Successful Response

---

### Backtest

#### POST /backtest/batch

**批量运行多个回测任务**

**请求体: **

参考模型: `BatchBacktestRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/walk-forward

**运行 Walk-Forward 分析**

**请求体: **

参考模型: `WalkForwardRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/market-regimes

**运行市场状态分层回测**

**请求体: **

参考模型: `MarketRegimeRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/portfolio-strategy

**运行组合级策略回测**

**请求体: **

参考模型: `PortfolioStrategyRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/

**运行策略回测**

运行交易策略回测

**请求体: **

参考模型: `BacktestRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/compare

**比较多个策略的性能**

**请求体: **

参考模型: `CompareRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/monte-carlo

**回测结果 Monte Carlo 路径模拟**

**请求体: **

参考模型: `MonteCarloBacktestRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/monte-carlo/async

**异步提交 Monte Carlo 回测任务**

**请求体: **

参考模型: `MonteCarloBacktestRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/compare/significance

**策略对比显著性检验**

**请求体: **

参考模型: `SignificanceCompareRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/compare/significance/async

**异步提交策略显著性检验任务**

**请求体: **

参考模型: `SignificanceCompareRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/multi-period

**多周期并行回测**

**请求体: **

参考模型: `MultiPeriodBacktestRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/multi-period/async

**异步提交多周期回测任务**

**请求体: **

参考模型: `MultiPeriodBacktestRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/impact-analysis

**市场冲击敏感性分析**

**请求体: **

参考模型: `MarketImpactAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/impact-analysis/async

**异步提交市场冲击分析任务**

**请求体: **

参考模型: `MarketImpactAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /backtest/history

**获取回测历史记录**

获取回测历史记录

Args:
    limit: 返回记录数量限制 (默认20)
    symbol: 按股票代码过滤
    strategy: 按策略名称过滤

**请求参数: **

- `limit` （可选）: 无描述
- `offset` （可选）: 无描述
- `symbol` （可选）: 无描述
- `strategy` （可选）: 无描述
- `record_type` （可选）: 无描述
- `summary_only` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /backtest/history/stats

**获取回测历史统计**

获取回测历史统计信息

**请求参数: **

- `symbol` （可选）: 无描述
- `strategy` （可选）: 无描述
- `record_type` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /backtest/history/{record_id}

**获取特定回测记录**

根据ID获取回测记录详情

**请求参数: **

- `record_id` （必需）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### DELETE /backtest/history/{record_id}

**删除回测记录**

删除特定回测记录

**请求参数: **

- `record_id` （必需）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/history/advanced

**保存高级实验记录到历史**

**请求体: **

参考模型: `AdvancedHistorySaveRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/report

**生成回测报告 PDF**

生成策略回测报告 PDF

如果提供了 backtest_result，则直接使用；
否则会先运行回测再生成报告。

**请求体: **

参考模型: `ReportRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /backtest/report/base64

**生成回测报告 (Base64)**

生成策略回测报告并返回 Base64 编码
适用于前端直接下载

**请求体: **

参考模型: `ReportRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

### System

#### GET /system/status

**系统状态检查**

系统状态检查接口

Args:
    detailed: 是否执行详细检查 (默认 False，仅返回基础资源使用情况)

**请求参数: **

- `detailed` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /system/performance

**获取性能指标概览**

获取性能指标

**响应: **

- **200**: Successful Response

---

#### GET /system/health-check

**综合健康检查**

综合健康检查

**响应: **

- **200**: Successful Response

---

#### GET /system/metrics

**获取详细性能指标**

获取性能指标

**响应: **

- **200**: Successful Response

---

#### GET /system/providers/status

**数据源运行状态**

Return provider registry and circuit-breaker state without probing remotes.

Also embeds the primary A-share source (Tushare) health so the frontend can
surface a green/amber/red data-source dot. ``health_check`` is cached ~60s.

**响应: **

- **200**: Successful Response

---

#### GET /system/dependencies

**依赖项连通性检查**

检查所有外部依赖项的连通性
包括：yfinance API、缓存系统、ML模型等

**响应: **

- **200**: Successful Response

---

### Realtime

#### GET /realtime/quote/{symbol}

**获取实时报价**

获取股票的统一实时报价信息。

**请求参数: **

- `symbol` （必需）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /realtime/quotes

**批量获取实时报价**

批量获取股票的统一实时报价信息。

**请求参数: **

- `symbols` （必需）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /realtime/summary

**获取实时行情运行摘要**

**响应: **

- **200**: Successful Response

---

#### GET /realtime/market-mood

**获取 Tushare 盘后市场情绪**

**请求参数: **

- `trade_date` （可选）: 无描述
- `include_bj` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /realtime/metadata

**获取实时标的元数据**

**请求参数: **

- `symbols` （必需）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /realtime/replay/{symbol}

**个股行情回放帧**

**请求参数: **

- `symbol` （必需）: 无描述
- `period` （可选）: 无描述
- `interval` （可选）: 无描述
- `limit` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /realtime/anomaly-diagnostics/{symbol}

**统计异常波动诊断**

**请求参数: **

- `symbol` （必需）: 无描述
- `period` （可选）: 无描述
- `interval` （可选）: 无描述
- `limit` （可选）: 无描述
- `z_window` （可选）: 无描述
- `return_z_threshold` （可选）: 无描述
- `volume_z_threshold` （可选）: 无描述
- `cusum_threshold_sigma` （可选）: 无描述
- `pattern_lookback` （可选）: 无描述
- `pattern_matches` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /realtime/orderbook/{symbol}

**Level 2 订单簿能力探测**

**请求参数: **

- `symbol` （必需）: 无描述
- `levels` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /realtime/preferences

**获取实时行情偏好配置**

**响应: **

- **200**: Successful Response

---

#### PUT /realtime/preferences

**更新实时行情偏好配置**

**请求体: **

参考模型: `RealtimePreferencesRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /realtime/alerts

**获取实时提醒规则**

**响应: **

- **200**: Successful Response

---

#### PUT /realtime/alerts

**更新实时提醒规则**

**请求体: **

参考模型: `RealtimeAlertsRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /realtime/alerts/hits

**记录实时提醒命中**

**请求体: **

参考模型: `RealtimeAlertHitRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /realtime/journal

**获取实时行情复盘与时间线**

**响应: **

- **200**: Successful Response

---

#### PUT /realtime/journal

**更新实时行情复盘与时间线**

**请求体: **

参考模型: `RealtimeJournalRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /realtime/subscribe

**兼容层：确认订阅请求**

兼容旧客户端的订阅确认接口，不维护持久订阅态。

**请求体: **

参考模型: `SubscriptionRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /realtime/unsubscribe

**兼容层：确认取消订阅请求**

兼容旧客户端的取消订阅确认接口，不维护持久订阅态。

**请求体: **

参考模型: `SubscriptionRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

### Analysis

#### POST /analysis/analyze

**分析股票趋势**

分析股票趋势，返回趋势方向、支撑阻力位和技术评分

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/comprehensive

**综合分析**

综合分析股票，整合趋势、量价、情绪等多维度分析
返回综合评分和投资建议

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/overview

**分析总览**

轻量总览分析，返回评分与关键信号

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/fundamental

**基本面分析**

基本面分析

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/klines

**K线数据**

获取K线数据（默认150条）

**请求参数: **

- `limit` （可选）: 无描述

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/volume-price

**量价分析**

分析成交量与价格的关系

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/sentiment

**市场情绪分析**

分析市场情绪和恐慌程度

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/patterns

**形态识别**

识别K线形态和图表形态

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/prediction

**AI价格预测**

使用AI模型预测未来价格

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/correlation

**多股票相关性分析**

分析多只股票之间的价格相关性
返回相关性矩阵和统计信息

**请求体: **

参考模型: `CorrelationRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/prediction/compare

**多模型预测对比**

使用多个模型进行预测并对比结果
同时返回 Random Forest 和 LSTM 的预测结果

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/prediction/lstm

**LSTM 模型预测**

使用 LSTM 神经网络模型进行价格预测

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/train/all

**训练所有模型**

为指定股票训练所有可用的预测模型
包括 Random Forest 和 LSTM

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/technical-indicators

**技术指标快照**

获取常用技术指标快照（RSI、MACD、布林带）

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/sentiment-history

**历史情绪趋势**

获取过去N天的恐慌贪婪指数历史趋势

**请求参数: **

- `days` （可选）: 无描述

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/industry-comparison

**行业对比分析**

获取同行业公司的关键指标对比

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /analysis/risk-metrics

**风险评估增强**

获取 VaR、最大回撤、夏普比率等风险指标

**请求体: **

参考模型: `TrendAnalysisRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

### Optimization

#### POST /optimization/optimize

**投资组合优化**

计算投资组合的最优资产配置权重

**请求体: **

参考模型: `Body_optimize_portfolio_optimization_optimize_post`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

### Industry Analysis

#### GET /industry/industries/heatmap

**Get Industry Heatmap**

获取行业热力图数据

返回所有行业的涨跌幅和市值数据，用于渲染热力图可视化。

**请求参数: **

- `days` （可选）: 分析周期（天）

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/industries/heatmap/history

**Get Industry Heatmap History**

获取行业热力图历史快照。

用于行业热度模块的历史回放。当前返回服务端近期保留的快照窗口。

**请求参数: **

- `limit` （可选）: 返回快照数量
- `days` （可选）: 按周期过滤

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/bootstrap

**Get Industry Bootstrap**

**请求参数: **

- `days` （可选）: 热力图与默认热度排序使用的周期
- `ranking_top_n` （可选）: 预热排行榜条数
- `leader_top_n` （可选）: 预热龙头股总条数
- `top_industries` （可选）: 龙头股从前N个热门行业中选取
- `per_industry` （可选）: 每个行业选取的龙头数量

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/leaders

**Get Leader Stocks**

获取龙头股推荐列表

- hot (热点先锋): 使用独立的 0-100 动量评分，聚焦短期涨势与资金关注度。
- core (核心资产): 使用 0-100 综合评分，侧重长线基本面与流动性。

**请求参数: **

- `top_n` （可选）: 返回龙头股数量
- `top_industries` （可选）: 从前N个热门行业中选取
- `per_industry` （可选）: 每个行业选取的龙头数量
- `list_type` （可选）: 榜单类型：hot(热点先锋) 或 core(核心资产)

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/leaders/overview

**Get Leader Boards**

一次性返回核心资产与热点先锋榜单，减少前端冷启动的双请求成本。

**请求参数: **

- `top_n` （可选）: 返回龙头股数量
- `top_industries` （可选）: 从前N个热门行业中选取
- `per_industry` （可选）: 每个行业选取的龙头数量

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/leaders/{symbol}/detail

**Get Leader Detail**

获取龙头股详细分析

返回指定股票的完整分析报告，包括评分详情、技术分析和历史价格。

- **symbol**: 股票代码（如 "000001"、"600519"）

**请求参数: **

- `symbol` （必需）: 无描述
- `score_type` （可选）: 评分类型: core 或 hot

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/industries/hot

**Get Hot Industries**

获取热门行业排名

基于动量、资金流向和成交量变化综合评分，识别当前市场关注度高的行业。

- **top_n**: 返回排名前 N 的行业
- **lookback_days**: 用于计算动量和资金流向的回看周期
- **sort_by**: 排序字段 (total_score, change_pct, money_flow, industry_volatility)
- **order**: 排序顺序 (desc, asc)
- **include_policy_signal**: 可选，附带 policy_radar 行业级政策信号；缺数据时为 None

**请求参数: **

- `top_n` （可选）: 返回前N个热门行业
- `lookback_days` （可选）: 回看周期（天）
- `sort_by` （可选）: 排序字段: total_score, change_pct, money_flow, industry_volatility
- `order` （可选）: 排序顺序: desc, asc
- `include_policy_signal` （可选）: 是否在每一行附带 policy_radar 政策信号 (avg_impact / mentions / signal / last_refresh_at)。默认 false，保持既有调用方不变；缺少政策数据的行业返回 None。

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/industries/{industry_name}/stocks

**Get Industry Stocks**

获取行业成分股及排名

返回指定行业内按综合得分排名的股票列表。

- **industry_name**: 行业名称（如 "电子"、"医药生物"）
- **top_n**: 返回排名前 N 的股票

**请求参数: **

- `industry_name` （必需）: 无描述
- `top_n` （可选）: 返回前N只股票

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/industries/{industry_name}/stocks/status

**Get Industry Stock Build Status**

**请求参数: **

- `industry_name` （必需）: 无描述
- `top_n` （可选）: 返回前N只股票

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/industries/{industry_name}/stocks/stream

**Stream Industry Stock Build Status**

**请求参数: **

- `industry_name` （必需）: 无描述
- `top_n` （可选）: 返回前N只股票

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/preferences

**Get Industry Preferences**

**响应: **

- **200**: Successful Response

---

#### PUT /industry/preferences

**Update Industry Preferences**

**请求体: **

参考模型: `IndustryPreferencesResponse`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/preferences/export

**Export Industry Preferences**

**响应: **

- **200**: Successful Response

---

#### POST /industry/preferences/import

**Import Industry Preferences**

**请求体: **

参考模型: `IndustryPreferencesResponse`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/industries/{industry_name}/trend

**Get Industry Trend**

获取行业趋势分析

返回指定行业的详细趋势分析，包括涨幅/跌幅前5的股票。

**请求参数: **

- `industry_name` （必需）: 无描述
- `days` （可选）: 分析周期（天）

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/industries/clusters

**Get Industry Clusters**

获取行业聚类分析

使用 K-Means 算法将行业聚类为热门组和非热门组。

**请求参数: **

- `n_clusters` （可选）: 聚类数量

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/industries/rotation

**Get Industry Rotation**

获取行业轮动对比数据

比较多个行业在不同时间周期的涨跌幅表现。

- **industries**: 行业名称列表，用逗号分隔（如2-5个）

**请求参数: **

- `industries` （必需）: 行业名称列表，逗号分隔
- `periods` （可选）: 统计周期列表，逗号分隔，如 1,5,20

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/industries/intelligence

**行业生命周期、ETF 映射与事件日历**

**请求参数: **

- `top_n` （可选）: 分析前 N 个热门行业
- `lookback_days` （可选）: 热度回看周期

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/industries/network

**行业相关性网络图**

**请求参数: **

- `top_n` （可选）: 网络节点数量
- `lookback_days` （可选）: 热度回看周期
- `min_similarity` （可选）: 最小相似度

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /industry/health

**Health Check**

行业分析模块健康检查 + 数据源状态

返回当前活跃数据源、能力、连接状态等详细信息

**响应: **

- **200**: Successful Response

---

### Events

#### POST /events/summary

**获取股票相关事件**

获取股票的事件信息，包括财报、分红和新闻

**请求体: **

参考模型: `EventRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

### Cross Market

#### GET /cross-market/templates

**Get cross-market demo templates**

**响应: **

- **200**: Successful Response

---

#### POST /cross-market/backtest

**Run cross-market backtest**

**请求体: **

参考模型: `CrossMarketBacktestRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

### Infrastructure

#### GET /infrastructure/status

**基础设施状态**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/auth/token

**签发本地研究令牌**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**请求体: **

参考模型: `TokenRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/auth/login

**本地用户密码登录**

**请求体: **

参考模型: `LoginRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/auth/refresh

**使用 refresh token 刷新访问令牌**

**请求体: **

参考模型: `RefreshRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/oauth/token

**OAuth2 Password / Refresh Token 交换**

**请求体: **

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /infrastructure/auth/users

**查看本地用户目录**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/auth/users

**创建或更新本地用户**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**请求体: **

参考模型: `AuthUserRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /infrastructure/auth/oauth/providers

**查看 OAuth Provider 配置**

**响应: **

- **200**: Successful Response

---

#### POST /infrastructure/auth/oauth/providers

**创建或更新 OAuth Provider**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**请求体: **

参考模型: `OAuthProviderRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/auth/oauth/providers/sync-env

**从环境变量同步 OAuth Provider**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /infrastructure/auth/oauth/providers/{provider_id}/diagnostics

**诊断 OAuth Provider 配置**

**请求参数: **

- `provider_id` （必需）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/auth/oauth/providers/{provider_id}/authorize

**生成 OAuth 授权链接**

**请求参数: **

- `provider_id` （必需）: 无描述

**请求体: **

参考模型: `OAuthAuthorizationRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/auth/oauth/providers/{provider_id}/exchange

**交换 OAuth 授权码**

**请求参数: **

- `provider_id` （必需）: 无描述

**请求体: **

参考模型: `OAuthExchangeRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /infrastructure/auth/oauth/providers/{provider_id}/callback

**OAuth 登录回调**

**请求参数: **

- `provider_id` （必需）: 无描述
- `code` （可选）: 无描述
- `state` （可选）: 无描述
- `error` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/auth/sessions/{session_id}/revoke

**撤销 refresh session**

**请求参数: **

- `session_id` （必需）: 无描述
- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/auth/policy

**更新认证策略**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**请求体: **

参考模型: `AuthPolicyRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/tasks

**提交异步任务**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**请求体: **

参考模型: `TaskRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /infrastructure/tasks

**查看任务队列**

**请求参数: **

- `limit` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /infrastructure/tasks/{task_id}

**查看任务状态**

**请求参数: **

- `task_id` （必需）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/tasks/{task_id}/cancel

**取消异步任务**

**请求参数: **

- `task_id` （必需）: 无描述
- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/rate-limits

**更新按用户 / 按端点限流规则**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**请求体: **

参考模型: `RateLimitUpdateRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/persistence/records

**写入持久化记录**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**请求体: **

参考模型: `RecordRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /infrastructure/persistence/records

**读取持久化记录**

**请求参数: **

- `record_type` （可选）: 无描述
- `limit` （可选）: 无描述
- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /infrastructure/persistence/diagnostics

**查看数据库 / TimescaleDB 接入诊断**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/persistence/bootstrap

**初始化 PostgreSQL / TimescaleDB 持久化结构**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**请求体: **

参考模型: `PersistenceBootstrapRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /infrastructure/persistence/migration/preview

**预览 SQLite fallback -> PostgreSQL 迁移**

**请求参数: **

- `sqlite_path` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/persistence/migration/run

**执行 SQLite fallback -> PostgreSQL 迁移**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**请求体: **

参考模型: `PersistenceMigrationRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/persistence/timeseries

**写入时序记录**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**请求体: **

参考模型: `TimeSeriesRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /infrastructure/persistence/timeseries

**读取时序记录**

**请求参数: **

- `series_name` （可选）: 无描述
- `symbol` （可选）: 无描述
- `limit` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/config-versions

**保存配置版本**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**请求体: **

参考模型: `ConfigVersionRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /infrastructure/config-versions

**读取配置版本**

**请求参数: **

- `config_type` （必需）: 无描述
- `config_key` （必需）: 无描述
- `owner_id` （可选）: 无描述
- `limit` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### GET /infrastructure/config-versions/diff

**对比配置版本**

**请求参数: **

- `config_type` （必需）: 无描述
- `config_key` （必需）: 无描述
- `from_version` （必需）: 无描述
- `to_version` （必需）: 无描述
- `owner_id` （可选）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/config-versions/restore

**从历史配置恢复为新版本**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**请求体: **

参考模型: `ConfigRestoreRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/notifications/test

**测试通知通道**

**请求参数: **

- `authorization` （可选）: 无描述
- `x-api-key` （可选）: 无描述

**请求体: **

参考模型: `NotificationRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### POST /infrastructure/notifications/channels

**保存通知渠道**

**请求体: **

参考模型: `NotificationChannelRequest`

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

#### DELETE /infrastructure/notifications/channels/{channel_id}

**删除通知渠道**

**请求参数: **

- `channel_id` （必需）: 无描述

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

### Policy Radar

#### GET /policy-radar/signal

**获取最新政策雷达综合信号**

返回 PolicySignalProvider 的最新汇总信号：industry_signals / source_health / policy_count / last_refresh。底层数据来自 AltDataManager 的 60 分钟缓存，不会触发现场抓取或 NLP 推理。

**响应: **

- **200**: Successful Response

---

#### GET /policy-radar/records

**获取政策雷达历史记录**

按时间倒序返回最近的政策记录，可选按行业 tag 过滤。`industry` 与记录 tags 完全匹配（区分大小写按字面值）。`timeframe` 形如 `7d` / `30d`。

**请求参数: **

- `industry` （可选）: 可选：仅返回 tags 包含该值的记录
- `timeframe` （可选）: 时间窗（如 7d / 30d）
- `limit` （可选）: 最多返回的记录条数

**响应: **

- **200**: Successful Response
- **422**: Validation Error

---

### 未分类

#### GET /

**Root**

根路径

**响应: **

- **200**: Successful Response

---

### 健康检查

#### GET /health

**基础健康检查**

基础健康检查接口

**响应: **

- **200**: Successful Response

---

## 实时行情说明

- **正式实时订阅入口**: `WS /ws/quotes`
- **兼容层接口**: `POST /realtime/subscribe` 与 `POST /realtime/unsubscribe`
- **兼容层说明**: 仅用于兼容旧客户端，返回订阅确认，不维护持久订阅态
- **报价字段**: `symbol, price, change, change_percent, volume, high, low, open, previous_close, bid, ask, timestamp, source`

## 数据模型

### AdvancedHistorySaveRequest

**字段: **

- `record_type` (string): 无描述
- `title` (unknown): 无描述
- `symbol` (string): 无描述
- `strategy` (string): 无描述
- `parameters` (object): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `metrics` (object): 无描述
- `result` (object): 无描述

### AuthPolicyRequest

**字段: **

- `required` (boolean): 无描述

### AuthUserRequest

**字段: **

- `subject` (string): 无描述
- `password` (unknown): 无描述
- `role` (string): 无描述
- `display_name` (string): 无描述
- `enabled` (boolean): 无描述
- `scopes` (array): 无描述
- `metadata` (object): 无描述

### BacktestRequest

**字段: **

- `symbol` (string): 无描述
- `strategy` (string): 无描述
- `parameters` (object): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述
- `fixed_commission` (number): 无描述
- `min_commission` (number): 无描述
- `market_impact_bps` (number): 无描述
- `market_impact_model` (string): 无描述
- `impact_reference_notional` (number): 无描述
- `impact_coefficient` (number): 无描述
- `permanent_impact_bps` (number): 无描述
- `execution_lag` (integer): 无描述
- `max_holding_days` (unknown): 无描述

### BacktestResponse

**字段: **

- `success` (boolean): 无描述
- `data` (unknown): 无描述
- `error` (unknown): 无描述

### BatchBacktestRequest

**字段: **

- `tasks` (array): 无描述
- `ranking_metric` (string): 无描述
- `ascending` (boolean): 无描述
- `top_n` (unknown): 无描述
- `max_workers` (integer): 无描述
- `use_processes` (boolean): 无描述
- `timeout_seconds` (number): 无描述

### BatchBacktestTaskRequest

**字段: **

- `task_id` (unknown): 无描述
- `research_label` (unknown): 无描述
- `symbol` (string): 无描述
- `strategy` (string): 无描述
- `parameters` (object): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述
- `fixed_commission` (number): 无描述
- `min_commission` (number): 无描述
- `market_impact_bps` (number): 无描述
- `market_impact_model` (string): 无描述
- `impact_reference_notional` (number): 无描述
- `impact_coefficient` (number): 无描述
- `permanent_impact_bps` (number): 无描述
- `execution_lag` (integer): 无描述
- `max_holding_days` (unknown): 无描述

### Body_issue_oauth_token_infrastructure_oauth_token_post

**字段: **

- `grant_type` (string): 无描述
- `username` (unknown): 无描述
- `password` (unknown): 无描述
- `refresh_token` (unknown): 无描述
- `scope` (string): 无描述

### Body_optimize_portfolio_optimization_optimize_post

**字段: **

- `symbols` (array): 无描述
- `period` (string): 无描述
- `objective` (string): 无描述

### ClusterResponse

聚类分析响应

**字段: **

- `clusters` (object): 各簇行业列表
- `hot_cluster` (integer): 热门簇索引
- `cluster_stats` (object): 各簇统计
- `points` (array): 聚类散点数据
- `selected_cluster_count` (integer): 自动选择的聚类数
- `silhouette_score` (unknown): 最佳聚类轮廓系数
- `cluster_candidates` (object): 候选聚类数的轮廓系数

### CompareRequest

**字段: **

- `symbol` (string): 无描述
- `strategies` (unknown): 无描述
- `strategy_configs` (unknown): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述
- `fixed_commission` (number): 无描述
- `min_commission` (number): 无描述
- `market_impact_bps` (number): 无描述
- `market_impact_model` (string): 无描述
- `impact_reference_notional` (number): 无描述
- `impact_coefficient` (number): 无描述
- `permanent_impact_bps` (number): 无描述
- `execution_lag` (integer): 无描述
- `max_holding_days` (unknown): 无描述

### CompareStrategyConfig

**字段: **

- `name` (string): 无描述
- `parameters` (object): 无描述

### ConfigRestoreRequest

**字段: **

- `config_type` (string): 无描述
- `config_key` (string): 无描述
- `version` (integer): 无描述
- `owner_id` (string): 无描述

### ConfigVersionRequest

**字段: **

- `config_type` (string): 无描述
- `config_key` (string): 无描述
- `payload` (object): 无描述
- `owner_id` (string): 无描述

### CorrelationRequest

**字段: **

- `symbols` (array): 无描述
- `period_days` (integer): 无描述

### CrossMarketAllocationConstraints

**字段: **

- `max_single_weight` (unknown): 无描述
- `min_single_weight` (unknown): 无描述

### CrossMarketAsset

**字段: **

- `symbol` (string): Ticker symbol, e.g. XLU
- `asset_class` (string): 无描述
- `side` (string): 无描述
- `weight` (unknown): 无描述

### CrossMarketBacktestRequest

**字段: **

- `assets` (array): 无描述
- `template_context` (unknown): 无描述
- `allocation_constraints` (unknown): 无描述
- `strategy` (string): 无描述
- `construction_mode` (string): 无描述
- `parameters` (object): 无描述
- `min_history_days` (integer): 无描述
- `min_overlap_ratio` (number): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述

### CrossMarketBacktestResponse

**字段: **

- `success` (boolean): 无描述
- `data` (unknown): 无描述
- `error` (unknown): 无描述

### CrossMarketTemplateAsset

**字段: **

- `symbol` (string): Ticker symbol, e.g. XLU
- `asset_class` (string): 无描述
- `side` (string): 无描述
- `weight` (unknown): 无描述

### CrossMarketTemplateContext

**字段: **

- `template_id` (unknown): 无描述
- `template_name` (unknown): 无描述
- `theme` (unknown): 无描述
- `allocation_mode` (unknown): 无描述
- `bias_summary` (unknown): 无描述
- `bias_strength_raw` (unknown): 无描述
- `bias_strength` (unknown): 无描述
- `bias_scale` (unknown): 无描述
- `bias_quality_label` (unknown): 无描述
- `bias_quality_reason` (unknown): 无描述
- `base_recommendation_score` (unknown): 无描述
- `recommendation_score` (unknown): 无描述
- `base_recommendation_tier` (unknown): 无描述
- `recommendation_tier` (unknown): 无描述
- `ranking_penalty` (unknown): 无描述
- `ranking_penalty_reason` (unknown): 无描述
- `input_reliability_label` (unknown): 无描述
- `input_reliability_score` (unknown): 无描述
- `input_reliability_lead` (unknown): 无描述
- `input_reliability_posture` (unknown): 无描述
- `input_reliability_reason` (unknown): 无描述
- `input_reliability_action_hint` (unknown): 无描述
- `department_chaos_label` (unknown): 无描述
- `department_chaos_score` (unknown): 无描述
- `department_chaos_top_department` (unknown): 无描述
- `department_chaos_reason` (unknown): 无描述
- `department_chaos_risk_budget_scale` (unknown): 无描述
- `policy_execution_label` (unknown): 无描述
- `policy_execution_score` (unknown): 无描述
- `policy_execution_top_department` (unknown): 无描述
- `policy_execution_reason` (unknown): 无描述
- `policy_execution_risk_budget_scale` (unknown): 无描述
- `people_fragility_label` (unknown): 无描述
- `people_fragility_score` (unknown): 无描述
- `people_fragility_focus` (unknown): 无描述
- `people_fragility_reason` (unknown): 无描述
- `people_fragility_risk_budget_scale` (unknown): 无描述
- `source_mode_label` (unknown): 无描述
- `source_mode_dominant` (unknown): 无描述
- `source_mode_reason` (unknown): 无描述
- `source_mode_risk_budget_scale` (unknown): 无描述
- `structural_decay_radar_label` (unknown): 无描述
- `structural_decay_radar_display_label` (unknown): 无描述
- `structural_decay_radar_score` (unknown): 无描述
- `structural_decay_radar_action_hint` (unknown): 无描述
- `structural_decay_radar_risk_budget_scale` (unknown): 无描述
- `structural_decay_radar_top_signals` (array): 无描述
- `bias_highlights_raw` (array): 无描述
- `bias_highlights` (array): 无描述
- `bias_actions` (array): 无描述
- `signal_attribution` (array): 无描述
- `driver_summary` (array): 无描述
- `dominant_drivers` (array): 无描述
- `core_legs` (array): 无描述
- `support_legs` (array): 无描述
- `theme_core` (unknown): 无描述
- `theme_support` (unknown): 无描述
- `execution_posture` (unknown): 无描述
- `base_assets` (array): 无描述
- `raw_bias_assets` (array): 无描述

### EventRequest

**字段: **

- `symbol` (string): 无描述

### HTTPValidationError

**字段: **

- `detail` (array): 无描述

### HeatmapDataItem

热力图数据项

**字段: **

- `name` (string): 行业名称
- `value` (number): 涨跌幅
- `total_score` (number): 综合得分
- `size` (number): 市值/成交额
- `stockCount` (integer): 成分股数量
- `moneyFlow` (number): 资金流向
- `turnoverRate` (number): 换手率
- `industryVolatility` (number): 行业区间波动率(%)
- `industryVolatilitySource` (string): 行业波动率来源: historical_index/stock_dispersion/amplitude_proxy/turnover_rate_proxy/change_proxy/unavailable
- `netInflowRatio` (number): 主力净流入占比
- `leadingStock` (unknown): 领涨股
- `leadingStockSymbol` (unknown): 领涨股代码
- `sizeSource` (string): 热力图尺寸口径: live/snapshot/proxy/estimated，与 marketCapSource 类别保持一致
- `marketCapSource` (string): 行业市值来源: akshare_metadata/sina_stock_sum/sina_proxy_stock_sum/snapshot_*/estimated_*
- `marketCapSnapshotAgeHours` (unknown): 快照市值距今小时数，仅 snapshot_* 来源时存在
- `marketCapSnapshotIsStale` (boolean): 快照市值是否超过新鲜度阈值
- `valuationSource` (string): 估值来源: akshare_sw/tencent_leader_proxy/unavailable
- `valuationQuality` (string): 估值质量: industry_level/leader_proxy/unavailable
- `dataSources` (array): 该行业记录使用到的数据源
- `industryIndex` (number): 行业指数点位
- `totalInflow` (number): 总流入资金（亿元）
- `totalOutflow` (number): 总流出资金（亿元）
- `leadingStockChange` (number): 领涨股涨跌幅（%），1日特有
- `leadingStockPrice` (number): 领涨股当前股价（元），1日特有
- `pe_ttm` (unknown): 滚动市盈率(PE TTM)
- `pb` (unknown): 市净率(PB)
- `dividend_yield` (unknown): 静态股息率(%)

### HeatmapHistoryItem

热力图历史快照

**字段: **

- `snapshot_id` (string): 快照ID
- `days` (integer): 分析周期（天）
- `captured_at` (string): 服务端记录时间
- `update_time` (string): 快照更新时间
- `max_value` (number): 最大值
- `min_value` (number): 最小值
- `industries` (array): 行业数据

### HeatmapHistoryResponse

热力图历史响应

**字段: **

- `items` (array): 历史快照列表

### HeatmapResponse

热力图响应

**字段: **

- `industries` (array): 行业数据
- `max_value` (number): 最大值
- `min_value` (number): 最小值
- `update_time` (string): 更新时间

### IndustryBootstrapResponse

行业页首屏 bootstrap 响应

**字段: **

- `days` (integer): 热力图与默认热度排序使用的周期
- `ranking_top_n` (integer): 预热的排行榜条数
- `ranking_type` (string): 预热排行榜类型
- `ranking_sort_by` (string): 预热排行榜排序字段
- `ranking_order` (string): 预热排行榜排序方向
- `heatmap` (unknown): 热力图首屏数据
- `hot_industries` (array): 预热后的行业排行榜
- `leaders` (unknown): 龙头股双榜单
- `errors` (object): 非阻断预热错误

### IndustryPolicySignal

行业级政策雷达信号（policy_radar industry_signals 投影）

**字段: **

- `avg_impact` (unknown): 平均影响强度，正值偏多/负值偏空
- `mentions` (integer): 近期政策提及次数
- `signal` (string): 信号分类: bullish / bearish / neutral
- `last_refresh_at` (unknown): policy_radar 最后刷新时间 (ISO 8601)

### IndustryPreferencesResponse

**字段: **

- `watchlist_industries` (array): 观察列表
- `saved_views` (array): 保存视图
- `alert_thresholds` (object): 行业提醒阈值

### IndustryRankResponse

行业排名响应

**字段: **

- `rank` (integer): 排名
- `industry_name` (string): 行业名称
- `score` (number): 综合得分
- `momentum` (number): 动量指标
- `change_pct` (number): 涨跌幅
- `money_flow` (number): 资金流向
- `flow_strength` (number): 资金强度
- `industryVolatility` (number): 行业区间波动率(%)
- `industryVolatilitySource` (string): 行业波动率来源: historical_index/stock_dispersion/amplitude_proxy/turnover_rate_proxy/change_proxy/unavailable
- `stock_count` (integer): 成分股数量
- `total_market_cap` (number): 总市值
- `marketCapSource` (string): 行业市值来源: akshare_metadata/sina_stock_sum/sina_proxy_stock_sum/snapshot_*/estimated_*
- `mini_trend` (array): 近5日相对走势火花线数据
- `score_breakdown` (array): 后端统一评分拆解数据
- `policy_signal` (unknown): 行业政策雷达信号（仅当 include_policy_signal=true 时返回，无数据时为 None）

### IndustryRotationResponse

行业轮动对比响应

**字段: **

- `industries` (array): 对比行业列表
- `periods` (array): 统计周期
- `data` (array): 轮动数据
- `update_time` (string): 更新时间

### IndustryStockBuildStatusResponse

**字段: **

- `industry_name` (string): 行业名称
- `top_n` (integer): 返回条数
- `status` (string): 构建状态: idle/building/ready/failed
- `rows` (integer): 已构建条数
- `message` (unknown): 状态说明
- `updated_at` (string): 状态更新时间

### IndustryTrendPoint

行业趋势序列点

**字段: **

- `date` (string): 日期
- `open` (unknown): 开盘价
- `high` (unknown): 最高价
- `low` (unknown): 最低价
- `close` (unknown): 收盘价
- `volume` (unknown): 成交量
- `amount` (unknown): 成交额
- `change_pct` (unknown): 相对前一交易日涨跌幅

### IndustryTrendResponse

行业趋势响应

**字段: **

- `industry_name` (string): 行业名称
- `stock_count` (integer): 成分股数量
- `expected_stock_count` (integer): 预期成分股数量
- `total_market_cap` (number): 总市值
- `avg_pe` (number): 平均市盈率
- `industry_volatility` (number): 行业区间波动率(%)
- `industry_volatility_source` (string): 行业波动率来源
- `period_days` (integer): 周期天数
- `period_change_pct` (number): 周期内行业涨跌幅
- `period_money_flow` (number): 周期内资金流向
- `top_gainers` (array): 涨幅前5
- `top_losers` (array): 跌幅前5
- `rise_count` (integer): 上涨股票数
- `fall_count` (integer): 下跌股票数
- `flat_count` (integer): 平盘股票数
- `stock_coverage_ratio` (number): 成分股覆盖率
- `change_coverage_ratio` (number): 涨跌幅覆盖率
- `market_cap_coverage_ratio` (number): 市值覆盖率
- `pe_coverage_ratio` (number): 市盈率覆盖率
- `total_market_cap_fallback` (boolean): 总市值是否回退到行业聚合口径
- `avg_pe_fallback` (boolean): 平均市盈率是否回退到行业聚合口径
- `market_cap_source` (string): 市值来源
- `valuation_source` (string): 估值来源
- `valuation_quality` (string): 估值质量
- `trend_series` (array): 行业指数趋势序列
- `degraded` (boolean): 是否为降级数据
- `note` (unknown): 降级或补充说明
- `update_time` (string): 更新时间

### LeaderBoardsResponse

龙头股双榜单响应

**字段: **

- `core` (array): 核心资产榜单
- `hot` (array): 热点先锋榜单
- `errors` (object): 部分榜单失败时的错误提示

### LeaderDetailResponse

龙头股详细信息响应

**字段: **

- `symbol` (string): 股票代码
- `name` (string): 股票名称
- `total_score` (number): 综合得分
- `score_type` (unknown): 评分类型: core(综合评分) 或 hot(动量评分)
- `dimension_scores` (object): 各维度得分
- `raw_data` (object): 原始数据
- `technical_analysis` (object): 技术分析
- `price_data` (array): 价格数据
- `degraded` (boolean): 是否为降级详情
- `note` (unknown): 降级或回退说明

### LeaderStockResponse

龙头股推荐响应

**字段: **

- `symbol` (string): 股票代码
- `name` (string): 股票名称
- `industry` (string): 所属行业
- `score_type` (unknown): 评分类型: core(综合评分) 或 hot(动量评分)
- `global_rank` (integer): 全局排名
- `industry_rank` (integer): 行业内排名
- `total_score` (number): 综合得分
- `market_cap` (number): 市值
- `pe_ratio` (number): 市盈率
- `change_pct` (number): 涨跌幅
- `dimension_scores` (object): 各维度得分
- `mini_trend` (array): 近期价格走势火花线数据

### LoginRequest

**字段: **

- `subject` (string): 无描述
- `password` (string): 无描述
- `expires_in_seconds` (integer): 无描述
- `refresh_expires_in_seconds` (integer): 无描述

### MarketDataRequest

**字段: **

- `symbol` (string): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `interval` (string): 无描述
- `period` (unknown): 无描述

### MarketImpactAnalysisRequest

**字段: **

- `symbol` (string): 无描述
- `strategy` (string): 无描述
- `parameters` (object): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述
- `fixed_commission` (number): 无描述
- `min_commission` (number): 无描述
- `market_impact_bps` (number): 无描述
- `market_impact_model` (string): 无描述
- `impact_reference_notional` (number): 无描述
- `impact_coefficient` (number): 无描述
- `permanent_impact_bps` (number): 无描述
- `execution_lag` (integer): 无描述
- `max_holding_days` (unknown): 无描述
- `scenarios` (unknown): 无描述
- `sample_trade_values` (array): 无描述

### MarketImpactScenarioConfig

**字段: **

- `label` (unknown): 无描述
- `market_impact_model` (string): 无描述
- `market_impact_bps` (number): 无描述
- `impact_reference_notional` (unknown): 无描述
- `impact_coefficient` (number): 无描述
- `permanent_impact_bps` (number): 无描述

### MarketRegimeRequest

**字段: **

- `symbol` (string): 无描述
- `strategy` (string): 无描述
- `parameters` (object): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述
- `fixed_commission` (number): 无描述
- `min_commission` (number): 无描述
- `market_impact_bps` (number): 无描述
- `market_impact_model` (string): 无描述
- `impact_reference_notional` (number): 无描述
- `impact_coefficient` (number): 无描述
- `permanent_impact_bps` (number): 无描述
- `execution_lag` (integer): 无描述
- `max_holding_days` (unknown): 无描述
- `lookback_days` (integer): 无描述
- `trend_threshold` (number): 无描述

### MonteCarloBacktestRequest

**字段: **

- `symbol` (string): 无描述
- `strategy` (string): 无描述
- `parameters` (object): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述
- `fixed_commission` (number): 无描述
- `min_commission` (number): 无描述
- `market_impact_bps` (number): 无描述
- `market_impact_model` (string): 无描述
- `impact_reference_notional` (number): 无描述
- `impact_coefficient` (number): 无描述
- `permanent_impact_bps` (number): 无描述
- `execution_lag` (integer): 无描述
- `max_holding_days` (unknown): 无描述
- `simulations` (integer): 无描述
- `horizon_days` (unknown): 无描述
- `seed` (unknown): 无描述

### MultiPeriodBacktestRequest

**字段: **

- `symbol` (string): 无描述
- `strategy` (string): 无描述
- `parameters` (object): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述
- `fixed_commission` (number): 无描述
- `min_commission` (number): 无描述
- `market_impact_bps` (number): 无描述
- `market_impact_model` (string): 无描述
- `impact_reference_notional` (number): 无描述
- `impact_coefficient` (number): 无描述
- `permanent_impact_bps` (number): 无描述
- `execution_lag` (integer): 无描述
- `max_holding_days` (unknown): 无描述
- `intervals` (array): 无描述

### NotificationChannelRequest

**字段: **

- `id` (string): 无描述
- `type` (string): 无描述
- `label` (string): 无描述
- `enabled` (boolean): 无描述
- `settings` (object): 无描述

### NotificationRequest

**字段: **

- `channel` (string): 无描述
- `payload` (object): 无描述

### OAuthAuthorizationRequest

**字段: **

- `frontend_origin` (string): 无描述
- `redirect_uri` (string): 无描述

### OAuthExchangeRequest

**字段: **

- `code` (string): 无描述
- `state` (string): 无描述
- `redirect_uri` (string): 无描述
- `expires_in_seconds` (integer): 无描述
- `refresh_expires_in_seconds` (integer): 无描述

### OAuthProviderRequest

**字段: **

- `provider_id` (string): 无描述
- `label` (string): 无描述
- `provider_type` (string): 无描述
- `enabled` (boolean): 无描述
- `client_id` (string): 无描述
- `client_secret` (unknown): 无描述
- `auth_url` (unknown): 无描述
- `token_url` (unknown): 无描述
- `userinfo_url` (unknown): 无描述
- `redirect_uri` (string): 无描述
- `frontend_origin` (string): 无描述
- `scopes` (array): 无描述
- `auto_create_user` (boolean): 无描述
- `default_role` (string): 无描述
- `default_scopes` (array): 无描述
- `subject_field` (string): 无描述
- `display_name_field` (string): 无描述
- `email_field` (string): 无描述
- `extra_params` (object): 无描述
- `metadata` (object): 无描述

### PersistenceBootstrapRequest

**字段: **

- `enable_timescale_schema` (boolean): 无描述

### PersistenceMigrationRequest

**字段: **

- `sqlite_path` (unknown): 无描述
- `dry_run` (boolean): 无描述
- `include_records` (boolean): 无描述
- `include_timeseries` (boolean): 无描述
- `dedupe_timeseries` (boolean): 无描述
- `record_limit` (unknown): 无描述
- `timeseries_limit` (unknown): 无描述

### PortfolioStrategyRequest

**字段: **

- `symbols` (array): 无描述
- `strategy` (string): 无描述
- `parameters` (object): 无描述
- `weights` (unknown): 无描述
- `objective` (string): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述
- `fixed_commission` (number): 无描述
- `min_commission` (number): 无描述
- `market_impact_bps` (number): 无描述
- `market_impact_model` (string): 无描述
- `impact_reference_notional` (number): 无描述
- `impact_coefficient` (number): 无描述
- `permanent_impact_bps` (number): 无描述
- `execution_lag` (integer): 无描述
- `min_trade_value` (number): 无描述
- `min_rebalance_weight_delta` (number): 无描述
- `max_turnover_per_rebalance` (unknown): 无描述

### RateLimitRuleRequest

**字段: **

- `id` (unknown): 无描述
- `pattern` (string): 无描述
- `requests_per_minute` (integer): 无描述
- `burst_size` (integer): 无描述
- `enabled` (boolean): 无描述

### RateLimitUpdateRequest

**字段: **

- `default_requests_per_minute` (integer): 无描述
- `default_burst_size` (integer): 无描述
- `rules` (array): 无描述

### RealtimeAlertHitRequest

**字段: **

- `entry` (object): 无描述
- `notify_channels` (array): 无描述
- `create_workbench_task` (boolean): 兼容旧客户端的保留字段。公开仓会忽略该值，不再创建研究工作台任务。
- `persist_event_record` (boolean): 无描述
- `severity` (string): 无描述

### RealtimeAlertsRequest

**字段: **

- `alerts` (array): 无描述
- `alert_hit_history` (array): 无描述

### RealtimeJournalRequest

**字段: **

- `review_snapshots` (array): 无描述
- `timeline_events` (array): 无描述

### RealtimePreferencesRequest

**字段: **

- `symbols` (array): 无描述
- `active_tab` (string): 无描述
- `symbol_categories` (object): 无描述
- `watch_groups` (array): 无描述

### RecordRequest

**字段: **

- `record_type` (string): 无描述
- `record_key` (string): 无描述
- `payload` (object): 无描述
- `record_id` (unknown): 无描述

### RefreshRequest

**字段: **

- `refresh_token` (string): 无描述
- `expires_in_seconds` (integer): 无描述
- `refresh_expires_in_seconds` (integer): 无描述

### ReportRequest

报告生成请求

**字段: **

- `symbol` (string): 无描述
- `strategy` (string): 无描述
- `backtest_result` (unknown): 无描述
- `parameters` (unknown): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述

### SignificanceCompareRequest

**字段: **

- `symbol` (string): 无描述
- `strategies` (unknown): 无描述
- `strategy_configs` (unknown): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述
- `fixed_commission` (number): 无描述
- `min_commission` (number): 无描述
- `market_impact_bps` (number): 无描述
- `market_impact_model` (string): 无描述
- `impact_reference_notional` (number): 无描述
- `impact_coefficient` (number): 无描述
- `permanent_impact_bps` (number): 无描述
- `execution_lag` (integer): 无描述
- `max_holding_days` (unknown): 无描述
- `baseline_strategy` (unknown): 无描述
- `bootstrap_samples` (integer): 无描述
- `seed` (unknown): 无描述

### StockResponse

股票信息响应

**字段: **

- `symbol` (string): 股票代码
- `name` (string): 股票名称
- `rank` (integer): 行业内排名
- `total_score` (number): 综合得分
- `scoreStage` (unknown): 评分阶段: quick(快速评分) 或 full(完整评分)
- `market_cap` (unknown): 市值
- `pe_ratio` (unknown): 市盈率
- `change_pct` (unknown): 涨跌幅
- `money_flow` (unknown): 主力净流入
- `turnover_rate` (unknown): 换手率
- `industry` (string): 所属行业

### StrategyInfo

**字段: **

- `name` (string): 无描述
- `description` (string): 无描述
- `parameters` (object): 无描述

### SubscriptionRequest

兼容层订阅请求。

**字段: **

- `symbol` (unknown): 无描述
- `symbols` (array): 无描述

### TaskRequest

**字段: **

- `name` (string): 无描述
- `payload` (object): 无描述
- `execution_backend` (string): 无描述

### TimeSeriesRequest

**字段: **

- `series_name` (string): 无描述
- `symbol` (string): 无描述
- `timestamp` (string): 无描述
- `value` (unknown): 无描述
- `payload` (object): 无描述

### TokenRequest

**字段: **

- `subject` (string): 无描述
- `role` (string): 无描述
- `expires_in_seconds` (integer): 无描述
- `refresh_expires_in_seconds` (integer): 无描述

### TrendAnalysisRequest

**字段: **

- `symbol` (string): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `interval` (string): 无描述

### TrendAnalysisResponse

**字段: **

- `symbol` (string): 无描述
- `trend` (string): 无描述
- `score` (number): 无描述
- `support_levels` (array): 无描述
- `resistance_levels` (array): 无描述
- `indicators` (object): 无描述
- `trend_details` (object): 无描述
- `timestamp` (string): 无描述
- `multi_timeframe` (unknown): 无描述
- `trend_strength` (unknown): 无描述
- `signal_strength` (unknown): 无描述
- `momentum` (unknown): 无描述
- `volatility` (unknown): 无描述
- `fibonacci_levels` (unknown): 无描述

### ValidationError

**字段: **

- `loc` (array): 无描述
- `msg` (string): 无描述
- `type` (string): 无描述

### WalkForwardRequest

**字段: **

- `symbol` (string): 无描述
- `strategy` (string): 无描述
- `parameters` (object): 无描述
- `parameter_grid` (unknown): 无描述
- `parameter_candidates` (unknown): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述
- `fixed_commission` (number): 无描述
- `min_commission` (number): 无描述
- `market_impact_bps` (number): 无描述
- `market_impact_model` (string): 无描述
- `impact_reference_notional` (number): 无描述
- `impact_coefficient` (number): 无描述
- `permanent_impact_bps` (number): 无描述
- `execution_lag` (integer): 无描述
- `max_holding_days` (unknown): 无描述
- `train_period` (integer): 无描述
- `test_period` (integer): 无描述
- `step_size` (integer): 无描述
- `optimization_metric` (string): 无描述
- `optimization_method` (string): 无描述
- `optimization_budget` (unknown): 无描述
- `monte_carlo_simulations` (integer): 无描述
- `timeout_seconds` (number): 无描述

## 错误代码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 422 | 请求数据验证失败 |
| 500 | 服务器内部错误 |

## 示例

### 获取策略列表

```bash
curl -X GET "http://localhost:8000/strategies" \
     -H "accept: application/json"
```

### 运行回测

```bash
curl -X POST "http://localhost:8000/backtest" \
     -H "accept: application/json" \
     -H "Content-Type: application/json" \
     -d '{
       "symbol": "AAPL",
       "strategy": "moving_average",
       "start_date": "2023-01-01",
       "end_date": "2023-12-31",
       "initial_capital": 10000,
       "parameters": {
         "short_window": 10,
         "long_window": 30
       }
     }'
```

## 文档说明

- 本文档由 `python3 scripts/generate_api_docs.py` 自动生成
- 版本与仓库边界说明以根目录 `VERSION`、`README.md` 与 `docs/CHANGELOG.md` 为准
- 兼容字段的公开行为以对应 schema 字段描述为准

## 支持

如有问题，请联系技术支持或查看项目文档。
