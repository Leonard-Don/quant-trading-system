# Feature G — Journal Entry → Paper Trading Handoff (设计文档)

- 日期: 2026-05-04
- 范围: 把"送到纸面账户"快捷入口从单一的 backtest 结果面板扩展到任何 today research 档案里 type=backtest 的条目
- 状态: 用户已确认全权决策

## 背景

F 把 `BacktestDashboard` 的实时回测结果接到 paper trading：跑完回测 → 点按钮 → 自动预填下单表单。但**对历史回测档案没有等价路径**——用户在 today research 档案里看到一条 1 周前归档的回测记录，要继续验证它，必须重新跑一次回测才能用 F 的入口。

G 把这个对偶补全：每条 type=backtest 的档案条目都带一个 "送到纸面账户" 按钮，行为和 F 完全一致。

## 数据可用性

E 的 auto-archive 当前在 `raw` 字段持久化的内容：

```js
raw: {
    strategy: strategyName,
    parameters: { ... },
    period: { start, end },
    initial_capital,
    commission,
    slippage,
}
```

**没有 last_trade 信息**——F 用最后一笔交易的 side/quantity 预填，但 journal 不存这块。

### 决策：扩展 raw 包含 last_trade，而不是仅 symbol-only fallback

替代方案对比：

| 方案 | 优 | 缺 |
|------|------|------|
| **A. 扩 raw 加 last_trade** | G 与 F 表现一致（symbol + side + quantity 全预填） | 写入路径多两个字段；旧档案的条目仍只有 symbol |
| B. G 仅预填 symbol | 不动数据 schema；旧条目和新条目表现一致 | 用户体验比 F 弱；交互上"还得自己想 side / quantity" |

选 A：用户感知一致是关键，旧条目缺 last_trade 自动 fallback 到"只填 symbol"，没有破坏，是渐进增强。

### 数据加固

`buildBacktestJournalEntry` 增加：

```js
const lastTrade = trades.length > 0 ? trades[trades.length - 1] : null;
raw: {
    ...,
    last_trade: lastTrade
        ? {
            side: lastTrade.type,
            quantity: lastTrade.quantity,
            price: lastTrade.price,
            date: lastTrade.date,
        }
        : null,
}
```

## 设计

### 新增 `buildPrefillFromJournalEntry` (utils/paperTradingPrefill.js)

```js
export const buildPrefillFromJournalEntry = (entry) => {
    if (!entry || entry.type !== 'backtest') return null;
    const symbol = String(entry.symbol || '').toUpperCase();
    if (!symbol) return null;

    const raw = entry.raw || {};
    const lastTrade = raw.last_trade || null;
    const side = lastTrade?.side === 'BUY' || lastTrade?.side === 'SELL' ? lastTrade.side : null;
    const qty = typeof lastTrade?.quantity === 'number' && Number.isFinite(lastTrade.quantity) && lastTrade.quantity > 0
        ? lastTrade.quantity
        : null;
    const strategyName = raw.strategy || '';
    return {
        symbol,
        side,
        quantity: qty,
        sourceLabel: strategyName ? `由 ${strategyName} · 档案带入` : '由档案带入',
    };
};
```

注意 sourceLabel 用"档案带入"而不是 F 的"回测带入"，让用户在 paper 工作区一眼能区分入口来源。

### TodayResearchDashboard 集成

在 `renderEntry` 的 actions Space 中，对 type=backtest 的条目额外加一个按钮：

```jsx
{entry.type === 'backtest' && entry.symbol ? (
    <Button
        size="small"
        icon={<ThunderboltOutlined />}
        onClick={() => handleSendEntryToPaper(entry)}
        data-testid="today-entry-send-to-paper"
    >
        送到纸面账户
    </Button>
) : null}
```

`handleSendEntryToPaper` 复用 paperTradingPrefill 的 setPaperPrefill + 现有 navigateToAppUrl(buildAppUrl({ view: 'paper' }))。

## 测试

### 1. paperTradingPrefill.test.js (扩展)

新增 `buildPrefillFromJournalEntry` 6 个用例：
- 完整 entry（含 last_trade）→ symbol/side/quantity 都预填
- 只有 symbol（无 last_trade）→ 只预填 symbol，side/quantity 为 null
- 非 backtest 类型 → 返回 null
- 缺 symbol → 返回 null
- last_trade.side 不合法 → side 为 null（其他保留）
- raw 缺失 → 不崩，按 symbol-only

### 2. backtest-journal-entry.test.js (扩展)

加 1 用例：构造时如果 result.trades 非空，raw.last_trade 被填入；为空则 raw.last_trade 为 null。

### 3. today-research.test.js（如果存在）vs 新增 today-research-send-to-paper.test.js

新增专用测试文件，因为已有 today-research.test.js 是端到端 RTL，专用文件更易聚焦：
- entry type=backtest 渲染时按钮可见
- entry type=manual 渲染时按钮不可见
- entry type=backtest 但 symbol 为空时按钮不可见
- 点击按钮 → setPaperPrefill 被调用 + navigate 到 paper

### 4. verify_new_features.js 扩探针

走：访问 ?view=today → mock 一条 backtest entry → 点按钮 → 确认到了 ?view=paper 且 prefill tag 出现。但这要求"先有一条 backtest entry"，今日研究档案在测试环境可能为空。

简化：探针只验证按钮存在与不存在的条件渲染，不做端到端跳转。或者直接靠 jest 测试覆盖跳转逻辑——浏览器探针的价值是路由层，今日 → 纸面同样过路由层，已被 F 的探针覆盖。

**取舍**：不在 verify_new_features.js 加 G 的探针，jest 测试足够。

## 不在范围

- 不让其他类型的条目（manual / industry_watch / realtime_alert）走"送到纸面"——此入口语义专门是"基于回测信号下单"
- 不在 paper trading 工作区显示反向"来源回看"链接
- 不持久化 trade_plan 类型——继续走 sessionStorage 一次性传递

## 验证标准

| 编号 | 条件 |
|------|------|
| G.U1 | paperTradingPrefill 新增 6 用例全绿 |
| G.U2 | backtest-journal-entry 1 个 last_trade 用例绿 |
| G.U3 | TodayResearchDashboard send-to-paper jest 测试 4 用例全绿 |
| G.整 | 完整 frontend jest（43+ suites）全绿；后端不动；现有 E2E 不破 |

## 实施顺序

1. 扩展 buildBacktestJournalEntry → 加 last_trade
2. 扩展 paperTradingPrefill → 加 buildPrefillFromJournalEntry
3. 扩展 TodayResearchDashboard → 加按钮 + handler
4. 单元测试 + 集成测试
5. 完整回归
