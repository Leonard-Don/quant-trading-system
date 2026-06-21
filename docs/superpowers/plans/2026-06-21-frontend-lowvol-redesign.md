# Frontend Low-Volatility Workspace Redesign (Plan 0c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Elevate the `lowvol` (低波动) workspace onto the design-system primitives, adopt the green-up / red-down market color convention (user decision), and drop hardcoded colors — without breaking the existing Vitest specs.

**Architecture:** Restyle, not rewrite. Keep all logic/state/handlers/data. Wrap each panel in the `Panel` primitive; convert the portfolio's antd `Statistic` row to `MetricGrid`/`StatCard`; theme the recharts equity curve via CSS-var strokes; flip the screen's return color to green-up via token utilities. CRITICAL: both test files fully `vi.mock('antd', ...)` and `vi.mock('recharts', ...)`, so the mocked antd `Table`/`Alert`/`Button` provide the test hooks — those antd components MUST stay.

**Tech Stack:** React 18, Ant Design 5 (kept for Table/Alert/Button/Select/InputNumber/Tabs), the `src/design/` primitives, Tailwind v4, recharts, Vitest.

**Conventions:** Run from `frontend/`. Branch `feat/frontend-lowvol-redesign`. Every commit ends with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT touch repo-root `scripts/start_system.sh`.

---

## DO-NOT-BREAK contract (from the two test files, which mock antd + recharts)

`low-volatility-screen.test.jsx`:
- Rows come from the MOCKED antd `Table` → keep using antd `Table` (it yields `data-testid="lowvol-row"`). 3 rows, ascending vol order, with symbol + name text.
- A button with accessible name `查询` (mocked antd `Button`).
- `role="alert"` disclaimer (mocked antd `Alert`) whose combined text contains `样本外验证`, `lowvol-confirmation.md`, `非投资建议`.
- `getLowVolatilityScreen` called once on mount, again on 查询 click; `message.error(detail)` on failure.

`low-vol-portfolio-panel.test.jsx`:
- A button with accessible name `运行回测` (mocked antd `Button`); `getLowVolatilityPortfolio` NOT called on mount, called once on click.
- Metric rows from the MOCKED antd `Table` → keep antd `Table` (yields `data-testid="metric-row"`). 3 rows: `低波动篮子(净)` … `等权基准`, text includes Sharpe `0.44` and `0.22`.
- `role="alert"` disclaimer containing `非投资建议` / `样本外验证`.
- `message.error(detail)` on failure.

Anything NOT asserted (the `Statistic` row, recharts internals, Card/Panel wrapper, colors) is free to change. Keep antd `Alert`/`Button`/`Table`/`Select`/`InputNumber`. Do NOT edit the test files.

---

## Color convention (user decision: 绿涨红跌 / Western green-up)
- Screen `recent_return` cell: positive → green, negative → red. Current code is the A-share inverse (`>=0 ? '#cf1322'(red) : '#3f8600'(green)`) — FLIP it, and express via token utility classes `text-up` (green) / `text-down` (red) instead of hex.
- Portfolio equity-curve lines are SERIES (not direction): use neutral token CSS-var strokes — net basket `var(--color-accent)`, gross `var(--color-warn)`, benchmark `var(--color-muted)` — replacing `#cf1322`/`#fa8c16`/`#8c8c8c`. (`var(--color-*)` resolves in SVG stroke and is theme-reactive; the recharts mock ignores it in tests.)
- No remaining hardcoded design hex in these two files (the inline `#8c8c8c` loading-text colors → `text-muted`/`text-subtle`).

---

## File Structure
| Path | Change |
|---|---|
| `src/components/LowVolatilityScreen.jsx` | Task 1 — Panel wrapper, green-up return color, token spacing/colors, optional FadeIn |
| `src/components/LowVolPortfolioPanel.jsx` | Task 2 — Panel wrapper, MetricGrid/StatCard stat row, token chart strokes, token colors |

`LowVolatilityView.jsx` (the antd `Tabs` shell) stays as-is. No test files change.

---

## Task 1: Elevate LowVolatilityScreen

**Files:** Modify `frontend/src/components/LowVolatilityScreen.jsx`

- [ ] **Step 1: Implement**
  - Import `Panel` from `'../design/components'` (and `FadeIn` from `'../design/motion'` if wrapping). Remove `Card` from the antd import; KEEP `Select, InputNumber, Button, Table, Alert, Space, Typography, Tag, Empty, Spin` from antd.
  - Replace the outer antd `<Card title={…} extra={…}>` with `<Panel title="低波动选股" actions={<Button …>查询</Button>}>`. Keep the `SafetyCertificateOutlined` icon via Panel's `icon` prop. Keep the `查询` Button exactly (text + onClick + loading) as the `actions`.
  - Keep the antd `Alert` disclaimer verbatim (text contract). Keep the controls (指数池 Select + 返回名次 InputNumber); you may group them in a `flex flex-wrap items-center gap-3` row instead of nested antd `Space`.
  - In `buildColumns()`, change the `近20日收益` render: replace the inline hex color with token classes — `const cls = Number(value) >= 0 ? 'text-up' : 'text-down';` and render `<Text className={cls}>{formatPercent(value)}</Text>` (positive = green per the new convention).
  - Replace the inline `color: '#8c8c8c'` loading text with `className="text-muted"` (Tailwind), drop the inline style.
  - Optional: wrap the returned Panel in `<FadeIn>`.
  - Keep antd `Table` (rows + lowvol-row test hook come from the mock), `rowKey`, columns, dataSource, loading, pagination, size, locale.

