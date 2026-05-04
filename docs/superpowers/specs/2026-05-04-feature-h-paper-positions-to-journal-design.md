# Feature H — Paper Positions → Research Journal (设计文档 · v0)

- 日期: 2026-05-04
- 范围: 把当前 paper trading 持仓快照回写到统一研究档案，让"验证 → 研究"反向链路接通
- 状态: 用户已确认全权决策

## 当前状态

经过 E/F/G，研究→验证一侧已经形成闭环：

| 入口 | 路径 |
|------|------|
| 跑完回测立刻动手 | F: ResultsDisplay "送到纸面账户" |
| 历史回测档案回看后动手 | G: TodayResearchDashboard 上的 "送到纸面账户" |
| 自动留痕 | E: handleBacktest 写 journal entry |

**反向链路缺失**：用户在 paper 账户里持仓中，要回到 today research 看自己整体研究状态时，看不到"我现在还持有什么"。今日研究档案里只有 backtest / industry / realtime 三类，缺 paper。

## v0 设计

### 范围

| 含 | 不含 |
|----|------|
| 当前持仓一键归档到档案（type=trade_plan）| 自动周期性同步（cron） |
| 每个 symbol 一条 entry，stable id 自动去重 | 历史已平仓持仓的归档 |
| 携带均价 / 数量 / 现价（若 frontend 有）/ 盈亏 | 现金、订单流水的归档 |
| 复用现有 createResearchJournalEntry 端点 | 新增后端端点 |

### 用户路径

PaperTradingPanel 顶部 chip 条加一个按钮 "归档持仓到档案"：

- 持仓为空时禁用，tooltip 提示 "暂无持仓可归档"
- 点击后对每条 position 调用 `createResearchJournalEntry`
- 成功后用 message 弹 "已归档 N 条持仓到今日研究档案"

### Entry 形状

```js
{
    id: `paper-position:${symbol}`,    // 稳定 id → 同一标的下次归档自动覆盖
    type: 'trade_plan',
    status: 'open',
    priority: 'medium',
    title: `${symbol} 纸面持仓 ${quantity} 股`,
    summary: `均价 $${avg_cost}，当前 $${last_price}，浮动 ${pnl}`,  // last_price/pnl 没有时回退到只显示均价
    symbol,
    source: 'paper_trading',
    source_label: '纸面账户',
    metrics: {
        quantity,
        avg_cost,
        last_price,         // null 当 quote 未拿到
        market_value,       // last_price * quantity 当可计算
        unrealized_pnl,     // (last_price - avg_cost) * quantity 当可计算
    },
    raw: {
        opened_at,
        updated_at,
    },
    tags: ['paper', symbol],
}
```

`title` / `summary` 的具体字符串保持精简，因为 today dashboard 的 entry 是"扫一眼即懂"的卡片，不放过多数字。

### Stable id 行为

`research_journal_store._normalize_entries` 按 id 去重，新 entry 的 `updated_at` 更新时直接覆盖旧的。所以：

- 第一次归档 AAPL 持仓 → 创建 `paper-position:AAPL`
- 后续 BUY 加仓后再次归档 → 同 id，`updated_at` 更新，覆盖旧条目
- 平仓后再次归档 → AAPL 不在 `summary.positions` 里，不会发请求；老的 `paper-position:AAPL` 自然留在档案里直到用户手动 mark-done

### 已平仓的处理

v0 不主动清理已平仓的 entry——用户保留 vs 删除的判断由用户自己做（mark done 或 archived），与现有 manual entry 一致。如果发现这是个槽点，再考虑后端"软删除"逻辑。

## 实现

### `frontend/src/utils/paperPositionJournal.js`

纯函数：

```js
export const buildPaperPositionEntry = (position, options = {}) => {
    if (!position || !position.symbol) return null;
    // ... shape per spec
};
```

输入 position（含可选 last_price），返回 entry。无副作用。

### `PaperTradingPanel.js`

- import `buildPaperPositionEntry` + `createResearchJournalEntry`
- 顶部 chip 条加按钮 "归档到档案"，绑定 `handleSnapshotPositions`
- `handleSnapshotPositions` 遍历 `summary.positions`（已经包含 mark-to-market 字段），逐条 POST，promise.all 等全部完成后 message.success

### TodayResearchDashboard

不需要改：trade_plan 类型已在现有 TYPE_ICON / TYPE_COLOR / TYPE_LABELS 里支持，会自然渲染。

## 测试

1. **`paper-position-journal.test.js`** — buildPaperPositionEntry 4 用例
   - 完整 position（带 quote）→ summary 含均价/现价/PnL
   - 缺 last_price → summary 只显示均价
   - quantity 非有限 → 返回 null
   - 输入为 null/undefined → 返回 null

2. **`paper-trading-panel.test.js` 扩展** — 1 个新用例
   - mock createResearchJournalEntry，点 "归档到档案" → API 被 N 次调用（每持仓一次）
   - 持仓为空时按钮 disabled

3. **`verify_new_features.js` 不动** — 路由层未变；jest 已覆盖。

## 不在范围

- 自动周期同步（websocket / cron）
- 后端 endpoint
- entry diff（"仓位变化" 提示）
- 把现金状态写进 trade_plan
- 已平仓 paper 持仓的回填
- 在 today dashboard 给 trade_plan entry 加专用动作（如反向"打开纸面账户"）—— 现有"打开"按钮已能跳到默认 view

## 验证标准

| 编号 | 条件 |
|------|------|
| H.U | paper-position-journal jest 4 用例全绿 |
| H.集 | paper-trading-panel jest 新增 1 用例绿 |
| H.整 | 完整前端 jest 全绿；后端不动；CI 流水线无影响 |
| 手验 | 启动后开纸面账户，BUY AAPL 5 股，点"归档到档案"，切到今日研究 → 看到 type=trade_plan 的 AAPL 条目 |

## 实施顺序

1. paperPositionJournal util + 单测
2. PaperTradingPanel 顶部按钮 + 集成测
3. 完整回归
