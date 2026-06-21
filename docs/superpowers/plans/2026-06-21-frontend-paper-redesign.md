# Frontend Paper-Trading Workspace Redesign (Plan 0d) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Elevate the `paper` (纸面账户) workspace onto the design-system primitives, flip its directional P&L colors to the chosen GREEN-UP convention (escaping the `!important` antd-text pins), and keep all existing Vitest specs green.

**Scope:** ONLY `frontend/src/components/PaperTradingPanel.jsx` (the `paper` view). `TradePanel.jsx` is out of scope — it is lazy-loaded by `RealTimePanel` (a trade modal), so it belongs to the realtime phase.

**Architecture:** Restyle, not rewrite. Keep all logic/state/handlers/column defs/forms. Replace antd `Card`→`Panel`; replace the hero's antd `Statistic`/`Row`/`Col` KPI block→`MetricGrid`/`StatCard`; render directional P&L as plain `<span style={{color:'var(--color-up|down)'}}>` (NOT antd `Statistic`/`Text`, which are pinned by `.ant-statistic-content-value`/`.ant-typography { color:var(--text-primary)!important }`). Keep antd `Form`/`Table`/`Popconfirm`/`InputNumber`/`Segmented`/`Tag`/`Button`/`Tooltip` and every `data-testid`.

**Tech Stack:** React 18, Ant Design 5 (kept for Form/Table/Popconfirm/etc.), the `src/design/` primitives, Tailwind v4, Vitest.

**Conventions:** Run from `frontend/`. Branch `feat/frontend-paper-redesign`. Every commit ends with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT touch repo-root `scripts/start_system.sh`.

---

## DO-NOT-BREAK contract (paper-trading-panel.test.js renders REAL antd; selective API mocks; fake setInterval/clearInterval)
Keep ALL of these:
- data-testids: `paper-snapshot-positions`, `paper-export-orders-csv`, `paper-export-positions-csv`, `paper-stop-loss-input`, `paper-take-profit-input`, `paper-prefill-tag`, `paper-position-stop-loss-${symbol}`, `paper-position-take-profit-${symbol}`, `paper-cancel-pending-${id}`, `paper-order-effective-${id}`, `paper-order-source-${id}`.
- Text/format the test asserts: the chip Tags `持仓 1` / `订单 1` / `初始资金 ¥10000.00`; currency cell formats (`$142.50`, `¥1710.00`, etc.); `距触发` text inside the stop/take-profit cell wrappers; source labels (`止损自动`/`止盈自动`/`限价触发`/`手动`); error text (`insufficient cash`, `请输入成交价`).
- Roles: buttons `提交订单`, `取消挂单` (inside the Popconfirm popover), the CSV/snapshot buttons (by testid); placeholders `如 600519.SS / AAPL`, `如 10`, `如 150.0`, `如 5`.
- The ONE antd-class assertion: `document.querySelector('.ant-popover')` — so KEEP the antd `Popconfirm` for the cancel-pending action.
- No test asserts `.ant-statistic-content-value`, `.ant-typography`, `.ant-card`, or antd Table classes → replacing `Statistic`/`Text`/`Card` with primitives/plain spans is safe as long as the numbers/text still render.
Do NOT edit the test file.

