# Feature C — Paper Trading Simulator (设计文档 · v0)

- 日期: 2026-05-03
- 范围: 纸面实盘模拟器最小可用版本（v0），后续可在此基础上叠加 strategy 自动执行 / 撮合细节
- 状态: 用户已确认全权决策

## 全功能 vs v0 的取舍

完整版 paper trading（评估时估时 3–4 周）涉及：

1. 策略 → 信号 → 订单的自动管线
2. 撮合层（bid/ask 模拟、滑点、部分成交、撤单）
3. 持仓 + 风控 + 强平
4. 实时撮合循环（订阅 realtime feed → 触发条件单）
5. 对账、报表、回放

单 session 全部交付 = 不切实际。

**v0 的设计原则**：交付一个"可见、可点、能持久化、能算盈亏"的最小账本，作为后续 feature 的基底；不假装做撮合、不假装做策略联动。

## v0 范围

| 能力 | v0 含 | v0 不含 |
|------|------|---------|
| 手动提交 BUY/SELL 订单 | ✅ | 自动信号触发 |
| 立即成交（用户提供成交价） | ✅ | bid/ask 模拟、滑点、撮合延迟 |
| 持仓 + 现金 + 订单流水 | ✅ | 保证金、融资融券、强平 |
| 加权平均成本计算 | ✅ | LIFO/FIFO 选择 |
| 客户端 mark-to-market PnL | ✅（用现成 realtime quote）| 服务端 PnL 推送 |
| 多账号（per profile）持久化 | ✅ JSON 落盘 | 跨设备同步 |
| 重置账户 | ✅ | 历史快照 / 还原版本 |

> 这个 v0 类似"个人纸面账本"，不是"自动化交易引擎"。其价值在于：让回测里看好的策略能放进一个真实日历驱动的容器跑，而不是在 backtest 历史数据里测一次就丢。

## 数据模型

### Backend persistence

```json
{
  "profile_id": "default",
  "initial_capital": 10000.0,
  "cash": 9215.0,
  "positions": {
    "AAPL": {
      "symbol": "AAPL",
      "quantity": 5.0,
      "avg_cost": 157.0,
      "opened_at": "2026-05-03T08:00:00+00:00",
      "updated_at": "2026-05-03T08:00:00+00:00"
    }
  },
  "orders": [
    {
      "id": "ord-1",
      "symbol": "AAPL",
      "side": "BUY",
      "quantity": 5.0,
      "fill_price": 157.0,
      "commission": 0.0,
      "submitted_at": "2026-05-03T08:00:00+00:00",
      "note": ""
    }
  ],
  "created_at": "2026-05-03T08:00:00+00:00",
  "updated_at": "2026-05-03T08:00:00+00:00"
}
```

每个 `profile_id` 一份文件，存到 `data/paper_trading/{profile-id}.json`，复用 `research_journal_store` 的"per-profile JSON + threading.RLock"模式。

### Order 业务规则（v0）

- **BUY**: `cash -= quantity × fill_price + commission`；若 cash 不足，**拒单**返回 422；持仓加权平均：
  ```
  new_avg = (old_qty × old_avg + new_qty × fill_price) / (old_qty + new_qty)
  ```
- **SELL**: 必须有足量持仓（无做空）；不足时拒单 422；`cash += quantity × fill_price - commission`；持仓减去后若为 0 则移除该 key
- **不支持**：fractional shares 之外的精度问题、currency conversion、跨账户对手方
- **commission 默认 0**，可选传入

### PnL 计算 (frontend, on quote tick)

```
unrealized_pnl(position, quote) = position.quantity × (quote.price - position.avg_cost)
total_equity = cash + Σ position.quantity × quote.price
total_return = (total_equity - initial_capital) / initial_capital
```

不依赖服务端推送，前端从 `useRealtimeFeed` 的 quote 算就够。

## 后端 API

```
GET  /paper/account              — 当前账户状态
POST /paper/orders               — 提交 BUY/SELL 订单（同步）
GET  /paper/orders               — 订单历史（倒序）
POST /paper/reset                — 重置账户至初始资金
```

