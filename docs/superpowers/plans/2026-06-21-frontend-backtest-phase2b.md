# Frontend Backtest Phase 2b (Plan 0i) — Advanced Lab sections

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Elevate the 7 `advanced-backtest/*` section components onto `Panel` (convert their 10 antd Cards), and fix 2 "always-green" recharts bars to conditional green/red. Already green-up — no convention flip. `AdvancedBacktestLab.jsx` itself has no Cards (bespoke summary-strip layout) — leave it.

**Test safety:** The two `advanced-*` tests (`advanced-backtest-lab.test.js`, `advanced-experiment-templates.test.js`) are PURE UTIL tests (zero rendering, zero antd, zero color assertions). The only test that renders `AdvancedBacktestLab` is `backtest-dashboard.test.js`, which STUBS it. So Card→Panel + color changes in these 7 components break NOTHING. KPIs are already plain `summary-strip` divs (no antd Statistic pins) — leave them.

**Architecture:** antd `Card`→`Panel` (`Panel` supports `title`/`actions`/`testId`/`style`/`className`). Keep all logic/forms/tables/charts. Import `{ Panel }` from `'../../design/components'` (these files are in `components/advanced-backtest/`).

**Conventions:** Run from `frontend/`. Branch `feat/frontend-backtest-phase2b`. Every commit ends with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT touch repo-root `scripts/start_system.sh`. No arbitrary `[..]`/`md:col-span-N` classes. Watch smart-quote insertion in JSX attrs.

## Card sites (all `<Card className="workspace-panel…">`)
- BatchBacktestSection.jsx:112 (form, composite JSX title), :261 (results, `title={batchExperimentMeta.title}` + `extra={<Space>…3 Buttons…</Space>}`)
- BenchmarkSection.jsx:27 (`title="基准对照"`)
- PortfolioSection.jsx:29 (`title="组合级策略回测"`)
- ResearchInsightsSection.jsx:30 (`title="稳健性评分"`), :108 (`title="市场状态分层回测"`)
- ResearchToolsPanel.jsx:24 (compound `className`, NO title — header is a `.workspace-section__header` div in body)
- TemplateManagerSection.jsx:35 (compound `className`, NO title — header in body)
- WalkForwardSection.jsx:108, :283

Mapping: `title`→`title`, `extra`→`actions`, preserve the (possibly compound/template-literal) `className`. For no-title Cards, just `<Panel className=…>` (keep the in-body header div).

---

## Task 1: Batch + Benchmark + Portfolio sections

**Files:** `BatchBacktestSection.jsx`, `BenchmarkSection.jsx`, `PortfolioSection.jsx`.

- [ ] **Step 1: Implement**
  - `BatchBacktestSection.jsx`: Card@112 → `<Panel className="workspace-panel" title={…composite JSX…}>`; Card@261 → `<Panel className="workspace-panel workspace-chart-card" title={batchExperimentMeta.title} actions={batchResult ? <Space>…</Space> : null}>`. Keep Form/Row/Col/BarChart/Table + the summary-strip divs.
  - `BenchmarkSection.jsx`: Card@27 → `<Panel className="workspace-panel workspace-chart-card" title="基准对照">`. **Bar fix @57**: the `<Bar dataKey="totalReturn" name="总收益率" fill={CHART_POSITIVE} />` is always green; make it conditional per data point — `<Bar dataKey="totalReturn" name="总收益率">{<chartData>.map((d, i) => <Cell key={i} fill={(d.totalReturn ?? 0) >= 0 ? CHART_POSITIVE : CHART_NEGATIVE} />)}</Bar>` (import `Cell` from recharts; use the same data array the BarChart is fed). Keep the drawdown bar (`CHART_NEGATIVE`) as-is.
  - `PortfolioSection.jsx`: Card@29 → `<Panel className="workspace-panel workspace-chart-card" title="组合级策略回测">`. Keep the 2 summary-strip KPI grids + Row/Col charts + 2 Tables. (The NAV/exposure line colors are non-directional series identities — leave.)
  - Remove `Card` from each file's antd import if unused.