## Green-up flips (chosen convention: 绿涨红跌 / green-up)
The component is currently A-share red-up. Flip the two P&L spots to green-up AND move them off the pinned antd elements:
1. 总收益率 hero Statistic (≈lines 707–719): currently `valueStyle.color = (totalReturn>=0) ? var(--accent-danger)(red) : var(--accent-success)(green)` on an antd `<Statistic>` (color pinned, doesn't even show). Becomes a `StatCard` whose `value` is a colored plain span: `value={<span style={{ color: (summary.totalReturn ?? 0) >= 0 ? 'var(--color-up)' : 'var(--color-down)' }}>{fmtPct}</span>}` (green for gain now).
2. 浮动盈亏 positions column (≈lines 503–506): currently `<Text style={{color: value>=0 ? var(--accent-danger) : var(--accent-success)}}>`. Becomes `<span style={{ color: value >= 0 ? 'var(--color-up)' : 'var(--color-down)' }}>{formatMoney(...)}</span>` (plain span, green-up).
Leave NON-price-direction colors alone: the 止损价/止盈价 `距触发` proximity warnings (red=near stop, green=near take-profit) and the BUY/SELL `Tag` colors are order/warning semantics, not 涨跌 — keep them as-is.

---

## Task 1: Elevate PaperTradingPanel

**Files:** Modify `frontend/src/components/PaperTradingPanel.jsx`

- [ ] **Step 1: Implement**
  - Import `Panel, MetricGrid, StatCard` from `'../design/components'` (and `FadeIn` from `'../design/motion'` if wrapping). Remove `Card`, `Statistic`, `Row`, `Col` from the antd import; KEEP `Button, Empty, Form, Input, InputNumber, Popconfirm, Segmented, Space, Table, Tag, Tooltip, Typography, App as AntdApp`.
  - HERO (≈675–778): replace the `<Card variant="borderless">` + `<Title>` + `<Row>/<Col>` of four `<Statistic>` with a `Panel` (title `纸面账户`, icon `<ThunderboltOutlined />`, actions = the existing buttons `Space`). Inside, render the KPIs via `<MetricGrid>` + four `StatCard`s:
    - `<StatCard label="现金" value={…current value expr…} />`
    - `<StatCard label="持仓市值" value={…} />`
    - `<StatCard label="总权益" value={…} />`
    - `<StatCard label="总收益率" value={<span style={{ color: (summary.totalReturn ?? 0) >= 0 ? 'var(--color-up)' : 'var(--color-down)' }}>{…current percent text…}</span>} />`
    Keep the chip Tags (`持仓 N`, `订单 N`, `初始资金 …`) and the action buttons (snapshot + CSV exports, with their testids) — put them in the Panel `actions` or a `Toolbar`/flex row. Preserve the existing currency formatting helpers and value expressions exactly.
  - ORDER ENTRY (≈782–888): replace `<Card title={…} size="small">` with `<Panel title="下单" icon={<DollarOutlined />}>`. Keep the antd `Form` + all `Form.Item`s, `Segmented` (`paper-order-type-toggle`), inputs (`paper-stop-loss-input`, `paper-take-profit-input`), placeholders, and the `提交订单` Button unchanged.
  - POSITIONS (≈891–901): `<Card>`→`<Panel title="当前持仓" icon={<LineChartOutlined />}>`; keep the antd `Table` + `positionColumns`. In `positionColumns`, change the 浮动盈亏 render per green-up flip #2 (plain span). Keep the `paper-position-stop-loss-${symbol}` / `paper-position-take-profit-${symbol}` cell wrappers + `距触发` text.
  - PENDING ORDERS (≈904–956): `<Card>`→`<Panel title="挂单（限价单 / 待成交）">`; keep the antd `Table`, inline columns, the `Popconfirm` + `paper-cancel-pending-${id}` button (the `.ant-popover` contract).
  - RECENT ORDERS (≈958–967): `<Card>`→`<Panel title="近期订单">`; keep the antd `Table` + `orderColumns` (incl. `paper-order-effective-${id}`, `paper-order-source-${id}`).
  - Use Tailwind utilities for spacing (`flex flex-col gap-4`, grid) and `text-muted`/`text-subtle` for muted text. NO arbitrary `[..]` classes; NO hardcoded hex. The P&L colors use `var(--color-up)`/`var(--color-down)` only.
  - Optional: wrap the workspace in `<FadeIn>`.

- [ ] **Step 2: Run the paper spec**

Run: `npx vitest run src/__tests__/paper-trading-panel.test.js`
Expected: PASS (all the testids/text/roles/`.ant-popover` contracts intact). If a contract fails, restore the attribute/text (do NOT edit the test).

- [ ] **Step 3: Run full suite + lint + build**

Run: `npm test` (all green), `npm run lint && npm run lint:css && npm run build` (clean), and verify discipline: `grep -nE "(text|tracking|max-w|basis)-\[|#[0-9a-fA-F]{3,6}" src/components/PaperTradingPanel.jsx` → no arbitrary classes / no hardcoded hex (CSS-var colors like `var(--color-up)` are fine).

- [ ] **Step 4: Commit**
```bash
git add src/components/PaperTradingPanel.jsx
git commit -m "feat(paper): elevate 纸面账户 onto design primitives + green-up P&L" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Final verification + visual check

- [ ] **Step 1:** `npm test` green; `npm run lint && npm run lint:css && npm run build` clean.
- [ ] **Step 2 (controller):** load `http://localhost:3000/?view=paper` in DEV; confirm hero (Panel + KPI StatCards), order form, positions/orders panels render elevated in dark + light; confirm a positive 总收益率 / 浮动盈亏 shows GREEN and negative RED (green-up) — verify computed color via the page if needed (the `.ant-typography`/`.ant-statistic` pin must NOT apply since these are plain spans now).
- [ ] **Step 3:** fix any issue under Task 1. No commit for verification.

---

## Self-Review (plan author)
- Coverage: PaperTradingPanel elevated onto Panel + MetricGrid/StatCard; both P&L spots flipped to green-up AND moved to plain spans (escaping the `.ant-statistic-content-value`/`.ant-typography !important` pins). TradePanel correctly excluded (realtime scope). ✓
- Contracts: keeps real antd Form/Table/Popconfirm/InputNumber/Segmented/Tag/Button and every data-testid + the `.ant-popover` Popconfirm assertion; primitives render real (test uses real antd) and don't touch asserted hooks. ✓
- Consistency: same primitives/props as 0a–0c; green-up via `var(--color-up)`/`var(--color-down)` on plain spans (the proven pattern from 0c); StatCard accepts a node value so the colored span rides inside it. No arbitrary classes / no hex (Task 1 Step 3 grep).
