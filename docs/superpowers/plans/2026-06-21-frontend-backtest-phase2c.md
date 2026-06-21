# Frontend Backtest Phase 2c (Plan 0j) — Cross-Market tab (the last tab)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (controller parallelizes edit-only subagents across disjoint files, then aggregates). Steps use checkbox (`- [ ]`).

**Goal:** Elevate the cross-market backtest tab — convert all 34 antd `Card`s across `CrossMarketBacktestPanel` + the 6 `cross-market/*` subcomponents to `Panel`, un-pin the one directional `Statistic`, and make one always-green bar conditional. Already green-up — no convention flip. This is the LAST backtest tab; after it the whole frontend overhaul is complete.

**Architecture:** antd `Card`→`Panel` (Panel supports `title`/`actions`/`testId`/`style`/`className`; for `variant="borderless"` Cards, just drop the prop — Panel is the design surface). Keep all logic/forms/tables/charts/Selects/Statistics (except the one un-pin). Import `{ Panel }` from `'../design/components'` (panel) / `'../../design/components'` (subcomponents).

**Parallelization:** the 7 files are disjoint → the controller dispatches ~5 edit-only subagents concurrently (one per file/group), each edits its file and does NOT commit/build/run-full-suite. The controller then runs the full verification + commits once.

**Conventions:** Run from `frontend/`. Branch `feat/frontend-backtest-phase2c`. Commits end with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT touch repo-root `scripts/start_system.sh`. No arbitrary `[..]`/`md:col-span-N` classes. Watch smart-quote insertion in JSX attrs.