profile 解析复用 `research_journal._resolve_research_profile` 的同款逻辑（Header `X-Research-Profile` > query `profile_id` > "default"），保持工作台一致。

### 端点契约要点

- `POST /paper/orders` 请求体：`{symbol, side, quantity, fill_price, commission?, note?}`；422 对应业务错误（cash 不足 / 持仓不足）；400 对应 schema 错误
- `GET /paper/account` 响应：`{cash, positions[], orders_count, initial_capital, created_at, updated_at}`，positions 是数组形态便于前端 v-for
- `POST /paper/reset` 请求体：`{initial_capital?: float}`，默认 10000

## 前端

### 新增独立工作区 `?view=paper`

不塞进已经 3,273 行的 `RealTimePanel.js`。新建独立 view：

- `frontend/src/components/PaperTradingPanel.js` — 顶级懒加载组件
- 在 `App.js` 加入 `paper` view 路由 + 菜单项 + lazy import

### UI 组成

1. **顶部账户卡**：现金 / 总权益 / 总收益 / 持仓数 / 订单数 / "重置"按钮
2. **下单条**：symbol 输入 + side 切换 + quantity + fill_price + 提交按钮（成交即时反馈）
3. **持仓表**：symbol / 数量 / 均价 / 当前价（用 realtime feed） / 浮动盈亏
4. **订单历史**：最近 50 条订单倒序

### realtime feed 复用

- 用现有 `getMultipleQuotes(symbols)` 拉一次性 quote，或 `useRealtimeFeed({symbols})` 订阅 WebSocket
- v0 选 polling：轮询 `getMultipleQuotes(positions.map(p => p.symbol))` 每 5 秒，避免直接调 useRealtimeFeed 引入复杂的订阅管理

## 测试

### 后端

`tests/unit/test_paper_trading.py`（8 个用例）：

1. 全新账户 → `get_account` 返回 initial_capital + 空 positions
2. BUY 成功 → cash 减少、positions 出现该 symbol 且数量正确
3. 同 symbol 多次 BUY → avg_cost 加权平均
4. SELL 部分 → 数量减少、cash 增加
5. SELL 全部 → positions 中该 key 消失
6. 现金不足 → BUY 返回 422，账户状态不变
7. 持仓不足 → SELL 返回 422，账户状态不变
8. reset 后回到 initial_capital

### 前端

`frontend/src/__tests__/paper-trading-panel.test.js`（4 个用例）：

1. 渲染：mock `getPaperAccount` 返回有持仓状态 → 表格行出现，账户卡显示总权益
2. 提交订单：填表 → 调用 `submitPaperOrder`
3. 提交失败：API 抛 422 → 显示错误 message
4. 重置：点击 reset → 调用 `resetPaperAccount`

## 验证标准

| 编号 | 条件 |
|------|------|
| C.B | `pytest tests/unit/test_paper_trading.py -q` 通过；8 个用例全绿 |
| C.F | `CI=1 npm test -- --testPathPattern=paper-trading-panel` 通过；4 个用例全绿 |
| C.整 | 后端 504+ / 前端 260+ 全绿 |
| 手验 | `?view=paper` 能进入；下单后刷新能看到持仓；重置能清空 |

## 风险

- **低**：纯 read/write 的内存 + 文件状态机，无外部副作用
- **小坑**：精度——quantity 用 float 而非 Decimal 时，重复 BUY/SELL 后会有 float 漂移。v0 接受；如果用户真用来跟踪长期账户，再升级为 Decimal
- **持久化锁**：profile_id 范围内 `threading.RLock` 已足够，不引入跨进程协调

## 不在范围（明确推迟）

- 自动策略执行（需要新建一个 strategy supervisor 进程）
- 撮合细节（bid/ask 模拟、滑点、撤单、limit/stop 订单）
- 服务端 mark-to-market 推送
- 多账户聚合 / 跨 profile 比较
- 与 backtest 结果联动（"把这次回测的最优策略放进 paper trade 跑"）

## 实施顺序

1. 后端：schemas + service + endpoints + 单元测试 → commit
2. 前端：API client + PaperTradingPanel + view 路由 + 测试 → commit
