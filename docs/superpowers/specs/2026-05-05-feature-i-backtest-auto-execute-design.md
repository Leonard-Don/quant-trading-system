# Feature I — Backtest Auto-Execute to Paper (设计文档 · v0)

- 日期: 2026-05-05
- 范围: 在 ResultsDisplay 增加 "按市价直接下单到纸面" 按钮，跑完回测一键完成订单提交（不要求用户手填价格）
- 状态: 用户已确认全权决策

## F vs I

F (commit `fa0b0e1`) 已经把回测结果转化成纸面下单表单的 prefill：

```
回测结果  ──「送到纸面账户」──►  ?view=paper（表单已预填，等用户填价 + 提交）
```

但是用户仍需要手动填 fill_price 并点 "提交订单"——两个步骤。如果用户对策略有信心、想要立刻执行，这两步就是阻力。

I 加一条**并行的快速路径**：

```
回测结果  ──「按市价直接下单到纸面」──►
              ├── fetch 当前 quote
              ├── submitPaperOrder({...prefill, fill_price: quote.price})
              └── 跳到 ?view=paper（已经有持仓，可以直接看 PnL）
```

F 不动——继续是默认的"审视后下单"路径。I 是 opt-in 的"信任后下单"快捷方式。

## v0 范围

| 含 | 不含 |
|----|------|
| 单一额外按钮，并存 F 的现有按钮 | 默认替换 F（用户可能想先审视） |
| 用 last trade 的 side + quantity 自动构造订单 | 通过策略当前信号重新跑（需 strategy supervisor）|
| fill_price = 当前 realtime quote 的 price | 自定义滑点 / 限价 |
| 错误回退到 F 路径（prefill + 跳转）| 自动重试 / 复杂的失败状态 |
| Popconfirm 二次确认（避免误点）| 跳过确认 |

## 触发条件

按钮 **仅在以下条件全满足时启用**：
1. 回测结果含 symbol（buildPrefillFromBacktest 不返回 null）
2. last trade 含 side ∈ {BUY, SELL}
3. last trade 含正数 quantity

否则按钮 disabled，tooltip 解释 "需要回测产生过交易才能直接下单"。这避免了"buildPrefillFromBacktest 返回 symbol-only，submit 时缺 side/quantity 报错"的中间态。

## 实施

### `frontend/src/utils/paperTradingPrefill.js` 扩展

新增 `canAutoExecutePrefill(prefill)`：

```js
export const canAutoExecutePrefill = (prefill) =>
    Boolean(prefill && prefill.symbol && (prefill.side === 'BUY' || prefill.side === 'SELL') && prefill.quantity > 0);
```

纯函数，可单测。

### `frontend/src/components/ResultsDisplay.js`

在现有"送到纸面账户"按钮后新增 "按市价直接下单到纸面" 按钮。两按钮共享 prefill 计算（已有逻辑），但点击 handler 不同：

- F 按钮：`onSendToPaperTrading?.(normalizedResults)` （现状）
- I 按钮：`onAutoExecuteToPaperTrading?.(normalizedResults)` （新）

I 按钮在 `canAutoExecutePrefill` 不通过时 `disabled` + tooltip。

### `App.js`

新 handler `handleAutoExecuteBacktestToPaper`：

```js
async (backtestResult) => {
    const prefill = buildPrefillFromBacktest(backtestResult);
    if (!canAutoExecutePrefill(prefill)) {
        message.warning('当前回测结果缺少有效成交信息，无法直接下单');
        return;
    }
    try {
        const quote = await getRealtimeQuote(prefill.symbol);
        const price = Number(quote?.data?.price ?? quote?.price);
        if (!Number.isFinite(price) || price <= 0) {
            // Quote unavailable → fall back to manual prefill path
            message.warning('行情不可用，已切到手填模式');
            setPaperPrefill(prefill);
            setCurrentView('paper');
            return;
        }
        await submitPaperOrder({
            symbol: prefill.symbol,
            side: prefill.side,
            quantity: prefill.quantity,
            fill_price: price,
            commission: 0,
            slippage_bps: 0,
        });
        message.success(`已按市价 $${price.toFixed(2)} 下单 ${prefill.side} ${prefill.quantity} ${prefill.symbol}`);
        setCurrentView('paper');
    } catch (error) {
        // Order rejected (e.g. insufficient cash) → fall back to manual flow
        const detail = error?.response?.data?.error?.message
            || error?.message
            || '下单失败';
        message.error(`直接下单失败：${detail}（已切到手填模式）`);
        setPaperPrefill(prefill);
        setCurrentView('paper');
    }
}
```

行为关键点：
- 快路径成功 → toast 显示成交价 + 跳转到 paper
- 快路径失败（任何环节）→ 回退到 F 路径（prefill + 跳转），不消耗 prefill 流程让用户继续手填
- 不引入新业务异常类型，复用 paper_trading endpoint 已有的 422 处理

### `BacktestDashboard.js`

新增 `onAutoExecuteToPaperTrading` prop 透传。

### Popconfirm 包裹

I 按钮用 Antd Popconfirm 包裹：

```
title: "按当前市价立即下单？"
description: `将以最新行情价为 ${prefill.symbol} 下单 ${prefill.side} ${prefill.quantity} 股，订单立即成交。`
okText: "下单"
cancelText: "取消"
```

确认后才执行 handler。这是关键的 UX 防误点措施。

## 测试

### 1. paperTradingPrefill.test.js 扩展（4 用例）

- canAutoExecutePrefill: 完整 prefill → true
- canAutoExecutePrefill: 缺 side → false
- canAutoExecutePrefill: 缺 quantity → false
- canAutoExecutePrefill: null → false

### 2. backtest-auto-archive.test.js 不动

### 3. 新增 backtest-auto-execute.test.js 集成测试（3-4 用例）

- 完整 prefill + quote 可用 → submitPaperOrder 调用 + 跳转 paper
- quote 失败 → fallback 到 prefill 路径（setPaperPrefill 调用 + 跳转）
- order 失败 → fallback 到 prefill 路径

### 4. 探针不扩

`verify_new_features.js` 已覆盖 F 路径。I 走的是同样的路由 + sessionStorage / 直接订单 endpoint，两者都已经被覆盖；I 特有的 "auto-execute" 流程是 jest 集成测试的领域，浏览器 smoke 不增量。

## 不在范围（明确推迟）

- 用户自定义"市价下单时叠加 N bps 滑点"
- 与 G 路径的 auto-execute 集成（journal entry 一键直接下单）—— G 走稳健路径就够，不需要也加 I
- 后端"/paper/auto-execute" 复合端点（前端编排足够）
- 跳转后高亮新成交订单（非阻塞）

## 验证标准

| 编号 | 条件 |
|------|------|
| I.U | paperTradingPrefill 新增 4 用例全绿 |
| I.集 | backtest-auto-execute 新增 3-4 用例全绿 |
| I.整 | 完整前端 jest 全绿；后端不动 |
| 手验 | 跑回测 → 点 I 按钮 → 弹 Popconfirm → 确认 → 跳到 paper 工作区，看到新订单和持仓 |

## 风险

- **中等**：自动下单是真实订单（虽然纸面账户内），Popconfirm 是必要的防线
- 错误回退路径有多种触发点（quote 失败 / order 422 / 网络错误），统一回退到 F 路径让用户体验始终是"先有 prefill，再选择"
