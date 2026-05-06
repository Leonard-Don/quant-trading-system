# 多日 Session Retrospective（2026-05-03 → 2026-05-05）

一个连续多天的协作 session 的全景索引。本文档不是设计稿，是回看清单——
任何想要"这段时间里到底做了什么"的人（包括未来的 Claude / 用户本人）
直接读这一页就够。

## 数字概览

| 指标 | 起 | 终 | Δ |
|------|----|----|----|
| 后端 pytest（unit + integration，跳过 perf） | ~480 | **541** | +60+ |
| 前端 jest 套件 | 30 | **53** | +23 |
| 前端 jest 用例 | 245 | **413** | +168 |
| commits（this session arc） | `928fe00` | `f9a42e8`+ | 38+ |
| 前端 build 警告 | n/a | **0** | clean |

## 三类工作

### 一、新功能（15 项）

| # | 主题 | 工作区 | Commit | 备注 |
|---|------|--------|--------|------|
| A | Walk-Forward + 参数搜索 | backtest | （README 曝光）| 调研后发现早已实现，本次只让其在介绍文档可见 |
| B | 多策略组合 / Portfolio | backtest | （README 曝光）| 同 A |
| C | 纸面账户 v0 | paper | `659ae13` | 手动 BUY/SELL，per-profile 持久化 |
| D | 政策雷达 UI | industry | `fd7cc5c` | 把已就绪的 alt-data PolicySignalProvider 抬到前端 |
| D2 | 政策叠加到行业热力图 | industry | `116feef` | tile 右上角徽标，opt-in 切换 |
| E | 实验追踪（auto-archive 回测）| backtest | `6ed2369` | App.handleBacktest 自动写 journal entry |
| F | 回测结果 → 纸面（手填）| backtest → paper | `fa0b0e1` | sessionStorage 一次性 prefill |
| G | 历史档案 → 纸面 | today → paper | `13c5150` | TodayResearchDashboard 上的 send-to-paper 按钮 |
| H | 纸面持仓 → 档案 | paper → today | `68d921c` | 一键 archive 持仓到 journal trade_plan 条目 |
| I | 回测 → 纸面（按市价直接下单）| backtest → paper | `be19672` | F 的快速路径，Popconfirm 防误点 |
| C2 | 滑点（slippage_bps）| paper | `8eded28` | BUY 实付高 / SELL 收少 |
| C2.1 | 滑点订单可视化 | paper | `a46a530` | effective_fill_price 显示在订单表 + tooltip |
| C3 | 止损（stop_loss_pct + 自动 SELL）| paper | `0aaa788` | 前端 quote 轮询触发 |
| C4 | 止盈（take_profit_pct + 自动 SELL）| paper | `12cfd55` | 镜像 C3，统一 fireAutoSell helper |
| C5 | 限价单 + 取消 | paper | `f9a42e8` | 新 pending_orders 状态机；DELETE /paper/orders/{id} 端点 |

### 二、重构 / 拆分（layer 1 + layer 2）

| 组件 | layer 1 | layer 2 |
|------|---------|---------|
| `IndustryHeatmap.js` | `c4cced1` 2014→1826 (−188) | `d67ea4b` Legend + `6b2945a` StatsBar，−208 |
| `MarketAnalysis.js` | `2c13f3b` 2660→2566 (−94) | `d8ba25d` ScoreVisuals，−86 |
| `CrossMarketBacktestPanel.js` | `8bb39a5` 2858→2727 (−131) | `d28e261` AssetSection，−39 |
| `RealTimePanel.js` | `afd8bac` 3273→3066 (−207) | （仅 layer 1，layer 2 留给后续）|

合计 4 mega-component layer 1 共 −620 行，layer 2 已抽 4 个子组件再减 −333 行。
拆分剧本和进度表：[`docs/architecture/frontend-component-split-playbook.md`](../../architecture/frontend-component-split-playbook.md)。

### 三、维护 / Bug 修复 / 加固

| 类型 | Commit | 说明 |
|------|--------|------|
| Bug 修复 | `dbc6685` | `?view=paper` 路由静默兜底回 `backtest`（PUBLIC_VIEWS 漏 'paper'） |
| Bug 修复 | （含在 `d8ba25d` 内）| `colorForScore(null)` 误判为红色（Number(null)===0）|
| Bug 修复 | （含在 `12cfd55` 内）| polling effect 不稳 deps 导致测试 timeout |
| 加固 | `5adfe9f` | CI 切到 `verify:all`，把 today/backtest/new 三个 verify 拉回流水线 |
| 加固 | `a6713f5` | `verify_new_features.js` 探针扩 G/H/C2 |
| 清理 | `81bfb09` | 删 11 个孤立 ad-hoc 脚本（−410 行）|
| 文档 | `327f0a7` | industry layering charter（src/analytics ↔ services/industry ↔ endpoints 三层关系）|
| 文档 | `5deca9e` | frontend split playbook |

