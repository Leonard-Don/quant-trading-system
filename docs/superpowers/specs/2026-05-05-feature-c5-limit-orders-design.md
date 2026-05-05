# Feature C5 — Paper Trading Limit Orders (设计文档 · v0)

- 日期: 2026-05-05
- 范围: 给 paper trading 加 LIMIT 单：用户提交后挂入 pending list，前端 quote 轮询触发时按 limit_price 成交
- 状态: 用户已确认全权决策（"都做完"）

## 现状

C / C2 / C3 / C4 让 paper trading 拥有：

- MARKET 立即成交（C v0）
- 滑点（C2）
- 止损 / 止盈自动触发（C3 / C4）

**缺**：用户没法挂单——想"AAPL 跌到 95 就买入"必须自己盯盘手动下单。

## v0 范围

| 含 | 不含 |
|----|------|
| `order_type: MARKET / LIMIT` 字段（默认 MARKET，向后兼容）| 跟踪止损 / 时间触发的限价单 |
| LIMIT 订单：`limit_price` 必填，挂入 `pending_orders` 列表 | 后端 quote 触发轮询（前端轮询触发） |
| 前端 quote 轮询时：BUY-LIMIT 在 quote ≤ limit_price 时触发；SELL-LIMIT 在 quote ≥ limit_price 时触发 | LIMIT 订单的现金/持仓预占 |
| 触发：执行 MARKET 订单 @ limit_price + DELETE 原 pending | "GTC / GTD / IOC" 等 time-in-force |
| `DELETE /paper/orders/{id}` 取消 pending（仅 pending 可删，已成交不动）| 部分成交 |
| pending orders 列在 paper 工作区独立表，带 "取消" 按钮 | 撤单后通知 |

### 现金预占的取舍

**不预占**：v0 选这条。pending LIMIT 不锁定 cash；触发时按现有 _apply_order 路径检查 cash 是否充足，不足则 422 fail，前端在 message.error 显示。

理由：
- 实现简单，不需要 schema migration（cash 字段含义不变）
- 与现有 stop_loss / take_profit 一致（都不预占）
- v0 用户场景：手动盯几个 limit，不太会同时挂 100 个全仓预算

未来如果用户场景变成"挂大量限价单做对冲"，再加 `cash_reserved` 字段。

## Schema 变化

### `PaperOrderRequest`

```python
order_type: Literal["MARKET", "LIMIT"] = "MARKET"
limit_price: Optional[float] = Field(default=None, gt=0)
```

校验：`order_type == "LIMIT"` ⇒ `limit_price` 必填，否则 422。MARKET 时 limit_price 被忽略。

### Account 持久化

新增字段：

```json
{
    "pending_orders": [
        {
            "id": "ord-...",
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "limit_price": 95,
            "submitted_at": "...",
            "order_type": "LIMIT",
            "note": "..."
        }
    ]
}
```

老账户（C4 之前）没 pending_orders 字段，读取时 fallback 为 `[]`。

### Public view

`get_account` 返回新增 `pending_orders: [...]`，前端读出渲染 pending 表。

## API

```
POST /paper/orders            # 已有，新支持 order_type + limit_price
DELETE /paper/orders/{id}     # 新增：仅取消 pending，已成交订单返回 422
```

### POST /paper/orders 行为

- `order_type = "MARKET"`（默认或显式）→ 走现有 `_apply_order` → 立即成交
- `order_type = "LIMIT"` → 走新 `_queue_limit_order`：
  - 验证 limit_price > 0
  - 拒绝同 symbol/side 已经在 pending（避免重复挂单）—— **可不做，v0 简化为允许**，跳过
  - append 到 `account.pending_orders`，分配 id（`ord-pending-...`）
  - 返回 `{order: {...}, account: public_view}`，pending order 在 public view 里可见

### DELETE /paper/orders/{id}

- 在 `pending_orders` 找 id：找到则移除，返回 `{success: true, data: account_view}`
- 找不到：404
- id 在 orders（已成交）里：422 with message "order already filled, cannot cancel"

## 前端

### 下单表单

- 新增 Segmented "MARKET" / "LIMIT"
- order_type=LIMIT 时显示 `limit_price` 字段（取代 fill_price？或并存）

