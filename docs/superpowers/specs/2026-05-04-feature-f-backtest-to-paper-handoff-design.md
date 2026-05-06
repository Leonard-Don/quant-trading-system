# Feature F — Backtest → Paper Trading Handoff (设计文档 · v0)

- 日期: 2026-05-04
- 范围: 把回测结果一键导入纸面账户的下单表单，连接"研究 ↔ 验证"两个工作区
- 状态: 用户已确认全权决策

## 背景

E（commit `6ed2369`）让每次主回测自动归档到研究档案；C（commit `659ae13`）让用户能手动管理纸面账户；D2（commit `116feef`）让政策信号叠加到行业热力图。

但**回测和纸面账户之间还是断开的**：研究者跑完一个有效策略，要继续验证它，得自己手动把策略的 symbol / 最后一笔交易方向 / 数量重新输入纸面账户的下单表单。这种重复输入是最容易让"研究 → 验证"链路掉队的摩擦点。

F 把这一步消除掉。

## 设计

### v0 范围

| 含 | 不含 |
|----|------|
| 在回测结果工具栏加"送到纸面账户"按钮 | 自动按当前实时行情成交（v0 仍由用户填价） |
| 把策略 symbol、最后一笔交易方向、数量预填到纸面下单表单 | 自动重跑策略推断"现在该买/卖"（需要后端 strategy supervisor） |
| 一次性传递（消费即清，不污染 URL） | 多回测结果队列管理 |
| 不展示历史快照"曾经把哪个回测送到了纸面" | trade_plan 长期持仓 / 跨设备同步 |

### 数据传递机制：sessionStorage

**为什么不用 URL 参数**：URL 参数会经过 `sanitizeParamsForView`，要追加白名单；同时分享 URL 时会带上失效的 prefill，体验不干净。sessionStorage 是 same-tab 转手专用通道，自动隔离不同 tab。

**Key**：`paper-trading-prefill`
**Payload**：
```json
{
  "symbol": "AAPL",
  "side": "BUY",
  "quantity": 10,
  "sourceLabel": "由 MovingAverageCrossover · 回测带入",
  "writtenAt": 1714836000000
}
```

**生命周期**：
- ResultsDisplay 写入
- PaperTradingPanel mount 时读取 → 调用 `orderForm.setFieldsValue` → 立即删除该 key
- 30 秒未消费的 prefill 视为过期（用 `writtenAt` 比较），新 mount 不消费

### 数据导出（"最后一笔交易"语义）

回测结果的 `trades` 数组按时间排序，每条 trade 含 `{date, type: BUY/SELL, price, quantity, value, pnl}`。

策略：取**最后一笔交易**作为推荐：
- side = lastTrade.type
- quantity = lastTrade.quantity
- symbol = normalizedResults.symbol
- fill_price 不预填——让用户在纸面端用当前行情或自定价输入；avoiding "用历史价做未来纸面交易"的误导

如果 `trades` 为空（回测无成交），则只填 symbol + 让用户在纸面手动选 side / quantity。

### 调用链

```
ResultsDisplay
  └── onSendToPaperTrading?.({symbol, side, quantity, sourceLabel})
        ↑
        └── BacktestDashboard 透传 props
              ↑
              └── App.js 实现：
                    setPaperPrefill(payload)            // 写 sessionStorage
                    setCurrentView('paper')             // 路由到纸面工作区

PaperTradingPanel
  └── useEffect on mount
        consumePaperPrefill() → orderForm.setFieldsValue
        显示一行 Tag：「来自回测」+ sourceLabel
```

### Util 模块

新增 `frontend/src/utils/paperTradingPrefill.js`：

```js
export const PAPER_TRADING_PREFILL_KEY = 'paper-trading-prefill';
export const PAPER_TRADING_PREFILL_TTL_MS = 30_000;

export const setPaperPrefill = (payload) => { ... }
export const consumePaperPrefill = () => { ... }  // 读+删；过期返回 null
```

纯 sessionStorage 读写 + 时间戳过期检查。无 React。

## 验证标准

| 编号 | 条件 |
|------|------|
| F.U | `paper-trading-prefill.test.js` 覆盖：写入 / 读取并清除 / 过期返回 null / 损坏 JSON 容错 |
| F.集 | PaperTradingPanel 单元测试新增一例：mount 前注入 sessionStorage → 表单字段被预填 |
| F.集 | ResultsDisplay 单元测试新增一例：trades 非空时，按下按钮调用 onSendToPaperTrading 并传递最后一笔交易的 side/quantity |
| F.整 | 后端套件无需变化；前端套件 +N 用例全绿 |

## 风险

- **极低**：纯前端 + sessionStorage，无后端、无新依赖、无 schema 改动
- **可观察的边角**：tab 之间不共享 sessionStorage，所以"在新 tab 打开纸面账户"不会带 prefill。这是 sessionStorage 设计行为，符合预期

## 不在范围（明确推迟）

- "把整段 trades 当成历史信号回放进 paper 账户"——需要新增"批量导入"端点
- 自动按当前 quote 成交——v0 让用户决定填价，避免 v0 把"实战可行性"假装做完
- trade_plan 持久化（journal 已有该类型，未来会用）

## 实施顺序

1. `paperTradingPrefill.js` util + 单元测试
2. PaperTradingPanel 集成 + 测试
3. ResultsDisplay 加按钮 + 测试
4. App.js + BacktestDashboard 串通调用链
5. 完整回归
