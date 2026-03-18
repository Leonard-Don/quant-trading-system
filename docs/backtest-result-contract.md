# Backtest Result Contract

策略回测相关入口统一遵循同一份结果契约，避免主回测、历史、报告和前端页面各自猜字段。

## Core Shape

- 顶层字段始终是第一真值来源，例如：
  - `total_return`
  - `annualized_return`
  - `sharpe_ratio`
  - `max_drawdown`
  - `num_trades`
  - `final_value`
- `metrics` 必须是顶层核心指标的镜像。
- `performance_metrics` 保留为兼容别名，内容与 `metrics` 对齐。

## Trade Records

每条交易记录应兼容以下别名：

- `type` 和 `action`
  - `BUY` <-> `buy`
  - `SELL` <-> `sell`
- `shares` 和 `quantity`
- `cost | revenue` 和 `value`

前端和报告层应优先消费规范化后的：

- `type`
- `action`
- `quantity`
- `value`

## Portfolio History

- 时序数据优先使用 `portfolio_history`
- 兼容别名 `portfolio`
- 每条记录至少应可解析出：
  - `date`
  - `total`
  - `returns`
  - `signal`
- 若有价格序列，可附带 `price`

## Consistency Rules

- `num_trades` 表示成交事件数，不是 round-trip 数。
- `total_trades` 是 `num_trades` 的兼容别名。
- `metrics` 不是第二套独立真值，必须和顶层关键指标保持一致。
- 报告补跑、策略对比和主回测必须走同一条回测执行管线。
