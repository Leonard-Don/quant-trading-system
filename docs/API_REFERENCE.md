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
    - **当前版本**: v4.0.0
    - **API版本**: v1
    - **最后更新**: 2026-04-14

    ### 认证
    当前版本无需认证，生产环境建议添加API密钥认证。

    ### 限制
    - 请求频率: 100次/分钟
    - 数据范围: 最多5年历史数据
    - 并发回测: 最多10个
    

**版本**: 4.0.0

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

### AlertEventPublishRequest

**字段: **

- `source_module` (string): 无描述
- `rule_name` (string): 无描述
- `symbol` (string): 无描述
- `severity` (string): 无描述
- `message` (string): 无描述
- `condition_summary` (string): 无描述
- `condition` (unknown): 无描述
- `trigger_value` (unknown): 无描述
- `threshold` (unknown): 无描述
- `rule_ids` (array): 无描述
- `notify_channels` (array): 无描述
- `create_workbench_task` (boolean): 无描述
- `workbench_task_type` (string): 无描述
- `workbench_status` (string): 无描述
- `persist_event_record` (boolean): 无描述
- `cascade_actions` (array): 无描述

### AlertOrchestrationUpdateRequest

**字段: **

- `composite_rules` (array): 无描述
- `channels` (array): 无描述
- `module_alerts` (array): 无描述
- `history_entry` (unknown): 无描述
- `history_updates` (array): 无描述

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

### FactorExpressionRequest

**字段: **

- `symbol` (string): 无描述
- `expression` (string): 无描述
- `period` (string): 无描述
- `preview_rows` (integer): 无描述

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

### IndustryRotationLabRequest

**字段: **

- `start_date` (string): 无描述
- `end_date` (string): 无描述
- `rebalance_freq` (string): 无描述
- `top_industries` (integer): 无描述
- `stocks_per_industry` (integer): 无描述
- `weight_method` (string): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述

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
- `min_trade_value` (number): 无描述
- `min_rebalance_weight_delta` (number): 无描述
- `max_turnover_per_rebalance` (unknown): 无描述

### PricingRequest

**字段: **

- `symbol` (string): 股票代码，如 AAPL
- `period` (string): 分析周期: 6mo, 1y, 2y, 3y, 5y

### PricingScreenerRequest

**字段: **

- `symbols` (array): 候选股票代码列表
- `period` (string): 分析周期: 6mo, 1y, 2y, 3y, 5y
- `limit` (integer): 返回前 N 个结果
- `max_workers` (integer): 并行执行数

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
- `create_workbench_task` (boolean): 无描述
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

### ResearchTaskBulkUpdateRequest

**字段: **

- `task_ids` (array): 无描述
- `status` (unknown): 无描述
- `comment` (string): 无描述
- `author` (string): 无描述

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
- `refresh_priority_event` (unknown): 无描述

### ResearchTaskRefreshPriorityEvent

**字段: **

- `reason_key` (string): 无描述
- `reason_label` (string): 无描述
- `severity` (string): 无描述
- `lead` (string): 无描述
- `detail` (string): 无描述
- `urgency_score` (unknown): 无描述
- `priority_weight` (unknown): 无描述
- `recommendation` (string): 无描述
- `summary` (string): 无描述

### ResearchTaskReorderItem

**字段: **

- `task_id` (string): 无描述
- `status` (string): 无描述
- `board_order` (integer): 无描述
- `refresh_priority_event` (unknown): 无描述

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
- `refresh_priority_event` (unknown): 无描述

### ResearchTaskUpdateRequest

**字段: **

- `status` (unknown): 无描述
- `title` (unknown): 无描述
- `note` (unknown): 无描述
- `board_order` (unknown): 无描述
- `context` (unknown): 无描述
- `snapshot` (unknown): 无描述
- `refresh_priority_event` (unknown): 无描述

### ResearchWorkbenchReorderRequest

**字段: **

- `items` (array): 无描述

### RiskCenterRequest

**字段: **

- `symbols` (array): 无描述
- `weights` (unknown): 无描述
- `period` (string): 无描述

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

### StrategyOptimizationRequest

**字段: **

- `symbol` (string): 无描述
- `strategy` (string): 无描述
- `parameters` (object): 无描述
- `parameter_grid` (unknown): 无描述
- `start_date` (unknown): 无描述
- `end_date` (unknown): 无描述
- `initial_capital` (number): 无描述
- `commission` (number): 无描述
- `slippage` (number): 无描述
- `density` (integer): 无描述
- `optimization_metric` (string): 无描述
- `optimization_method` (string): 无描述
- `optimization_budget` (unknown): 无描述
- `run_walk_forward` (boolean): 无描述
- `train_period` (integer): 无描述
- `test_period` (integer): 无描述
- `step_size` (integer): 无描述
- `monte_carlo_simulations` (integer): 无描述

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

### TradeRequest

**字段: **

- `symbol` (string): 无描述
- `action` (string): 无描述
- `quantity` (integer): 无描述
- `price` (unknown): 无描述

### TradingJournalUpdateRequest

**字段: **

- `notes` (object): 无描述
- `strategy_lifecycle` (array): 无描述

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

### ValuationLabRequest

**字段: **

- `symbol` (string): 无描述
- `period` (string): 无描述
- `peer_symbols` (array): 无描述
- `peer_limit` (integer): 无描述

### ValuationRequest

**字段: **

- `symbol` (string): 股票代码

### ValuationSensitivityRequest

**字段: **

- `symbol` (string): 股票代码
- `wacc` (unknown): 覆盖 WACC
- `initial_growth` (unknown): 覆盖初始增长率
- `terminal_growth` (unknown): 覆盖终值增长率
- `fcf_margin` (unknown): 覆盖现金流转化率
- `dcf_weight` (unknown): 覆盖 DCF 权重
- `comparable_weight` (unknown): 覆盖可比估值权重

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

## 更新日志

- **v3.1.0** (2025-09-09): 添加性能监控、缓存管理、结构化日志
- **v3.0.0** (2024-12-01): 初始版本，支持8种交易策略

## 支持

如有问题，请联系技术支持或查看项目文档。
