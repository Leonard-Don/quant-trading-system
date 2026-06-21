# Frontend Backtest Phase 2a (Plan 0h) — History / Comparison / Portfolio tabs

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Elevate three backtest sub-tabs (`PortfolioOptimizer`, `StrategyComparison`, `BacktestHistory`) onto `Panel`/`StatCard`, un-pin their directional colors (convert pinned antd `Statistic`/`Text` to plain spans), and align stray hardcoded directional hex to the green-up tokens. They are already green-up — no convention flip. Defer `AdvancedBacktestLab` (2b) and `CrossMarketBacktestPanel` (2c).

**Architecture:** Restyle + un-pin. antd `Card`→`Panel` (Panel now supports `style`/`testId` passthrough — use `style` for body-padding/border/margin nuances). antd `Statistic`/`Text type=success|danger`→ plain span / `StatCard` (escapes `.ant-statistic-content-value`/`.ant-typography` `!important`). Keep all logic/forms/tables/charts/testids.

**Tech Stack:** React 18, Ant Design 5 (kept for Form/Table/Select/charts), `src/design/` primitives, recharts, Vitest. `getValueColor` from `src/utils/formatting.js` → `var(--accent-success)` (green) for >0, `var(--accent-danger)` (red) for <0.

**Conventions:** Run from `frontend/`. Branch `feat/frontend-backtest-phase2`. Every commit ends with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT touch repo-root `scripts/start_system.sh`.

