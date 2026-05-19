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

## Execution Timing

- 单资产回测默认使用 `execution_lag = 1`，即策略在第 N 根 bar 生成的信号最早在第 N+1 根 bar 执行。
- `execution_diagnostics.execution_lag` 必须回传真实执行延迟。
- 仅在复现实验或兼容旧结果时将 `execution_lag` 显式设为 `0`。

## Formal statistical tests: when to use which

`src/backtest/strategy_statistical_tests.py` ships three orthogonal
hypothesis tests. They answer **different** questions; pick by the claim
you need to defend, not by significance shopping:

- **Diebold-Mariano** (`diebold_mariano_test`) — use when the claim is
  "strategy A has a *different expected return* (or any other loss
  metric) than strategy B". Newey-West HAC handles the autocorrelation
  in trading P&L. Default `loss_fn="negative_return"` for return
  comparisons; `loss_fn="squared_error"` if the claim is about
  *volatility* about zero (rare); `loss_fn="sharpe"` for a pooled-
  variance Sharpe-contribution version. Asymptotic — needs `n >= 30`
  for clean inference; small samples fall back to a t-distribution.
- **Memmel Sharpe-ratio test** (`sharpe_ratio_test`) — use when the
  claim is specifically about *Sharpe ratios* (e.g. "blend wins on
  risk-adjusted return"). Closed-form, asymptotic z-test on
  `Sharpe_a - Sharpe_b`. Cheaper than bootstrap; appropriate for
  pairwise grids of dozens of strategies. Less flexible than DM
  (Sharpe-only), more direct than computing Sharpe inside a bootstrap.
- **Politis-Romano block bootstrap** (`politis_romano_block_bootstrap`)
  — use when (a) the sample is small (`n < 50`), (b) the loss
  distribution is heavy-tailed or otherwise non-normal, or (c) you want
  a *confidence interval* on the return differential, not just a
  p-value. Block size `~ n^(1/3)` is the standard rule of thumb. Costs
  `O(n * n_bootstrap)` so reserve for headline pairs; DM / Memmel scale
  to wide grids for free.

**Multiple-testing**: any pairwise comparator that tests `k` pairs
inflates the family-wise error rate by ~`k`x. `bonferroni_correct(...)`
is conservative (every p-value compares to `α/k`); `holm_correct(...)`
is uniformly more powerful (sorted step-down). Use Holm by default;
prefer Bonferroni when the rejections need to be defensible to a
hostile reviewer.

When in doubt, **run all three** — they answer the same null from
different angles. If the conclusions agree (e.g. all three reject, or
all three fail to reject), the claim is robust; if they disagree (e.g.
DM rejects but Memmel doesn't), inspect the loss function, sample size,
and autocorrelation regime before going to print.

See `docs/sample_strategy_comparison.md` for a worked example on real
ETF data (the 2026-Q2 refresh).