- [ ] **Step 2:** `npx vitest run src/__tests__/advanced-backtest-lab.test.js src/__tests__/backtest-dashboard.test.js` → PASS. Then `npm test` green; `npm run lint && npm run lint:css && npm run build` clean.
- [ ] **Step 3: Commit**
```bash
git add src/components/advanced-backtest/BatchBacktestSection.jsx src/components/advanced-backtest/BenchmarkSection.jsx src/components/advanced-backtest/PortfolioSection.jsx
git commit -m "feat(backtest): Card→Panel for batch/benchmark/portfolio sections + conditional bar color" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: ResearchInsights + ResearchTools + TemplateManager + WalkForward sections

**Files:** `ResearchInsightsSection.jsx`, `ResearchToolsPanel.jsx`, `TemplateManagerSection.jsx`, `WalkForwardSection.jsx`.

- [ ] **Step 1: Implement**
  - `ResearchInsightsSection.jsx`: Card@30 → `<Panel className="workspace-panel workspace-chart-card" title="稳健性评分">`; Card@108 → `<Panel className="workspace-panel workspace-chart-card" title="市场状态分层回测">`. **Bar fix @143**: `<Bar dataKey="strategyTotalReturn" name="策略收益" fill={CHART_POSITIVE} />` → conditional per-point `<Cell>` (green if `>= 0`, else `CHART_NEGATIVE`; import `Cell`). Keep the market-return bar (`CHART_NEUTRAL`) as-is. Keep summary-strips + Tables.
  - `ResearchToolsPanel.jsx`: Card@24 → `<Panel className={`workspace-panel advanced-lab-tool-panel${compact ? ' advanced-lab-tool-panel--compact' : ''}`}>` (no title — keep the in-body `.workspace-section__header` div). Keep Row/Col inputs.
  - `TemplateManagerSection.jsx`: Card@35 → `<Panel className={`workspace-panel advanced-lab-control-card${compact ? ' advanced-lab-control-card--compact' : ''}`}>` (no title — keep in-body header). Keep body.
  - `WalkForwardSection.jsx`: Card@108 and Card@283 → `<Panel …>` (preserve their className/title/extra→actions; read to confirm). Keep Form/charts/Table + the line colors (return=green, drawdown=red, sharpe=neutral — all fine).
  - Remove `Card` from each file's antd import if unused.
- [ ] **Step 2:** `npx vitest run src/__tests__/advanced-backtest-lab.test.js src/__tests__/advanced-experiment-templates.test.js src/__tests__/backtest-dashboard.test.js` → PASS. Then `npm test` green; `npm run lint && npm run lint:css && npm run build` clean.
- [ ] **Step 3: Commit**
```bash
git add src/components/advanced-backtest/ResearchInsightsSection.jsx src/components/advanced-backtest/ResearchToolsPanel.jsx src/components/advanced-backtest/TemplateManagerSection.jsx src/components/advanced-backtest/WalkForwardSection.jsx
git commit -m "feat(backtest): Card→Panel for insights/tools/template/walkforward sections + conditional bar color" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Final verification
- [ ] **Step 1:** `npm test` green; `npm run lint && npm run lint:css && npm run build` clean; `grep -rnE "<Card" src/components/advanced-backtest/` → no matches (all converted); `grep -rnE "(text|tracking|max-w|basis|col-span)-\[" src/components/advanced-backtest/` → no arbitrary classes.
- [ ] **Step 2 (controller, if dev server up):** spot-check the 高级实验 tab's sub-panels render as elevated Panels.

## Deferred (backtest Phase 2c)
- `CrossMarketBacktestPanel` + `cross-market/*` (~3100 lines, the last/biggest tab).

## Self-Review (plan author)
- Coverage: all 10 Cards in the 7 sections → Panel (Task 1: 4, Task 2: 6); 2 always-green bars → conditional. AdvancedBacktestLab bespoke layout left; CrossMarket deferred to 2c. ✓
- Contracts: the 2 advanced tests are util-only (no rendering); backtest-dashboard stubs the lab → all component changes safe. KPIs stay as summary-strip divs. ✓
- Consistency: Panel for shells; already green-up (no flip); conditional Cell pattern matches BatchBacktestSection's existing one; no arbitrary classes.
