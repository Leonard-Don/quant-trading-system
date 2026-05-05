# Feature C3 — Paper Trading Stop-Loss (设计文档 · v0)

- 日期: 2026-05-05
- 范围: 给纸面账户的 BUY 订单加可选 `stop_loss_pct` 字段，持仓携带止损线，前端 quote 轮询时检测并自动 SELL
- 状态: 用户已确认全权决策

## 当前状态

C/C2/I 把 paper trading 做成了"手动下单 + 滑点 + 一键市价"。但 **没有任何风险控制**——一旦下单，position 就静坐到用户手动 SELL。在反向趋势里浮亏会无限累积。

## v0 范围

| 含 | 不含 |
|----|------|
| BUY 订单可选 `stop_loss_pct`（0–0.5）| 限价单、止盈、跟踪止损 |
| 持仓持久化 `stop_loss_pct` + `stop_loss_price`（计算字段）| 后端定时检测（需要新 worker）|
| 前端 quote 轮询时检测：last_price < stop_loss_price → 自动 SELL | 跨标签页同步（用户多开 paper tab 会重复触发的边界）|
| 持仓表显示止损价 + 距触发距离 | 全仓清算 / 组合级风控 |
| 触发后 message 通知用户 | UI 内取消/调整止损 |

## 数学

- 用户在 BUY 时填 `stop_loss_pct = 0.05`（5% 止损）
- 持仓的 `stop_loss_price = avg_cost × (1 - stop_loss_pct)`
  - 加仓后用新的加权 `avg_cost` 重算（避免老仓位的止损线被新加仓拖低）
- 前端 quote 轮询发现 `last_price ≤ stop_loss_price` → 自动 SELL 全部数量
- SELL 订单的 `note` 字段标 `stop_loss_triggered`，订单流水可识别

`stop_loss_pct = 0` 或缺失 → 跳过止损检测，与 C v0 行为完全一致。

## 风险与边界

- **单 tab 触发**：v0 只在用户 paper 工作区打开时检测，关掉就停。这是有意识的——paper 是研究工具不是经纪商，不应该在后台默默吃金。spec 里写明。
- **5 秒轮询延迟**：现有 quote 轮询周期 5s。极端行情可能 close-to-close 跌穿不触发——可接受范围。
- **多 tab 重复触发**：同一 profile 在两个 tab 打开都会检测。后端 SELL 量超持仓时返回 422，第二次自动 SELL 会失败但不破坏状态。
- **滑点叠加**：自动 SELL 默认 `slippage_bps = 10`（中等保守），模拟止损时市场已经在跌、流动性变差的场景。spec 里是固定值，未来可作为持仓字段。

## Schema 变化

### 后端 `PaperOrderRequest`

```python
stop_loss_pct: Optional[float] = Field(default=None, ge=0, le=0.5)
```

只在 BUY 订单上有意义；SELL 时被忽略。schema 不强制 side 互斥（避免破坏 SELL 路径），service 层在 BUY 时把 stop_loss_pct 写到 position，SELL 时不读。

### 持仓 schema

新增字段：

```python
{
    "stop_loss_pct": Optional[float],
    "stop_loss_price": Optional[float],   # 计算字段，自动派生
}
```

老持仓（C2 之前）没这两字段，读取时为 None / null，不触发止损。

### 加仓时的止损线

加仓的语义讨论：

- **方案 A**：保留旧仓位的止损线（更激进——加仓但不调整保护）
- **方案 B**：用新加权 avg_cost 重算（更对称——任何加仓都按当前总成本计止损）
- **方案 C**：用新订单的 stop_loss_pct 重新设置（最易理解）

选 B：加仓时如果新订单也带 `stop_loss_pct`，用新的；否则保留旧的。重算 `stop_loss_price = new_avg_cost × (1 - new_stop_loss_pct or old_stop_loss_pct)`。

### 自动 SELL 订单标识

`note = "stop_loss_triggered"` + `slippage_bps = 10`，订单 record 一目了然。

## 前端

### 下单表单

新加 `止损（可选，%）` InputNumber，min=0，max=50（即 0.5），step=1，suffix="%"，默认 0。提交时除以 100 转成 ratio 再传给后端。

只在 side=BUY 时显示该字段（form watcher）。

### 持仓表

新增列 "止损价"，显示 `formatMoney(stop_loss_price)` 或 "—"。下方小字 "距触发 X.XX%"（红色高亮如果 < 1%）。

### 轮询触发

`useEffect` quote 轮询块加：

```js
positions.forEach((position) => {
    const slPrice = Number(position.stop_loss_price);
    const lastPrice = Number(quoteMap[position.symbol]?.price);
    if (Number.isFinite(slPrice) && Number.isFinite(lastPrice) && lastPrice <= slPrice) {
        // already-triggered guard via Set
        if (triggeredSetRef.current.has(position.symbol)) return;
        triggeredSetRef.current.add(position.symbol);
        autoTriggerStopLoss(position, lastPrice);
    }
});
```

`triggeredSetRef` 防止同一持仓在 SELL 完成前被多次触发（请求未完成期间持仓仍在 list 里）。SELL 成功后从 set 移除（refresh 后持仓消失，set 自然清空）。

`autoTriggerStopLoss` 调用 `submitPaperOrder` with side=SELL, quantity=持仓数, fill_price=last_price, slippage_bps=10, note="stop_loss_triggered"。成功后 message.warning 通知 + refresh。

## 测试

### 后端

5 个新用例：
1. BUY with stop_loss_pct=0.05 → position 含 stop_loss_pct=0.05 + stop_loss_price=95（avg=100）
2. 加仓时 BUY 不带 stop_loss_pct → 保留旧 stop_loss_pct，但 stop_loss_price 用新 avg_cost 重算
3. 加仓时 BUY 带新的 stop_loss_pct → 新 pct 取代旧的，stop_loss_price 用新 avg + 新 pct
4. SELL 时 stop_loss_pct 忽略（请求带也不报错，position 不变）
5. schema 422：stop_loss_pct > 0.5

### 前端

3 个新用例：
1. BUY 表单填止损 → 提交时 payload 含 stop_loss_pct（除以 100 转换）
2. 持仓表显示 stop_loss_price 和距离百分比
3. quote 触发自动 SELL：mock quote 返回 < stop_loss_price → submitPaperOrder 被调用，side=SELL，note="stop_loss_triggered"

## 不在范围

- 后端定时检测（需要新 worker / scheduler，超 v0）
- 跟踪止损（trailing stop）
- 止盈（take profit，对偶但需另一组字段 + 触发）
- 止损线手动调整 UI（v0 设了就固定，要改只能 SELL 重 BUY）
- 多 tab 同步（用 BroadcastChannel 等）

## 实施顺序

1. 后端 schema + service + 5 个新单测
2. 前端 form 字段 + position table 列 + 轮询触发 + 3 个新测
3. 完整回归