UX 决策：复用 `fill_price` 字段——MARKET 时它是"立即成交价"，LIMIT 时它是"限价"。表单 label 根据 order_type 切换："成交价" / "限价"。这样表单不会复杂化太多。

实际上：MARKET 模式还需要 fill_price 输入吗？现在 MARKET 也是用户填 fill_price（C v0 设计就是用户填价）。所以 LIMIT 的 limit_price 完全等同于 MARKET 的 fill_price。直接复用同字段，提交时根据 order_type 把它命名为 `fill_price`（MARKET）或 `limit_price`（LIMIT）。

### Pending orders 表

新增独立 Card，紧挨"近期订单"。列：时间 / 方向 / 标的 / 数量 / 限价 / 当前价（quote） / 距触发 / 操作（取消按钮）。

### 触发逻辑

`fetchQuotes` 内的现有 stop-loss/take-profit 块旁边加 pending 检测：

```js
pendingOrders.forEach((order) => {
    const lastPrice = Number(quoteMap[order.symbol]?.price);
    const limitPrice = Number(order.limit_price);
    if (!Number.isFinite(lastPrice) || !Number.isFinite(limitPrice)) return;
    const inFlightKey = `limit:${order.id}`;
    if (limitInFlightRef.current.has(inFlightKey)) return;

    const triggered = order.side === 'BUY'
        ? lastPrice <= limitPrice
        : lastPrice >= limitPrice;
    if (!triggered) return;

    limitInFlightRef.current.add(inFlightKey);
    submitPaperOrder({
        symbol: order.symbol,
        side: order.side,
        quantity: order.quantity,
        fill_price: limitPrice,  // 按限价成交，不滑点（限价单天然定价）
        commission: 0,
        slippage_bps: 0,
        note: 'limit_triggered',
    }).then(() => deletePaperOrder(order.id))
      .then(() => {
          message.success(`${order.symbol} 限价 ${order.side} ${order.quantity} 已成交 @ ${limitPrice}`);
          limitInFlightRef.current.delete(inFlightKey);
          refresh();
      })
      .catch((err) => {
          limitInFlightRef.current.delete(inFlightKey);
          message.error(`${order.symbol} 限价单触发失败：${err.message}`);
      });
});
```

注意：触发后两步——先 POST MARKET，再 DELETE pending。如果 POST 失败（cash 不足），DELETE 不执行，pending 留着等下次触发或用户手动取消。

### 取消按钮

调用 `deletePaperOrder(id)` → 成功后 refresh。

## 测试

### 后端（5-6 个新用例）

1. POST LIMIT order → pending_orders 含该订单，cash/positions 不变
2. POST LIMIT 缺 limit_price → 422
3. POST LIMIT with limit_price=0 → 422（schema gt=0）
4. DELETE pending order → pending_orders 列表中该 id 消失
5. DELETE 已成交 order id → 422 with "already filled"
6. DELETE 不存在 id → 404
7. account_view 序列化包含 pending_orders 字段（含一条挂单时）

### 前端（3-4 个新用例）

1. 表单选 LIMIT → 提交时 payload 含 order_type=LIMIT + limit_price
2. pending 表渲染 + 取消按钮调用 deletePaperOrder
3. quote 触发：BUY LIMIT 当 quote ≤ limit → submitPaperOrder + deletePaperOrder 都被调用
4. SELL LIMIT 类似

## 不在范围

- Time-in-force（GTC / DAY / IOC）
- 部分成交
- 现金/持仓预占
- 自动撤老 LIMIT 当新 MARKET 用同 cash
- 后端 quote 触发（依然前端轮询）

## 验证标准

| 编号 | 条件 |
|------|------|
| C5.B | 后端 7 用例全绿 |
| C5.F | 前端 4 用例全绿 |
| C5.整 | 整体回归无破坏；既有 paper trading 行为不变 |

## 实施顺序

1. 后端 schema + service `_queue_limit_order` + DELETE endpoint + 7 个新用例
2. 前端表单 order_type Segmented + Pending orders 表 + 触发逻辑 + 4 个新用例
3. 完整回归