## DO-NOT-BREAK contract (from the test scout)
- **BacktestHistory** (tested REAL in `backtest-ui.test.js`): the table action-column download button MUST stay `<Button type="primary">` (test queries `container.querySelector('tbody button.ant-btn-primary')` — it's in the Table, not the Card, so Card→Panel is safe); the `allowClear` clear icon (`aria-label="clear"`) and the `EyeOutlined` detail button (`aria-label="eye"`) must stay; text strings `扩展诊断`/`交易明细`/`组合净值回放`/`平均盈利`/`买入`/`卖出`/`已全部平仓`/`实验摘要`/`总任务数`/`成功率`/`批量结果明细`/`12 条` preserved; batch records still suppress `组合净值回放`/`交易明细`.
- **StrategyComparison** (tested with FULL antd stub in `strategy-comparison.test.js`): keep `Select mode="multiple"` (`aria-label="strategy-select"`); `InputNumber` aria-labels/placeholders (`初始资金`/`手续费`/`滑点`/`移动平均策略-fast_period`/`-slow_period`); button text `开始对比` + `导出PDF报告`; `compareStrategies` decimal args; strategy names `买入持有`/`移动平均策略`; summary `2 个`.
- **PortfolioOptimizer**: stub-only in tests — no behavioral contract; just keep a default export.
- No test asserts color or any Card `data-testid`/`.ant-card` → un-pin/Card→Panel safe. Do NOT edit test files.

---

## Task 1: PortfolioOptimizer — Cards→Panel + Statistics→StatCard

**Files:** Modify `frontend/src/components/PortfolioOptimizer.jsx`. Import `{ Panel, MetricGrid, StatCard }` from `'../design/components'` and `getValueColor` from `'../utils/formatting'`.

- [ ] **Step 1: Implement**
  - Card 1 config bar (~145): `<Card className="workspace-panel" style={{marginBottom:24}}>` → `<Panel className="workspace-panel" style={{ marginBottom: 24 }}>`.
  - Card 2 metrics (~201): `<Card title="最优组合指标" variant="borderless" className="workspace-panel">` → `<Panel title="最优组合指标" className="workspace-panel">`. Inside, replace the `<Row gutter={[16,24]}>` of 3 `<Col span={24}><Statistic .../></Col>` with `<MetricGrid>` + 3 `<StatCard>`:
    - `<StatCard label="预期年化收益率" value={<span style={{ color: getValueColor(result.optimal_portfolio.return) }}>{formatted}%</span>} />` (was hardcoded green `#3f8600`; now conditional + un-pinned).
    - `<StatCard label="预期年化波动率" value={…} />` (non-directional — plain value).
    - `<StatCard label="夏普比率" value={…} />` (non-directional, or `getValueColor(sharpe)` if you want green/red).
  - Card 3 pie (~217) + Card 4 scatter (~258): `<Card title={…} variant="borderless" className="workspace-panel workspace-chart-card">` → `<Panel title={…} className="workspace-panel workspace-chart-card">`. (Drop `variant="borderless"`; if a borderless look matters, pass `style={{ border: 'none' }}`.)
  - Remove `Card`, `Statistic`, `Row`/`Col` from the antd import IF unused after (the metrics Row/Col is replaced; other Rows for selectors may remain — verify).
- [ ] **Step 2:** `npx vitest run src/__tests__/backtest-dashboard.test.js` → PASS (PortfolioOptimizer is stubbed there; this just confirms nothing else broke). Then `npm test` green; `npm run lint && npm run lint:css && npm run build` clean.
- [ ] **Step 3: Commit**
```bash
git add src/components/PortfolioOptimizer.jsx
git commit -m "feat(backtest): elevate PortfolioOptimizer onto Panel + StatCard (un-pin return color)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: StrategyComparison — Cards→Panel + un-pin Text colors

**Files:** Modify `frontend/src/components/StrategyComparison.jsx`. Import `{ Panel }` from `'../design/components'` and `getValueColor` from `'../utils/formatting'`.

- [ ] **Step 1: Implement**
  - Convert all 8 antd `<Card className="workspace-panel…">` to `<Panel …>` (map any `title`→`title`, `extra`→`actions`, preserve classNames + the `style={{marginBottom:…}}` via Panel `style`):
    - Card 1 config bar (~392), Card 2 param wrapper (~181, title `策略参数版本`), Card 3 per-strategy inner (~188, `size="small"`, dynamic title — keep `workspace-panel--subtle` class), Card 4 ranking (~503, title with TrophyOutlined), Card 5 results table (~555, `对比结果概览`), Card 6 radar (~567), Card 7 bar (~609), Card 8 sharpe bar (~637). Keep all chart/Table/Row/Col bodies + the bespoke rank divs (gold border for rank 1) unchanged.
  - Un-pin directional colors: line ~280 `<Text type={value >= 0 ? 'success' : 'danger'}>{…}</Text>` (table 总收益率) → plain `<span style={{ color: getValueColor(value) }}>{…}</span>`. Line ~298 `<Text type="danger">` (最大回撤, always red) → plain `<span style={{ color: 'var(--accent-danger)' }}>{…}</span>`.
  - Optional alignment: line ~626 recharts `<Cell fill={parseFloat(...) >= 0 ? '#00f5d4' : '#ff6b6b'}>` → `>= 0 ? '#22c55e' : '#ef4444'` (align the teal to the green used elsewhere); line ~629 drawdown bar keep red.
  - Remove `Card` from the antd import if unused; keep `Text` if still used elsewhere (it likely is).
- [ ] **Step 2:** `npx vitest run src/__tests__/strategy-comparison.test.js` → PASS. Then `npm test` green; `npm run lint && npm run lint:css && npm run build` clean.
- [ ] **Step 3: Commit**
```bash
git add src/components/StrategyComparison.jsx
git commit -m "feat(backtest): elevate StrategyComparison onto Panel + un-pin return colors" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: BacktestHistory — outer Card→Panel + color-var alignment

**Files:** Modify `frontend/src/components/BacktestHistory.jsx`. Import `{ Panel }` from `'../design/components'` and `getValueColor` from `'../utils/formatting'`.

- [ ] **Step 1: Implement**
  - Outer Card (~832): `<Card className="workspace-panel" title={…} extra={<Space className="workspace-toolbar">…</Space>} style={{marginTop:16}} styles={{body:{padding:0}}}>` → `<Panel className="workspace-panel" title={…} actions={<Space className="workspace-toolbar">…</Space>} style={{ marginTop: 16, padding: 0 }}>` (fold the body-padding:0 into Panel `style`; if the header/toolbar looks too flush against the edge, instead use Panel default padding and wrap the table in a `-mx`-free container — prefer `style={{ padding: 0 }}` first and visually confirm). KEEP the Table + the `tbody` primary download Button + the AutoComplete/Select allowClear + the EyeOutlined detail button untouched.
  - Color alignment: line ~482 table cell `<span style={{ color: val >= 0 ? 'green' : 'red' }}>` → `<span style={{ color: getValueColor(val) }}>`. The `CHART_POSITIVE`/`CHART_NEGATIVE` consts (~58–59, `#22c55e`/`#ef4444`) already green-up — leave (recharts hex is fine; optional to var-ize, skip to avoid getComputedStyle complexity). Line ~703 P&L already uses getValueColor — leave.
  - Remove `Card` from antd import if unused.
- [ ] **Step 2:** `npx vitest run src/__tests__/backtest-ui.test.js` → PASS (real-antd render; the `tbody button.ant-btn-primary` + `eye`/`clear` aria-labels must still resolve). Then `npm test` green; `npm run lint && npm run lint:css && npm run build` clean.
- [ ] **Step 3: Commit**
```bash
git add src/components/BacktestHistory.jsx
git commit -m "feat(backtest): elevate BacktestHistory onto Panel + token return color" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Final verification
- [ ] **Step 1:** `npm test` green; `npm run lint && npm run lint:css && npm run build` clean; `grep -nE "(text|tracking|max-w|basis|col-span)-\[|'green'|'red'" src/components/PortfolioOptimizer.jsx src/components/StrategyComparison.jsx src/components/BacktestHistory.jsx` → no arbitrary classes / no leftover named-color directional spans (BUY/SELL/status Tag `color="green"/"red"` are non-directional labels and may remain).
- [ ] **Step 2 (controller, if dev server up):** spot-check the 回测历史 / 策略对比 / 组合优化 tabs render as elevated Panels with green/red directional values. (Servers may be down — rely on tests + review if so.)
- [ ] **Step 3:** fix any issue under the relevant task.

## Deferred (backtest Phase 2b / 2c)
- 2b: `AdvancedBacktestLab` + `advanced-backtest/*` (7 sections).
- 2c: `CrossMarketBacktestPanel` + `cross-market/*` (6 subcomponents, ~3100 lines).

## Self-Review (plan author)
- Coverage: 3 tabs Card→Panel (Portfolio 4 / Comparison 8 / History 1); pinned directional colors un-pinned (Portfolio return Statistic→StatCard, Comparison 总收益率/回撤 Text→span); stray hex aligned. AdvancedLab + CrossMarket deferred. ✓
- Contracts: BacktestHistory `tbody button.ant-btn-primary` + clear/eye aria + text preserved (Table untouched); StrategyComparison stub-mock contracts (selects/inputs/buttons/aria) preserved; PortfolioOptimizer stub-only. No test asserts color/Card class. ✓
- Consistency: un-pin via plain span / StatCard + `getValueColor`/token vars (proven pattern); Panel `style` for body-padding/border/margin nuances; no arbitrary `[..]`/`col-span-N`.
