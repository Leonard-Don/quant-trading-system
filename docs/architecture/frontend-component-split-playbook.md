# Frontend Component Split Playbook

> 给后续 session 的指南：把 2k+ 行的前端巨型组件拆解成可维护规模时的安全步骤。
> 配套已完成案例：`frontend/src/components/IndustryHeatmap.js` 在 commit `c4cced1` 中按本剧本走了第一轮抽取。

## 适用场景

下列文件均超过 2,000 行且仍在主分支：

| 文件 | 行数 | 复杂度 |
|------|------|--------|
| `frontend/src/components/RealTimePanel.js` | 3,273 | 79 hooks |
| `frontend/src/components/CrossMarketBacktestPanel.js` | 2,858 | 46 hooks |
| `frontend/src/components/MarketAnalysis.js` | 2,660 | 37 hooks |
| `frontend/src/components/IndustryHeatmap.js` | ~1,826（已开始拆分） | 37 hooks |

每个文件应该用一个独立 session + 独立 spec + 独立 PR 处理，不要混在一起。

## 拆分成熟度的三层接缝

按从安全到风险递增排序。先做完第 1 层，再考虑第 2 层；多数情况下不需要做到第 3 层。

### 第 1 层：纯函数与常量（零风险）

**找什么**：

- 顶层 `const` 颜色 / 渐变 / 字体阴影 / URL / 时长常量
- 顶层 `function` / `const xxx = (args) => {...}` 不依赖 React、不引用组件 state
- 字符串归一化 / 搜索匹配 / 数据形状变换 / 数学计算 helper
- 不引入 hooks、不打 API 的纯辅助

**怎么做**：

1. 新建 `frontend/src/utils/<topic>.js`，原样搬过去（保留 JSDoc）。如果同一组件里有多组无关的纯函数，分别建文件而非塞一个。
2. 在原组件文件顶部 `import { ... } from '../utils/<topic>';`，删除本地定义。
3. 如果 helper 之前 `export`，在原组件文件加一行 re-export 保持 import 路径不变（避免改测试与外部 caller）：

   ```js
   export { buildFallbackHeatmapPayload };
   ```
4. `npm test -- --runInBand --watchAll=false --testPathPattern=<component-name>` 跑相关测试。
5. `CI=1 npm test -- --runInBand --watchAll=false` 跑全套，避免改名/路径意外影响其他模块。

**期望收益**：单文件 -100 ~ -300 行。`IndustryHeatmap.js` 通过这一层从 2014 → 1826 行（−188）。

### 第 2 层：纯展示子组件（低风险）

**找什么**：

- 组件主体里没有 hook、只接收 props 渲染 JSX 的内联 render fragment
- 工具栏 / 空状态 / 错误占位 / tooltip 内容 / 表头 / 单元格 / 单一卡片
- props 类型清晰（不依赖父级闭包变量）

**怎么做**：

1. 新建 `frontend/src/components/<ParentDir>/<SubName>.js`。如 `frontend/src/components/realtime/RealtimeQuoteBoardHeader.js`。
2. 把 JSX 提取，用 props 显式传入所有依赖（颜色、回调、文案）。
3. 在父组件用 `<SubName ... />` 替换原 JSX。
4. 跑组件级测试 + 全套测试。
5. **额外做**：人工浏览器开页面跑一遍——单测查不出像 z-index、`<Tooltip>` 嵌套、`useBreakpoint` 之类的视觉问题。

**期望收益**：单文件 -200 ~ -500 行；新建 1~3 个 ~50–150 行的纯展示组件。

### 第 3 层：含 hook 的子组件（中风险）

**找什么**：

- 一组紧密耦合的 hooks（如"提醒列表"的 useState / useEffect / useCallback / useMemo 五件套）
- 渲染时只用这组 hook 的状态、不需要父组件其他 state

**怎么做**：

