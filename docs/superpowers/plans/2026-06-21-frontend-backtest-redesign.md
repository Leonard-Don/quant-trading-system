# Frontend Backtest Workspace Redesign — Phase 1 (Plan 0g) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Elevate the CORE backtest flow's result metrics + panel shells onto the design-system primitives, and fix the bug where result-metric colors are silently killed by a global `!important` rule (so 总收益率/夏普/回撤 render monochrome today). Backtest is already green-up — NO directional convention flip is needed.

**Scope (Phase 1):** `ResultsDisplay` metric cards → `StatCard` (un-pins the color) + the panel shells (`StrategyForm` Card, `ResultsDisplay` Card, dashboard empty-state Card, `ResultsDisplay` trades inner Card) → `Panel`. DEFERRED to later phases (noted at bottom): the other 5 tabs — `BacktestHistory`, `StrategyComparison`, `PortfolioOptimizer`, `AdvancedBacktestLab`, `CrossMarketBacktestPanel`.

**Architecture:** Restyle + un-pin colors. Keep all logic/handlers/Form/Table/Tabs. The metric `<Statistic valueStyle={{color}}>`s are overridden by `index.css` `.ant-statistic-content-value { color: var(--text-primary) !important }`, so their directional color never shows — converting them to `StatCard` (plain spans) makes the color render.

**Tech Stack:** React 18, Ant Design 5 (kept for Form/Table/Tabs), `src/design/` primitives, Tailwind v4, recharts (charts unchanged), Vitest.

**Conventions:** Run from `frontend/`. Branch `feat/frontend-backtest-redesign`. Every commit ends with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT touch repo-root `scripts/start_system.sh`.

## DO-NOT-BREAK contract (backtest-ui.test.js renders REAL antd for ResultsDisplay; charts stubbed; NO test asserts color)
- `ResultsDisplay`: keep the metric TITLE text (`最终价值`, `总收益率`, `年化收益率`, `最大回撤`, `夏普比率`, `平均盈利`, `平均亏损`, `累计盈利`, `索提诺比率`, `平均单笔收益`, etc.) and the formatted VALUE text (`$11,000.00`, etc.) — the test queries these by text. Keep the result Tabs (`role="tab"` `交易记录`/overview/charts/analysis), the toolbar buttons (`查看历史记录`/`继续做高级实验`/`分析市场状态`/`保存快照`/`打开历史`), the snapshot textarea placeholder, the trades table + its P&L span (already a plain green-up span — leave). Keep the no-trade diagnostics text.
- `BacktestDashboard`: keep the 6 tabs (`role="button"`/`role="tab"` names new/history/comparison/portfolio/cross-market/advanced) + URL `tab=` sync; keep `StrategyForm`/`ResultsDisplay` render.
- `BacktestDataHealthPanel` (real antd in its test) is OUT of Phase 1 scope (already all plain divs) — don't touch unless needed.
- The ONE antd-internal selector `tbody button.ant-btn-primary` is in `BacktestHistory` (a DEFERRED tab) — not touched here.
- No test asserts color → the metric color un-pin is safe. Do NOT edit any test file.

---

## Task 1: Convert ResultsDisplay metric cards to StatCard (un-pin the directional colors)

**Files:** Modify `frontend/src/components/ResultsDisplay.jsx`.

Context: `primaryMetrics` (5: 总收益率/年化收益率/最大回撤/夏普比率/最终价值, defined ~lines 254–300, rendered ~681–697) and `secondaryMetrics`/extended (7: 索提诺/平均单笔收益/VaR + 平均盈利/平均亏损/平均持仓/累计盈利, defined ~lines 310–380, rendered ~728–742) are each rendered as `<Card className="metric-card workspace-kpi-card" size="small"><Statistic title value precision suffix formatter valueStyle={{ color: metric.color, fontSize }} prefix={icon} /></Card>`. The `valueStyle.color` is killed by the global `.ant-statistic-content-value !important` rule, so the metrics show as monochrome `--text-primary`.