## DO-NOT-BREAK contract (from the test scout)
- `cross-market-asset-section.test.js` (REAL antd) asserts `container.querySelectorAll('.ant-select-selector').length === 2` → `CrossMarketAssetSection` MUST keep its 2 antd `Select`s; also keep `多头篮子` title text, the `资产代码` placeholder inputs, the `新增`/`删除` buttons + their `onAdd`/`onUpdate`/`onRemove` callbacks. (Card→Panel doesn't touch any of these.)
- `cross-market-backtest-panel.test.js` (partial antd stub — Row/Col→div, Table→`mock-table`, rest real) asserts lots of TEXT (template-governance overlays `来源 回退来源偏高`/`政策执行 混乱`/`核心腿：…`, asset values `XLU`/`QQQ`, button `运行回测`, post-backtest `执行姿态：…`/`政策执行：…`/`来源治理：…`) — all preserved by Card→Panel. KEEP the `Table` renders (the `mock-table` stub). KEEP the `CrossMarketDiagnosticsSection`/`CrossMarketBasketSummaryCard` default exports.
- `cross-market-utils.test.js` + `cross-market-recommendations.test.js` pin util return values incl. NAMED COLOR STRINGS (`buildDisplayTone`→'volcano'/'gold'/'blue', `getConcentrationMeta`→'red'/'green', etc.) in `utils/crossMarketMeta.js`/`crossMarketFormatters.js`/`crossMarketRecommendations.js` — DO NOT TOUCH those util files.
- No test asserts `.ant-card`/`.ant-statistic-content-value` or any color on the components → Card→Panel + the un-pin are safe. Do NOT edit any test file.

## Card sites (all convert to Panel; map title→title, extra→actions, preserve className, drop `variant="borderless"`)
- CrossMarketBacktestPanel.jsx: 3 — context-rail@1137 (`app-page-context-rail`, no title), preview@1195 (`workspace-panel cross-market-preview-card`, no title), spinner@1270 (`workspace-panel`, no title).
- CrossMarketAssetSection.jsx: 1 — @23 (`title={title}` dynamic, `extra={<Button>新增</Button>}`, `cross-market-asset-card`). KEEP the inner antd Selects.
- CrossMarketBasketSummaryCard.jsx: 1 — @15 (`title="资产篮子摘要"`, no className).
- CrossMarketControlSidebar.jsx: 3 — @52 (`cross-market-sidebar-card--overview`, no title), @73 (`title="模板快选"`), @122 (`title="参数与模板"`).
- CrossMarketDiagnosticsSection.jsx: 2 — @25 (`title="数据对齐诊断"`), @82 (`title="执行诊断"`). LEAVE its ~18 antd `Statistic`s as-is (non-directional diagnostic numbers, no color pin).
- CrossMarketTemplateInsights.jsx: 2 (read to confirm exact lines/props).
- CrossMarketResultsView.jsx: 22 (read to confirm each; preserve title/extra/className). LEAVE the 12 `Statistic`s EXCEPT the one un-pin below.

## Directional fixes (CrossMarketResultsView.jsx)
- ~line 139: `<Statistic title="总收益率" value=… valueStyle={{ color: getValueColor(results.total_return) }} …>` — color is `.ant-statistic-content-value !important`-pinned (invisible). Replace this ONE Statistic with plain markup so the green/red shows: keep the title label, render the value as a plain `<span style={{ color: getValueColor(results.total_return) }}>{same formatted value + suffix}</span>` (e.g. inside a small label+value block, or a `StatCard`). The other Statistics nearby (sharpe/drawdown/etc.) have NO directional valueStyle color → leave them as antd Statistic.
- ~line 505: `<Bar … fill="#52c41a">` (长短腿累计收益, all bars flat green regardless of sign) → conditional per-point `<Cell>`: import `Cell` from recharts, `<Bar dataKey=…>{theBarData.map((d,i) => <Cell key={i} fill={(d.<thatDataKey> ?? 0) >= 0 ? '#22c55e' : '#ef4444'} />)}</Bar>` (use the same data array + dataKey the Bar uses).

---

## Task 1 (controller, parallel): Card→Panel across all 7 files + the 2 fixes
Dispatch ~5 concurrent edit-only subagents (no commit/build/full-suite), grouped by disjoint file:
- A: `CrossMarketResultsView.jsx` (22 Cards→Panel + un-pin :139 + conditional :505 bar).
- B: `CrossMarketBacktestPanel.jsx` (3 Cards→Panel).
- C: `CrossMarketControlSidebar.jsx` (3 Cards→Panel).
- D: `CrossMarketDiagnosticsSection.jsx` (2 Cards→Panel) + `CrossMarketTemplateInsights.jsx` (2 Cards→Panel).
- E: `CrossMarketAssetSection.jsx` (1 Card→Panel, keep Selects) + `CrossMarketBasketSummaryCard.jsx` (1 Card→Panel).
Each: import Panel from the right relative path; remove `Card` from antd import if unused; preserve all data-testids/text/Selects/Tables/Statistics (except the one un-pin).

- [ ] **Controller aggregate-verify (after all subagents return):**
  1. `grep -rnE "<Card" src/components/CrossMarketBacktestPanel.jsx src/components/cross-market/` → no matches (all 34 converted).
  2. `npx vitest run src/__tests__/cross-market-backtest-panel.test.js src/__tests__/cross-market-asset-section.test.js src/__tests__/cross-market-utils.test.js src/__tests__/cross-market-recommendations.test.js src/__tests__/backtest-dashboard.test.js` → PASS.
  3. `npm test` → FULL suite green; `npm run lint && npm run lint:css && npm run build` → clean; `grep -rnE "(text|tracking|max-w|basis|col-span)-\[" src/components/cross-market/ src/components/CrossMarketBacktestPanel.jsx` → no arbitrary classes.
- [ ] **Commit** (one commit; if a subagent broke something, dispatch a targeted fix first):
```bash
git add src/components/CrossMarketBacktestPanel.jsx src/components/cross-market/
git commit -m "feat(backtest): elevate cross-market tab onto Panel + un-pin total_return + conditional bar" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

## Self-Review (plan author)
- Coverage: all 34 Cards→Panel; the 1 pinned directional Statistic un-pinned; the 1 always-green bar made conditional. Util files (recommendations/meta/formatters) untouched (their color strings are test-pinned + non-directional). ✓
- Contracts: AssetSection Selects (`.ant-select-selector` x2) kept; panel test text + Table stubs preserved; Diagnostics/BasketSummary default exports kept; no test asserts Card/color. ✓
- Consistency: Panel for shells; already green-up; un-pin via plain span; conditional Cell matches the existing pattern; no arbitrary classes. After this, the frontend overhaul is COMPLETE.