- [ ] **Step 2: Run the screen spec + a quick render check**

Run: `npx vitest run src/__tests__/low-volatility-screen.test.jsx`
Expected: PASS (3 rows, 查询 button, alert text, mount+click fetch, error path all intact).

- [ ] **Step 3: Commit**
```bash
git add src/components/LowVolatilityScreen.jsx
git commit -m "feat(lowvol): elevate screen onto Panel + green-up return color" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Elevate LowVolPortfolioPanel

**Files:** Modify `frontend/src/components/LowVolPortfolioPanel.jsx`

- [ ] **Step 1: Implement**
  - Import `Panel, MetricGrid, StatCard` from `'../design/components'`. Remove `Card, Statistic, Row, Col` from the antd import; KEEP `Select, InputNumber, Button, Table, Alert, Space, Typography, Empty, Spin`.
  - Replace the outer antd `<Card type="inner" title={…} extra={…}>` with `<Panel title="低波动组合回测（净额，含 A 股摩擦）" icon={<LineChartOutlined />} actions={<Button …>运行回测</Button>}>`. Keep the `运行回测` Button exactly.
  - Keep the antd `Alert` disclaimer verbatim. Keep the controls row (指数池 + 篮子只数), regroupable with Tailwind flex.
  - Replace the antd `Statistic`/`Row`/`Col` summary block (调仓期数 / 年换手(单边) / 净超额年化 vs 等权) with `<MetricGrid><StatCard label="调仓期数" value={data.n_periods ?? '—'} /><StatCard label="年换手(单边)" value={`${ratio(data.avg_annual_turnover, 2)}×`} /><StatCard label="净超额年化 vs 等权" value={pct((data.metrics?.net?.cagr ?? 0) - (data.metrics?.benchmark?.cagr ?? 0))} accent /></MetricGrid>`. (Same values; the test does not assert these.)
  - Equity-curve `Line` strokes: net basket `stroke="var(--color-accent)"`, gross `stroke="var(--color-warn)"`, benchmark `stroke="var(--color-muted)"` (replace `#cf1322`/`#fa8c16`/`#8c8c8c`). Keep names, dataKeys, dot=false, strokeWidth/dasharray.
  - Replace the inline `color: '#8c8c8c'` loading text with `className="text-muted"`.
  - Keep antd `Table` for the metrics (metric-row test hook from the mock), `METRIC_COLUMNS`, `buildMetricRows`. The metric table's `highlight` bold styling stays.
  - Optional: wrap in `<FadeIn>`.

- [ ] **Step 2: Run the portfolio spec**

Run: `npx vitest run src/__tests__/low-vol-portfolio-panel.test.jsx`
Expected: PASS (no auto-run, 运行回测 fetches once, 3 metric rows with 0.44/0.22, alert text, error path).

- [ ] **Step 3: Commit**
```bash
git add src/components/LowVolPortfolioPanel.jsx
git commit -m "feat(lowvol): elevate portfolio panel onto Panel + StatCards + token chart" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Final verification + visual check

- [ ] **Step 1:** `npm test` (all green), `npm run lint && npm run lint:css && npm run build` (clean). Confirm no `[..]` arbitrary Tailwind classes were introduced (`grep -nE "(text|tracking|max-w|basis)-\[" src/components/LowVolatility*.jsx src/components/LowVolPortfolioPanel.jsx`) and no design hex (`grep -nE "#(cf1322|3f8600|8c8c8c|fa8c16)" src/components/LowVol*.jsx`).
- [ ] **Step 2 (controller):** load `http://localhost:3000/?view=lowvol` in DEV; confirm both tabs (选股 / 策略回测) render in the elevated style in dark + light; confirm positive returns show GREEN and negatives RED (green-up).
- [ ] **Step 3:** fix any issue under the relevant task. No commit for verification.

---

## Self-Review (plan author)
- Coverage: screen (Task 1) + portfolio (Task 2) elevated onto primitives; green-up convention applied (Task 1 return cell; chart uses neutral series tokens); hex removed (Task 3 grep). ✓
- Contracts: keeps antd `Table`/`Alert`/`Button` (the mocked sources of `lowvol-row`/`metric-row`/`role=alert`/button names); `Panel`/`MetricGrid`/`StatCard` render real and don't touch the asserted hooks. ✓
- Consistency: uses the same primitives/props as Plan 0a/0b; token utilities `text-up`(green)/`text-down`(red) match the green-up decision and the 0a token values; chart strokes via `var(--color-*)`. No new arbitrary classes (guarded by Task 3 grep + the existing design-no-arbitrary-classes guard covers primitives).
