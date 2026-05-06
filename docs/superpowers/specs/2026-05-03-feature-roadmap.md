# Feature Roadmap — 5 候选特性的现状审计与实施 spec

- 日期: 2026-05-03
- 触发: 用户在 5 个候选新功能上回复 "全部做"
- 状态: 实测发现两个已经完成，本文记录所有 5 个的真实状态与可执行 spec

## 调查结果：被误识别的"新功能"

### A. Walk-Forward + 参数搜索 UI — ✅ **早已实现**

不是新功能。已经在 `frontend/src/components/AdvancedBacktestLab.js` 里完整呈现：

- `WalkForwardSection.js` — 分析表单 + 结果可视化
- `BatchBacktestSection.js` — 批量参数扫描
- `BenchmarkSection.js` — 基准对比
- `PortfolioSection.js` — 组合曝险
- `ResearchInsightsSection.js` — 研究洞察自动总结
- `TemplateManagerSection.js` — 模板复用

后端引擎：`src/backtest/batch_backtester.py` 含 `BatchBacktester / WalkForwardAnalyzer / BayesianParameterOptimizer`，`backend/app/api/v1/endpoints/backtest.py` 暴露 `/batch`、`/walk-forward`、`/market-regimes`、`/portfolio-strategy` 端点。

入口：回测工作区 → "高级实验" tab（`?tab=advanced`）。

**问题不在于功能缺失，而在于 README / 介绍文档没有充分曝光这一块**。本期会调整 README 在"核心能力"段落中给"高级实验"独立提示。

### B. 多策略组合 / Portfolio 实验台 — ✅ **早已实现**

不是新功能。同样在 `AdvancedBacktestLab` 里：

- `frontend/src/components/PortfolioSection.js`
- `frontend/src/components/PortfolioOptimizer.js` (回测主面板的 `?tab=portfolio` 入口)
- 后端 `src/backtest/portfolio_backtester.py` + `src/analytics/portfolio_optimizer.py`

入口：回测工作区 → "优化" tab 或 "高级实验" → Portfolio section。

同 A，问题在曝光，不在实现。

### C. Paper Trading（纸面实盘模拟器）— ❌ **真的缺失**

完全没有实现的痕迹：`grep -rn "paper_trading|paperTrading|simulator" frontend/src` 返回 0；后端只有历史回测引擎，无"实时撮合"模拟层。

### D. 行业事件归因 (policy_radar UI) — ⚠️ **后端有，前端无**

`src/data/alternative/policy_radar/` 含完整管道（policy_crawler / policy_nlp / policy_signals / policy_execution，~1500 行），实现 `PolicySignalProvider(BaseAltDataProvider)`。但：

- `backend/app/api/v1/endpoints/` 中无 policy_radar 端点
- `frontend/src/services/api.js` 中无 policy 相关调用
- `frontend/src/components/` 中无 policy 视图

属于"装备齐全但商店没开门"。

### E. 实验追踪（auto-archive backtest → research_journal）— ⚠️ **基建在，最后一公里没接**

`backend/app/services/research_journal.py` 已有 `research_journal_store.add_entry(entry, profile_id)` 方法，端点 `POST /research-journal/entries` 已暴露，前端 `api.js` 已封装 `createResearchJournalEntry`。但：

- 该 API **只被 `TodayResearchDashboard` 用作"用户手动添加"**
- 主回测面板（`App.js#handleBacktest`）跑完后 **不会自动写入** journal
- 用户看到结果后必须手工去今日研究页加一条记录，体验断层

## 本期实施 spec：E. Backtest Auto-Archive

### 设计

在 `frontend/src/App.js` 的 `handleBacktest` 内，**在 `setResults` 之后**调用 `createResearchJournalEntry(...)` 异步追加一条 `type=backtest` 的 journal 记录。

**为什么前端 hook 而非后端 hook**：

1. 后端 `/backtest` 端点会被多种 caller 触达（前端单次 / `/batch` 子调用 / 集成测试），后端自动追加会产生噪声。
2. 前端 hook 只在 _用户主动跑了一次单回测_ 时触发，语义最准确。
3. 零后端改动 = 零回归风险。

### Entry 形状（与 journal store `_normalize_entry` 对齐）

```js
{
  type: 'backtest',
  status: 'open',
  priority: 'medium',
  title: `${formData.strategy_name} · ${formData.symbol}`,
  summary: `期间 ${formData.start_date} ~ ${formData.end_date}；初始资金 ${formData.initial_capital}`,
  symbol: formData.symbol,
  source: 'backtest_auto',
  source_label: '自动归档',
  metrics: {
    total_return: result.data.total_return,
    sharpe_ratio: result.data.sharpe_ratio,
    max_drawdown: result.data.max_drawdown,
    num_trades: result.data.num_trades,
  },
  raw: {
    strategy: formData.strategy_name,
    parameters: formData.strategy_params || {},
    period: { start: formData.start_date, end: formData.end_date },
  },
  tags: ['auto', formData.strategy_name].filter(Boolean),
}
```

### 失败容忍

journal 写入失败时：

- **不要影响主流程**——回测结果已展示，归档只是锦上添花
- 用 `try/catch` 包住，console.error 但不弹 message
- 可选：成功时不显式提示（避免双 toast），仅在 `?debug=1` 时打 debug log

### 验证标准

- 跑一次主回测 → `GET /research-journal/snapshot` 看到一条 `type=backtest` 记录
- 跑回测但 journal 端点返回 500 → 主回测仍正常显示结果（容错）
- frontend Jest 测试：mock `createResearchJournalEntry`，跑 `handleBacktest` 路径，断言被调用

### 实施步骤

1. `frontend/src/App.js`：import `createResearchJournalEntry`；在 `handleBacktest` 成功分支后追加异步归档块
2. 不动 `App.js` 的现有错误处理（保持原行为）
3. 新增 `frontend/src/__tests__/backtest-auto-archive.test.js`：mock api，断言归档调用与失败容忍
4. 更新 `README.md` "核心能力" 段：让"高级实验" 与 "回测自动归档" 都有 1 行可见提示

## 推迟：C 与 D 的独立 spec（仅大纲）

### C. Paper Trading（独立批次）

- 复用 `src/backtest/execution_engine.py` 的撮合逻辑作为基底
- 引入"持仓状态机"持久化（SQLite/Redis）
- 订阅 realtime WebSocket 行情驱动撮合
- 新工作区 `?view=paper` 展示持仓 / PnL / 历史成交
- 估时 3–4 周，需要单独 brainstorm。

### D. Policy Radar UI（独立批次）

- 后端：在 `backend/app/api/v1/endpoints/` 新增 `policy_radar.py`，暴露 `GET /policy-radar/signals`、`GET /policy-radar/timeline?industry=`
- 前端：在"行业热度"工作区加一个时间轴组件，把 `PolicySignalProvider` 的输出按行业 / 时间窗对齐显示
- 估时 1–2 周，需要单独 brainstorm。

## 不在范围内

- 不重写 `AdvancedBacktestLab` —— 它已经做得不错
- 不引入 Optuna 等新依赖（A/B 已用自家 BayesianParameterOptimizer）
- 不改 `research_journal_store` 的 schema
- 不动后端 `/backtest` 端点行为
