# API参考文档

## 概述


    ## 专业的量化交易策略回测系统

    ### 功能特性
    - 🚀 **8种交易策略**: 移动均线、RSI、布林带、MACD、均值回归、VWAP、动量策略、买入持有
    - 📊 **专业回测引擎**: 支持手续费、滑点、多种性能指标计算
    - 📈 **实时数据**: 集成yfinance，支持多种数据源
    - 🔍 **高级分析**: 夏普比率、最大回撤、VaR、CVaR等专业指标
    - ⚡ **高性能**: 异步处理、智能缓存、性能监控
    - 🔌 **WebSocket支持**: 实时股票报价推送

    ### API版本
    - **当前版本**: v3.6.0
    - **API版本**: v1
    - **最后更新**: 2026-03-20

    ### 认证
    当前版本无需认证，生产环境建议添加API密钥认证。

    ### 限制
    - 请求频率: 100次/分钟
    - 数据范围: 最多5年历史数据
    - 并发回测: 最多10个
    

**版本**: 3.6.0

## 基础信息

- **基础URL**: `http://localhost:8000`
- **认证方式**: 无需认证（开发环境）
- **数据格式**: JSON
- **字符编码**: UTF-8

## API端点

## 实时行情说明

- **正式实时订阅入口**: `WS /ws/quotes`
- **兼容层接口**: `POST /realtime/subscribe` 与 `POST /realtime/unsubscribe`
- **兼容层说明**: 仅用于兼容旧客户端，返回订阅确认，不维护持久订阅态
- **报价字段**: `symbol, price, change, change_percent, volume, high, low, open, previous_close, bid, ask, timestamp, source`

## 数据模型

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

### BatchBacktestTaskRequest

**字段: **

- `task_id` (unknown): 无描述
- `symbol` (string): 无描述
- `strategy` (string): 无描述
- `parameters` (object): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述

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

### CompareStrategyConfig

**字段: **

- `name` (string): 无描述
- `parameters` (object): 无描述

### CorrelationRequest

**字段: **

- `symbols` (array): 无描述
- `period_days` (integer): 无描述

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
- `bias_strength` (unknown): 无描述
- `bias_highlights` (array): 无描述
- `bias_actions` (array): 无描述
- `signal_attribution` (array): 无描述
- `base_assets` (array): 无描述

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
- `size` (number): 市值/成交额
- `stockCount` (integer): 成分股数量
- `moneyFlow` (number): 资金流向
- `turnoverRate` (number): 换手率
- `industryVolatility` (number): 行业区间波动率(%)
- `industryVolatilitySource` (string): 行业波动率来源: historical_index/stock_dispersion/amplitude_proxy/turnover_rate_proxy/change_proxy/unavailable
- `netInflowRatio` (number): 主力净流入占比
- `leadingStock` (unknown): 领涨股
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

### HeatmapResponse

热力图响应

**字段: **

- `industries` (array): 行业数据
- `max_value` (number): 最大值
- `min_value` (number): 最小值
- `update_time` (string): 更新时间

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

### IndustryRotationResponse

行业轮动对比响应

**字段: **

- `industries` (array): 对比行业列表
- `periods` (array): 统计周期
- `data` (array): 轮动数据
- `update_time` (string): 更新时间

### IndustryTrendResponse

行业趋势响应

**字段: **

- `industry_name` (string): 行业名称
- `stock_count` (integer): 成分股数量
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
- `degraded` (boolean): 是否为降级数据
- `note` (unknown): 降级或补充说明
- `update_time` (string): 更新时间

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

### MarketDataRequest

**字段: **

- `symbol` (string): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `interval` (string): 无描述
- `period` (unknown): 无描述

### PricingRequest

**字段: **

- `symbol` (string): 股票代码，如 AAPL
- `period` (string): 分析周期: 6mo, 1y, 2y, 3y, 5y

### RealtimePreferencesRequest

**字段: **

- `symbols` (array): 无描述
- `active_tab` (string): 无描述

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

### ResearchTaskCommentCreateRequest

**字段: **

- `author` (string): 无描述
- `body` (string): 无描述

### ResearchTaskCreateRequest

**字段: **

- `type` (string): 无描述
- `title` (string): 无描述
- `status` (string): 无描述
- `source` (string): 无描述
- `symbol` (string): 无描述
- `template` (string): 无描述
- `note` (string): 无描述
- `board_order` (unknown): 无描述
- `context` (object): 无描述
- `snapshot` (unknown): 无描述

### ResearchTaskReorderItem

**字段: **

- `task_id` (string): 无描述
- `status` (string): 无描述
- `board_order` (integer): 无描述

### ResearchTaskSnapshot

**字段: **

- `headline` (string): 无描述
- `summary` (string): 无描述
- `highlights` (array): 无描述
- `payload` (object): 无描述
- `saved_at` (string): 无描述

### ResearchTaskSnapshotCreateRequest

**字段: **

- `snapshot` (unknown): 无描述

### ResearchTaskUpdateRequest

**字段: **

- `status` (unknown): 无描述
- `title` (unknown): 无描述
- `note` (unknown): 无描述
- `board_order` (unknown): 无描述
- `context` (unknown): 无描述
- `snapshot` (unknown): 无描述

### ResearchWorkbenchReorderRequest

**字段: **

- `items` (array): 无描述

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

### TradeRequest

**字段: **

- `symbol` (string): 无描述
- `action` (string): 无描述
- `quantity` (integer): 无描述
- `price` (unknown): 无描述

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

### ValuationRequest

**字段: **

- `symbol` (string): 股票代码

### WalkForwardRequest

**字段: **

- `symbol` (string): 无描述
- `strategy` (string): 无描述
- `parameters` (object): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述
- `train_period` (integer): 无描述
- `test_period` (integer): 无描述
- `step_size` (integer): 无描述

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

## 更新日志

- **v3.1.0** (2025-09-09): 添加性能监控、缓存管理、结构化日志
- **v3.0.0** (2024-12-01): 初始版本，支持8种交易策略

## 支持

如有问题，请联系技术支持或查看项目文档。
