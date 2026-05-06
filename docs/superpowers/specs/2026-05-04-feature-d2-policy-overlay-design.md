# Feature D2 — Policy Overlay on Industry Heatmap (设计文档)

- 日期: 2026-05-04
- 范围: 把 D 阶段引入的 `policy_radar.industry_signals` 叠加到 `IndustryHeatmap` 的 tile 上
- 状态: 用户已确认全权决策

## 背景

D（commit `fd7cc5c`）已经把政策信号通过 `/policy-radar/signal` 暴露并放在 `IndustryDashboard` 的"政策雷达"tab 中。但热力图本身仍只反映 price / netflow / turnover 维度，看不到"这个行业有政策利好/利空"——研究者需要在两个 tab 之间反复切换才能合并两条信息。

D2 在主热力图上加一层政策叠加，让"行业涨幅 + 政策强度"成为同屏阅读。

## 设计

### 数据连接

- 复用 `getPolicyRadarSignal()`（D 已有）
- 拿到 `industry_signals: {industryName: {avg_impact, mentions, signal}}` 之后，按行业名 join 到热力图 items
- 行业名匹配用已抽取的 `normalizeIndustrySearchText` 工具（IndustryHeatmap 抽取期 `c4cced1`）做归一化匹配，避免"新能源" vs "新能源板块"之类小差异落空

### 视觉表达

不动主色（`change_pct` / `net_inflow_ratio` 等映射的红绿色不变），而是**在 tile 右上角加一个小三角徽标**：

| 政策信号 | 徽标 | 含义 |
|----------|------|------|
| `bullish`（avg_impact > 0.2） | 红色三角 ▲ | 政策利好 |
| `bearish`（avg_impact < -0.2） | 绿色三角 ▼ | 政策利空 |
| `neutral` 或缺失 | 不渲染 | — |

中性时不渲染徽标，保持热力图视觉负载不增加。

### 用户控制

热力图工具栏增加一个开关 "政策"（默认 off）。开启后才发起 `getPolicyRadarSignal()` 请求并显示徽标。关闭时不请求、不显示。

理由：
- 政策数据天然 hourly 节奏，多数情况下用户不需要每次刷新行情都拉一遍
- 默认 off 不破坏现有用户的视觉习惯
- 开关状态用 React state 即可，不持久化（与现有热力图开关风格一致）

### tooltip 增强（次要）

tile 悬浮 tooltip 已有"换手率 / 龙头股 / 资金流"等行；加一行"政策信号"，在政策叠加 ON 且有数据时显示 `偏多 / 偏空 / 中性 (mentions 个事件)`。

## 实现

### 新增 `frontend/src/utils/industryPolicyOverlay.js`

纯函数，纯 join 逻辑，无 React。导出：

```js
// 把 heatmap items 和 policy industry_signals 用归一化名字 join，
// 输出 enrichments: { [industryName]: { signal, avgImpact, mentions } }
export const buildPolicyOverlay = (industries, industrySignals) => { ... }

// 给定一个 industry 和一个 enrichments 字典，
// 返回 {signal, avgImpact, mentions} 或 null
export const lookupPolicyOverlay = (industryName, enrichments) => { ... }

// signal 阈值常量供 UI 复用
export const POLICY_OVERLAY_THRESHOLD = 0.2;
```

### IndustryHeatmap 修改

1. 顶部 import `getPolicyRadarSignal`、`buildPolicyOverlay`、`lookupPolicyOverlay`
2. 新增 state `[policyOverlayOn, setPolicyOverlayOn]`，`[policyOverlayMap, setPolicyOverlayMap]`
3. 新增 `useEffect` 仅在 `policyOverlayOn` 切到 true 时拉一次政策信号；持久化结果到 state
4. 工具栏 metric 切换组下方加一个 Switch："政策"，绑定 `policyOverlayOn`
5. tile 渲染 block 加一个右上角徽标，使用绝对定位；`zIndex: 6`；不影响交互
6. tooltip 末段加一行政策信号

### 测试

- `frontend/src/__tests__/industry-policy-overlay.test.js` — 7 个用例覆盖纯函数：
  1. 基础 exact 匹配
  2. 归一化匹配（"新能源" ↔ "新能源板块"）
  3. avg_impact 在阈值内 → signal=neutral
  4. avg_impact > 阈值 → signal=bullish
  5. avg_impact < -阈值 → signal=bearish
  6. 行业不在 industry_signals 中 → null
  7. 输入是空 / 非数组 → 返回空对象

- `industry-heatmap.test.js` 不动（视觉徽标用单元测试已覆盖）。如果时间允许，可以加一个 toggle 集成测试，但 IndustryHeatmap 是 1800 行的复杂组件，集成测试成本远高于纯函数测试，先不加。

## 不在范围

- 不把政策信号写进 `change_pct` 主色映射——用户希望"价格 vs 政策"分开看
- 不实时订阅 policy_radar（仍走 hourly 缓存的 HTTP 拉取）
- 不在 tile 上显示 mentions 数字（视觉负担太大；放在 tooltip）
- 不联动行业排行榜——后续如果需要，可以单独立项

## 验证标准

| 编号 | 条件 |
|------|------|
| D2.U | `industry-policy-overlay.test.js` 7 个用例全绿 |
| D2.整 | `industry-heatmap.test.js` 已有 3 用例不破坏 |
| 手验 | 启动后访问 `?view=industry`，开 "政策" 开关，bullish/bearish 行业 tile 出现红/绿三角 |

## 风险

- **极低**：纯前端、新增可选叠加层、默认 off
- 行业名匹配可能不完美（不同 provider 用不同别名），但归一化函数已经处理了主要情形；剩余 mismatch 在 lookup 层返回 null，不会报错