- [ ] **Step 1: Implement**
  - Import `{ MetricGrid, StatCard }` from `'../design/components'`.
  - Fix the `total_profit` (累计盈利) metric color bug (~line 338): it hardcodes `var(--accent-success)`; change to `getValueColor(total_profit)` so a losing strategy shows red. (Keep 最大回撤 always-`var(--accent-danger)`, 平均盈利 always-success, 平均亏损 always-danger — those are semantically fixed.)
  - Replace the primary KPI render (the `results-primary-kpi-grid` mapping of `<Card><Statistic/></Card>`) with `<MetricGrid className="results-primary-kpi-grid">` containing one `<StatCard>` per metric:
    `<StatCard key={metric.key} label={metric.title} value={<span style={{ color: metric.color }}>{displayValue}</span>} />`
    where `displayValue = metric.formatter ? metric.formatter(metric.value) : (metric.precision != null ? Number(metric.value).toFixed(metric.precision) : metric.value)` then append `metric.suffix || ''`. (Reproduce exactly what `<Statistic>` displayed so the test's value-text assertions still pass.) The metric `prefix` icon may be dropped or placed before the value — keep it simple; do NOT let it change the asserted text.
  - Replace the secondary KPI render (`results-secondary-kpi-grid` mapping) the same way with a second `<MetricGrid>` of `StatCard`s.
  - Remove the now-unused `Statistic` import if nothing else in the file uses it (the diagnostic panel uses plain `summary-strip__item` divs, not Statistic — verify). Keep `Card` import (still used for the outer card / trades card until Task 2).
  - Use the existing grid container classnames on MetricGrid via `className=` so layout stays close; do NOT introduce arbitrary `[..]`/`col-span-N` classes.

- [ ] **Step 2: Run the backtest UI test**

Run: `npx vitest run src/__tests__/backtest-ui.test.js`
Expected: PASS (metric titles + formatted values still render as text). If a value-text assertion fails, your `displayValue` formatting doesn't match the old `<Statistic>` output — align it (do NOT edit the test).

- [ ] **Step 3: Full suite + build, then commit**

Run: `npm test` (green), `npm run lint && npm run lint:css && npm run build` (clean), and `grep -nE "(text|tracking|max-w|basis|col-span)-\[" src/components/ResultsDisplay.jsx` → no matches.
```bash
git add src/components/ResultsDisplay.jsx
git commit -m "feat(backtest): result metrics on StatCard (un-pin green-up colors) + fix total_profit color" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Elevate the backtest panel shells onto Panel

**Files:** `frontend/src/components/StrategyForm.jsx`, `frontend/src/components/ResultsDisplay.jsx`, `frontend/src/components/BacktestDashboard.jsx`.

- [ ] **Step 1: Implement**
  - `StrategyForm.jsx` (outer Card ~line 527): `<Card className="workspace-panel workspace-panel--form" title={<div className="workspace-title">…</div>} extra={<Tag…/>} styles={{body:{padding:'24px'}}}>` → `<Panel title={<div className="workspace-title">…</div>} actions={<Tag…/>}>`. Keep the Form + summary-strip + all children. (Drop the `workspace-panel--form` bespoke shell in favor of Panel's surface; if a specific spacing is needed, use Tailwind padding on the Panel via `className`.) Import `{ Panel }` from `'../design/components'`.
  - `ResultsDisplay.jsx` (outer Card ~line 1049): `<Card className="workspace-panel workspace-panel--result" title={…} extra={<Space className="workspace-toolbar">…</Space>} size="small">` → `<Panel title={…} actions={<Space className="workspace-toolbar">…</Space>}>`. Keep the summary-strip + lead-grid + Tabs. Also the trades inner Card (~line 1029) `<Card className="workspace-chart-card" size="small" title="成交明细">` → `<Panel title="成交明细" className="workspace-chart-card">` (keep the Table).
  - `BacktestDashboard.jsx` (empty-state Card ~lines 200–254): `<Card className="workspace-panel workspace-panel--result backtest-main-stage__empty-card">…</Card>` → `<Panel className="backtest-main-stage__empty-card">…</Panel>`. Keep the empty-state content.
  - Remove `Card` from each file's antd import if it becomes unused (check — ResultsDisplay may still use Card elsewhere; if so keep). No arbitrary `[..]`/`col-span-N` classes; no new hardcoded hex.

- [ ] **Step 2:** `npx vitest run src/__tests__/backtest-ui.test.js src/__tests__/backtest-dashboard.test.js` → PASS.
- [ ] **Step 3:** `npm test` green; `npm run lint && npm run lint:css && npm run build` clean. Commit:
```bash
git add src/components/StrategyForm.jsx src/components/ResultsDisplay.jsx src/components/BacktestDashboard.jsx
git commit -m "feat(backtest): elevate strategy-form/results/empty-state panels onto Panel" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Final verification + visual check
- [ ] **Step 1:** `npm test` green; `npm run lint && npm run lint:css && npm run build` clean.
- [ ] **Step 2 (controller):** load `http://localhost:3000` (the default backtest view) in DEV (dark + light). Run a backtest (or rely on existing results) and confirm: the result KPI metrics now render with GREEN (positive) / RED (negative) color (no longer monochrome); the StrategyForm + ResultsDisplay + empty-state are elevated Panels. Confirm the metric VALUES read the same numbers as before.
- [ ] **Step 3:** fix any issue under the relevant task.

## Deferred to later phases (backtest Phase 2+)
- `BacktestHistory` (1173 lines, has the `tbody button.ant-btn-primary` test selector), `StrategyComparison`, `PortfolioOptimizer`, `AdvancedBacktestLab` (+ advanced-backtest/*), `CrossMarketBacktestPanel` (1305 + cross-market/*) — each its own Card→Panel + StatCard pass. All already green-up (no flip).
- BUY/SELL signal colors (PerformanceChart triangles, trade-table tag) are western (BUY=green) — left as-is (order side, not 涨跌; consistent with the western convention choice).

## Self-Review (plan author)
- Coverage: metric color un-pin via StatCard + total_profit bug (Task 1 — the clear visible win); panel shells → Panel (Task 2). Other 5 tabs deferred. No directional flip needed (already green-up). ✓
- Contracts: keeps metric title + value text (test queries them), result Tabs/toolbar/snapshot, dashboard tabs + URL sync; charts stubbed in the test so untouched; no color assertions → un-pin safe; no test edited. ✓
- Consistency: StatCard with colored value-node (the proven un-pin pattern from paper/cluster); Panel for shells (drop bespoke workspace-panel shell in favor of consistent Panel surface); no arbitrary `[..]`/`col-span-N`.
