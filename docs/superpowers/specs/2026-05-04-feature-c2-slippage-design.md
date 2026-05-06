# Feature C2 — Paper Trading Slippage (设计文档 · v0)

- 日期: 2026-05-04
- 范围: 给纸面账户的市价单加可选滑点参数，让"用户输入价格 → 实际成交价"之间产生可控偏差
- 状态: 用户已确认全权决策

## 当前状态（C v0）

`PaperOrderRequest` schema：

```python
class PaperOrderRequest(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float
    fill_price: float
    commission: float (default 0)
```

订单立即按用户输入的 `fill_price` 成交，零执行成本。这意味着：

- 在回测里看到的策略带入纸面跑时，paper trading 给出的 PnL 比实盘更乐观
- 用户没有"输入价格 vs 实际成交价"差距感

## v0 范围

| 含 | 不含 |
|----|------|
| `slippage_bps` 可选字段（基点，0-100，默认 0）| 限价/止损单（需 pending 状态机，下一批） |
| 立即成交按 `effective_fill_price` 计算现金 / 持仓成本 | 滑点模型可配置（线性/平方根/订单簿撮合） |
| 订单流水里同时记录 `fill_price`（用户输入）和 `effective_fill_price`（实际） | 后端跨账户聚合滑点 |
| 默认 0 保持向后兼容 | 自适应滑点（按行情 spread 推断） |

## 数学

`bps`（basis points）= 万分之一。

- BUY：`effective_fill_price = fill_price × (1 + slippage_bps / 10_000)` —— 实际成交价比用户填的高，符合"市场冲击"语义
- SELL：`effective_fill_price = fill_price × (1 - slippage_bps / 10_000)` —— 卖出按更差价，对买卖双方对称

例：fill_price = 100, slippage_bps = 5（万分之五，0.05%）
- BUY 实际成交 100 × 1.0005 = 100.05
- SELL 实际成交 100 × 0.9995 = 99.95

`fill_price = 0` 或 `slippage_bps = 0` 时退化为无滑点（与现状一致）。

## Schema 变化

### 后端

```python
class PaperOrderRequest(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float
    fill_price: float       # 用户填的"目标价"
    slippage_bps: float = 0 # 0 ≤ bps ≤ 100（最大 1%）
    commission: float = 0
    note: str = ""
```

`slippage_bps > 100` 在 schema 层 422，避免误填 5000 这种"半数滑点"的灾难。

### 持久化

`PaperTradingStore._apply_order` 现在记录：

```json
{
    "id": "ord-...",
    "symbol": "AAPL",
    "side": "BUY",
    "quantity": 5,
    "fill_price": 150,
    "effective_fill_price": 150.075,
    "slippage_bps": 5,
    "commission": 0,
    "submitted_at": "...",
    "note": ""
}
```

老订单（schema 改之前）没有 `effective_fill_price` 字段——读取时回退到 `fill_price`。

cash / 持仓 avg_cost 使用 `effective_fill_price`。

### 前端

- 下单表单新增 `slippage_bps` 字段（InputNumber，min=0，max=100，step=1，suffix="bps"，默认 0）
- 订单历史表加 "实际成交价" 列，仅在 effective ≠ fill_price 时显示，否则同列显示 fill_price
- 不动现有 success message（依然显示 `fill_price`，因为这是用户主动输入的字段；effective 在订单详情里看）

## 不在范围（明确推迟）

- 限价单 / 止损单 / 跟踪止损（需要 pending state，订单超时撤单等）
- 滑点根据 quantity / 流动性自适应（v0 用户自己填）
- 修改既有订单的 effective_fill_price（schema 升级；老订单仍以 `fill_price` 为准）
- buildPrefillFromBacktest / Journal 自动建议滑点
- 把滑点写进 paper-position 的 journal entry summary

## 测试

### 后端 `tests/unit/test_paper_trading.py` 扩展

5 个新用例：
1. BUY 带 slippage_bps=10 → cash 和 avg_cost 用 effective_fill_price 计算
2. SELL 带 slippage_bps=10 → cash 用 effective_fill_price（更低）计算
3. slippage_bps=0 行为与现状完全一致（向后兼容回归）
4. 订单记录同时持久化 fill_price + effective_fill_price + slippage_bps
5. slippage_bps > 100 → 422 schema 错误

### 前端 `paper-trading-panel.test.js` 扩展

1 个新用例：填入 slippage_bps 表单字段 → 提交时 payload 含该字段。

## 验证标准

| 编号 | 条件 |
|------|------|
| C2.B | 后端测试套件全绿（含 5 个新用例）|
| C2.F | 前端测试套件全绿（含 1 个新用例）|
| C2.整 | 整体回归无破坏 |
| 手验 | UI 下单表单出现 slippage_bps 字段；非零时订单历史显示 effective_fill_price |

## 风险

- **极低**：schema 加可选字段，service 层加纯数学，零状态机引入
- 唯一坑：老订单（持久化在磁盘上）没 effective_fill_price 字段——读取时 graceful fallback 到 fill_price，已在 _coerce_account 处理

## 实施顺序

1. 后端 schema + service + 5 个新单测 → commit
2. 前端表单字段 + payload 透传 + 1 个新测 → commit
3. 完整回归