## 跨工作区闭环：研究 ↔ 验证

```
                  ┌────────── E: auto-archive ──────────┐
                  ▼                                     │
[ 跑回测 ] ───┬──► [ Today Research 档案 ] ◄──────────┐
              │            │                           │
              │    G: 送到纸面                         │
              │            ▼                           │
              │    [ Paper Trading 工作区 ]            │
              │            ▲                           │
              ├── F: 送到纸面（手填）                  │
              ├── I: 按市价直接下单                    │
              │                                        │
              └────────────┘                           │
                                                       │
                  H: 归档到档案 ◄──────────────────── ┘
```

四个跨工作区入口已全部接通。Paper trading 内部已具备：手动 / 市价 / 限价 /
取消 / 滑点 / 止损 / 止盈 / 自动跟单 / mark-to-market。

## 哪些事 deliberately 没做

每条都有"为什么不做"的理由，避免下次 session 误把它们捡起来：

- **后端 scheduler 跑 stop-loss / take-profit / limit triggers**：v0 frontend
  polling 已够用，scheduler = 新进程 + 任务队列基础设施，与"本地研究工具"
  定位不符。
- **现金 / 持仓预占（pending LIMIT 不锁 cash）**：v0 选择"触发时再校验"，
  与现有 stop-loss / take-profit 一致。spec 解释见
  `docs/superpowers/specs/2026-05-05-feature-c5-limit-orders-design.md`。
- **Time-in-force（GTC / DAY / IOC）**：超 v0。
- **多 tab 同步触发**：单 tab 已交付，多 tab 重复触发被后端 422 自动挡。
- **paper trading 自动 strategy 跟踪**：F/G/I 给的是"信号点的一次性下单"，
  不是 strategy supervisor。
- **RealTimePanel layer 2/3**：79 个 hooks 之间的依赖图必须先理清，layer 1
  是安全的；layer 2/3 留给后续专门 session。
- **拆 src/analytics/industry_analyzer.py 或 backend/app/services/industry/runtime.py**：
  调研发现"职责模糊"判断错了——三层都已经有清楚边界，问题是体量。
  分层文档（`docs/architecture/industry-layering.md`）写明了演进方向但
  本期不动代码。

## 三类 spec 索引

所有本期产出的设计稿（`docs/superpowers/specs/`）：

```
2026-05-03-batch-a-repo-hygiene-design.md
2026-05-03-batch-b-industry-layering-design.md
2026-05-03-batch-c-integration-tests-design.md
2026-05-03-batch-d-frontend-split-design.md
2026-05-03-feature-d-policy-radar-design.md
2026-05-03-feature-roadmap.md
2026-05-04-feature-d2-policy-overlay-design.md
2026-05-04-feature-c-paper-trading-design.md
2026-05-04-feature-f-backtest-to-paper-handoff-design.md
2026-05-04-feature-g-journal-to-paper-design.md
2026-05-04-feature-h-paper-positions-to-journal-design.md
2026-05-05-feature-i-backtest-auto-execute-design.md
2026-05-05-feature-c2-slippage-design.md
2026-05-05-feature-c3-stop-loss-design.md
2026-05-05-feature-c5-limit-orders-design.md
2026-05-05-session-retrospective.md           ← (本文档)
```

C4 (take-profit) 直接复用了 C3 spec；后续如果要扩，可单独写。

## 下次 session 的"开盖即用"清单

如果下次想继续：

1. **Layer 2 续作**：MarketAnalysis 还有 tab content useMemos 可以抽（按
   playbook layer 2 方法）。CrossMarket 仍有大型 render 块。
2. **RealTimePanel layer 2/3**：先理清 79 个 hooks 的状态依赖图，再动。
3. **paper trading 风控扩展**：跟踪止损 / 时间触发 / 全仓清算。
4. **后端 scheduler**：把 stop-loss / take-profit / limit trigger 后端化，
   解除"必须打开 paper workspace"限制。
5. **F2: paper trading 持仓导出 CSV**：`buildBacktestJournalEntry` 抽出
   后已经有完整 mark-to-market 数据，加 CSV 导出按钮 = 30 分钟工作。
6. **回测 alpha attribution**：把 backtest 的每笔 trade 的 P&L 归因到
   策略组件（信号 / 风控 / 滑点）。