1. 先把这组 hook 提取成 `useXxx` 自定义 hook，放到 `frontend/src/hooks/useXxx.js`。
2. 父组件调用 `const { state, actions } = useXxx(...)`，render 不变。
3. **此时仅 hook 拆分**——验证全套测试 + 浏览器手动跑通。
4. 然后再把 render 部分提取成子组件，传入 hook 返回的 `state` / `actions`。

**禁忌**：不要一步把"hook + render"一起搬走。Hook 拆分本身可能引入闭包陷阱（`useEffect` 依赖数组、`useCallback` 引用稳定性），先单独验证再做 render 拆分。

**期望收益**：单文件 -300 ~ -800 行；引入 1 个新 hook 文件 + 1 个新组件文件。

## 不要做的事情

- ❌ **不要把 79 个 hook 的 RealTimePanel 一刀切**：`RealTimePanel.js` 里的状态机互相耦合（preferences ↔ feed ↔ alerts ↔ snapshot），强行拆会引入难调试的 stale closure / 渲染顺序 bug。先做第 1 层把纯辅助挪走，剩下的再每个 session 拆一组相关 hook。
- ❌ **不要为了"看起来对称"而做无收益重命名**：保持原 helper / 常量名，让 diff 只反映"位置变化"而不是"位置 + 命名变化"。
- ❌ **不要在拆分 commit 里顺便修 bug 或加功能**：每个拆分 commit 应该是 _零行为变化_，行为变化要单独 commit。
- ❌ **不要跳过浏览器手动验证**：CRA / Jest / RTL 不能验证 `<Treemap>` / `<Tooltip>` / 主题切换 / 响应式断点等视觉问题。

## 验证 checklist

```bash
# 1. 目标组件的 jest 测试
CI=1 npm test -- --runInBand --watchAll=false --testPathPattern=<name>

# 2. 全套 jest 测试（保险）
CI=1 npm test -- --runInBand --watchAll=false

# 3. 打包构建（避免 import 路径错位）
npm run build

# 4. 浏览器人工验证
./scripts/start_system.sh
# 打开对应页面，过一遍主路径 + 边界态（错误、空数据、加载中）
```

后两步在每个 session 末必须做，不能省。

## 提交信息模板

```
refactor: extract <component> <theme> into shared modules

Pull <list of helpers/constants/sub-components> out of <ComponentName>.js
into <new-files>. The component shrinks from <X> to <Y> lines and the
extracted helpers become reusable for <future use>.

<Test status: which tests run, all green>.

See docs/superpowers/specs/<spec>.md.
```

## 进度跟踪表

每完成一个组件，回到这里记一笔（避免重复评估）：

| 组件 | 状态 | 行数变化 | 完成 commit | session 日期 |
|------|------|---------|------------|-------------|
| `IndustryHeatmap.js` | 第 2 层进行中（HeatmapLegend + HeatmapStatsBar 已抽出）| L1: 2014 → 1826 (−188) → 加 D2 1914 → L2: 1706 (−208) | L1 `c4cced1` / L2.1 `d67ea4b` / L2.2 (本批次) | 2026-05-03 → 2026-05-05 |
| `MarketAnalysis.js` | 第 1 层完成 | 2660 → 2566 (−94) | `2c13f3b` | 2026-05-04 |
| `CrossMarketBacktestPanel.js` | 第 1 层完成 | 2858 → 2727 (−131) | `8bb39a5` | 2026-05-04 |
| `RealTimePanel.js` | 第 1 层完成 | 3273 → 3066 (−207) | `afd8bac` | 2026-05-04 |

**Layer 1 全部完成；Layer 2 在 IndustryHeatmap 上开门**。HeatmapLegend 是第一个被拆出的 presentational 子组件（154 行，完全无 hooks，单测覆盖 6 个用例）。剩余 layer-2 候选：renderStats（约 100 行 useMemo 渲染统计 strip）、renderDesktopControls / renderMobileControls（约 300 行控制条，但属于 layer 3 状态密集区）。继续在 IndustryHeatmap 推进 layer 2 之前可以先重复同样模式给其他 mega-component，或 layer 3 单独立 session。
