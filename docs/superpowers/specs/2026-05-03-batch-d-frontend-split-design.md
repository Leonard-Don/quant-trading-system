# Batch D — Frontend Mega-Component Split (设计文档)

- 日期: 2026-05-03
- 范围: 4 个超大前端组件 + 1 个后端 adapter 的拆分
- 状态: 用户已确认全权决策

## 体量盘点

| 文件 | 行数 | hooks 数 | 顶层函数数 | 关联测试 |
|------|------|---------|-----------|---------|
| `frontend/src/components/RealTimePanel.js` | 3,273 | 79 | 24 | `realtime-panel.test.js` 等 5 个 |
| `frontend/src/components/CrossMarketBacktestPanel.js` | 2,858 | 46 | 31 | `cross-market-backtest-panel.test.js` 等 3 个 |
| `frontend/src/components/MarketAnalysis.js` | 2,660 | 37 | 20 | `market-analysis.test.js` |
| `frontend/src/components/IndustryHeatmap.js` | 2,014 | 37 | 24 | `industry-heatmap.test.js` |
| `src/data/providers/sina_ths_adapter.py` | 3,116 | — | — | `test_sina_ths_adapter.py` |
| **合计** | **~13,920** | | | |

## 单 session 不可行

每个文件单独拆分需要：

1. 阅读理解整文件（前端组件平均 hooks 50+ 个，状态机复杂）
2. 找到"清楚的接缝"（不是所有大文件都能干净切；有些跨 hook 状态依赖会让拆分变成大改动）
3. 抽取子组件 / 工具函数到独立文件
4. 调整 props / state 透传
5. 跑 Jest 单元测试 + Playwright E2E
6. 浏览器人工烟雾测试（视觉回归保护薄弱）

合理估时：每个 1–2 天的专注工作。在一次 session 里把 ~14k 行代码全部安全重构 = 不现实。

## 修订计划：试点 + 剧本

### D1（本期完成）：IndustryHeatmap 拆分作为试点

选 IndustryHeatmap 是因为：

- 体量最小（2,014 行）
- 已有清楚接缝：squarified treemap 纯算法（~150 行）+ 搜索/字符串归一化辅助（~30 行）+ 一组 tooltip / heatmap 颜色常量
- 测试覆盖好：`industry-heatmap.test.js` 跑过基线 3 个用例都绿

**目标产出**：

1. 新增 `frontend/src/utils/squarifiedTreemap.js` — 抽 `worstAspectRatio` / `squarify` / `layoutRow` 三个纯函数（~150 行）
2. 新增 `frontend/src/utils/industrySearch.js` — 抽 `normalizeIndustrySearchText` / `buildIndustrySearchCandidates` / `matchesIndustrySearch` / `syncHeatmapTileFocusState`（~30 行）
3. 新增 `frontend/src/utils/industryHeatmapTokens.js` — 抽 `HEATMAP_SURFACE` / `TOOLTIP_*` / `HEATMAP_*` / `TILE_TEXT_SHADOW` 等样式 token 与超时常量（~20 行）
4. `IndustryHeatmap.js` 改为从这三个文件导入，不重复实现

预期 IndustryHeatmap.js 从 2,014 → ~1,800 行。看似小，但接缝是真实的；同样的模式可以在其他三个组件里复制。

### D2（本期完成）：拆分剧本文档

新增 `docs/architecture/frontend-component-split-playbook.md`，记录：

- 找接缝的方法（先从纯函数 / 常量 / 通用 search/format 起）
- 抽取的步骤（先 utils → 再子组件 → 最后才动 hook 状态机）
- 验证 checklist（jest / 浏览器人工 / E2E）
- 不该做什么（不要为了"看起来 cleaner"重写 hook 关系；不要把跨多个 useState 的状态机硬塞进新组件）

### 推迟到后续 session 单独立项

- **D3**: `CrossMarketBacktestPanel.js` 拆分（独立 spec + plan）
- **D4**: `MarketAnalysis.js` 拆分
- **D5**: `RealTimePanel.js` 拆分（最大、最复杂，需要先阅读 79 个 hook 的状态依赖图）
- **E**: `sina_ths_adapter.py` 拆分（独立批次，Python adapter，与前端无关）

每个续作 session 走完整 brainstorm → spec → plan → implement → review。

## D1 执行步骤

1. 创建 `frontend/src/utils/squarifiedTreemap.js`，把 `worstAspectRatio` / `squarify` / `layoutRow` 原样搬过去（保留 JSDoc）。
2. 创建 `frontend/src/utils/industrySearch.js`，把 4 个 helper 搬过去；`syncHeatmapTileFocusState` 名字改成更通用的 `applyHeatmapTileFocus` 不要——保持原名以减少 diff 噪声。
3. 创建 `frontend/src/utils/industryHeatmapTokens.js`，把所有 `HEATMAP_*` / `TOOLTIP_*` / `TILE_TEXT_SHADOW` / `*_TIMEOUT_MS` 常量搬过去。
4. `IndustryHeatmap.js` 顶部新增 import，删掉本地定义。
5. 跑 `industry-heatmap.test.js`，要求全绿。
6. 跑 `npm run build`（如果时间允许），确保打包不破。

## 验证标准

| 编号 | 条件 |
|------|------|
| D1 | `industry-heatmap.test.js` 三个用例全绿；`IndustryHeatmap.js` 行数下降 ~200；新建 3 个 utils 文件能从外部 import |
| D2 | `docs/architecture/frontend-component-split-playbook.md` 存在并能指导 D3/D4/D5 |
| 总 | 不破坏前端测试套件（至少 industry / heatmap 相关绿） |

## 风险

- D1: 低。纯抽取，无逻辑改动。失败模式都会被 Jest 测试捕获。
- D2: 零（纯文档）。

## 实施顺序

D1 → D2，两个 commit（"refactor: extract industry heatmap utilities"、"docs: add frontend component split playbook"）。
