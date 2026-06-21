# Frontend Industry Workspace Redesign — Phase 2 (Plan 0f) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Finish the industry workspace — wrap the secondary-tab sub-panel Cards in the `Panel` primitive and flip the remaining red-up directional colors to GREEN-up — so industry is fully consistent with the rest of the app. Keep the suite green.

**Architecture:** Restyle + localized color swaps. Add a small `style` passthrough to `Panel` (bespoke sub-panel surfaces use inline gradients/borders). antd `Card`→`Panel`; pinned directional `Statistic`s → plain spans. Keep all logic/handlers/tables/testids.

**Tech Stack:** React 18, Ant Design 5 (kept), `src/design/` primitives, Tailwind v4, Vitest.

**Conventions:** Run from `frontend/`. Branch `feat/frontend-industry-phase2`. Every commit ends with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT touch repo-root `scripts/start_system.sh`.

## DO-NOT-BREAK contract
- No unit test asserts any sub-panel Card `data-testid` — but FORWARD each via Panel's `testId` prop anyway (hygiene / E2E): `industry-alerts-card`, `industry-replay-card`, `industry-saved-views-panel`, `industry-watchlist-card`, `policy-radar-panel`.
- CRITICAL (tested): PolicyRadar refresh `Button` keeps `aria-label="刷新政策雷达"` (in Panel `actions`). policy-radar text contracts (`共 N 条政策记录`, `新能源 · 偏多`) unchanged.
- `industry-ranking-policy-overlay.test.jsx` (policy-signal testids) + `industry-dashboard-columns.test.jsx` render via the ranking table — keep the Table + its columns untouched inside the Panel.
- No test asserts color → all flips safe. Do NOT edit any test file.

## Color convention: GREEN-up (positive=green `var(--color-up)`, negative=red `var(--color-down)`). FLIP only DIRECTIONAL spots (sign of change/return/flow). KEEP non-directional (severity/category/source) as-is.

---

## Task 1: Add a `style` passthrough to the Panel primitive

**Files:** Modify `frontend/src/design/components/Panel.jsx`; Test `frontend/src/__tests__/design-panel.test.jsx` (extend).

- [ ] **Step 1: Write the failing assertion** — add to `design-panel.test.jsx`:
```jsx
test('forwards style + testId to the surface root', () => {
  render(<Panel testId="x" style={{ background: 'rgb(1, 2, 3)' }}>b</Panel>);
  const root = screen.getByTestId('x');
  expect(root.style.background).toBe('rgb(1, 2, 3)');
});
```
- [ ] **Step 2: Run → FAIL** (`npx vitest run src/__tests__/design-panel.test.jsx`) — Panel ignores `style`.
- [ ] **Step 3: Implement** — add `style` to Panel's params and forward to `Surface`:
  In `Panel.jsx`, change the signature to include `style`, and pass `style={style}` to the `<Surface ...>` element (Surface spreads `...rest` onto its div, so both `data-testid={testId}` and `style` land on the root). Keep everything else.
- [ ] **Step 4: Run → PASS** (`npx vitest run src/__tests__/design-panel.test.jsx`), then `npm run lint`.
- [ ] **Step 5: Commit**
```bash
git add src/design/components/Panel.jsx src/__tests__/design-panel.test.jsx
git commit -m "feat(design): Panel forwards style to its surface root" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Card→Panel + color flips — Ranking / SavedViews / PolicyRadar / Alerts / Replay

**Files:** `industry/IndustryRankingPanel.jsx`, `IndustrySavedViewsPanel.jsx`, `PolicyRadarPanel.jsx`, `IndustryAlertsPanel.jsx`, `IndustryReplayPanel.jsx`. Import `{ Panel }` from `'../../design/components'`; remove `Card` from antd imports where it becomes unused.

- [ ] **Step 1: Implement (per file; line numbers approximate — verify by reading)**
  - `IndustryRankingPanel.jsx` (Card ~line 36): `<Card className="industry-ranking-card" title="行业排名" extra={toolbar}>` → `<Panel className="industry-ranking-card" title="行业排名" actions={toolbar}>`. Keep the state-bar + Table body.
  - `IndustrySavedViewsPanel.jsx` (~21): `<Card size="small" data-testid="industry-saved-views-panel" style={{marginBottom:12}} title="保存视图" extra={<Space>…</Space>}>` → `<Panel testId="industry-saved-views-panel" style={{marginBottom:12}} title="保存视图" actions={<Space>…</Space>}>`.
  - `PolicyRadarPanel.jsx` (~164): `<Card size="small" data-testid="policy-radar-panel" title={<Space>…政策雷达…</Space>} extra={<Button aria-label="刷新政策雷达" …/>}>` → `<Panel testId="policy-radar-panel" title={<Space>…</Space>} actions={<Button aria-label="刷新政策雷达" …/>}>`. The aria-label MUST stay.
  - `IndustryAlertsPanel.jsx` (~85): `<Card size="small" data-testid="industry-alerts-card" style={{marginBottom:12, background:<gradient>, border:…, boxShadow:…}} styles={{body:{padding:'12px 14px'}}}>` → `<Panel testId="industry-alerts-card" style={{marginBottom:12, background:<same gradient>, border:<same>, boxShadow:<same>, padding:'12px 14px'}}>` (no title — the header stays the first child div in the body; fold the body padding into the style). Keep all children.
  - `IndustryReplayPanel.jsx` (~53): same pattern as Alerts — `<Panel testId="industry-replay-card" style={{marginBottom:12, background:<conditional gradient/panelSurface>, border:<conditional>, boxShadow:panelShadow, padding:'12px 14px'}}>`; header stays first child. Then COLOR FLIPS in this file: line ~219 hardcoded `color:'#cf1322'` (升温最快/rise) → `'var(--color-up)'`; line ~242 hardcoded `'#3f8600'` (降温最快/fall) → `'var(--color-down)'`; lines ~327/353/366 plain-div diff values `>= 0 ? '#cf1322' : '#3f8600'` → `>= 0 ? 'var(--color-up)' : 'var(--color-down)'`.
- [ ] **Step 2:** `npx vitest run src/__tests__/policy-radar-panel.test.js src/__tests__/industry-ranking-policy-overlay.test.jsx` → PASS.
- [ ] **Step 3:** `npm test` green; `npm run lint && npm run lint:css && npm run build` clean. Commit:
```bash
git add src/components/industry/IndustryRankingPanel.jsx src/components/industry/IndustrySavedViewsPanel.jsx src/components/industry/PolicyRadarPanel.jsx src/components/industry/IndustryAlertsPanel.jsx src/components/industry/IndustryReplayPanel.jsx
git commit -m "feat(industry): Card→Panel for ranking/views/policy/alerts/replay + green-up replay colors" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Card→Panel + color flips — Watchlist / ResearchFocus / Cluster / ScoreRadar / selection

**Files:** `industry/IndustryWatchlistPanel.jsx`, `IndustryResearchFocusPanel.jsx`, `IndustryClusterPanel.jsx`, `IndustryScoreRadarModal.jsx`, `industry/useIndustrySelection.js`.

- [ ] **Step 1: Implement**
  - `IndustryWatchlistPanel.jsx`: outer Card (~24) → `<Panel testId="industry-watchlist-card" style={{marginBottom:12, borderRadius:12, border:<same>, boxShadow:<same>, background:<same>}} title={<div>…我的观察…</div>} actions={watchlistEntries.length>0 ? <Space>…</Space> : null}>`. Color flips: line ~93 `<Tag color={changeDelta>=0 ? 'red' : 'green'}>` → `'green' : 'red'`; lines ~100/103 plain spans `>= 0 ? '#cf1322' : '#3f8600'` → `'var(--color-up)' : 'var(--color-down)'`.
  - `IndustryResearchFocusPanel.jsx`: outer Card (~31) → `<Panel style={{marginBottom:12, borderRadius:12, border:<conditional>, boxShadow:PANEL_SHADOW, background:<conditional>}} title={<div>研究焦点 …</div>}>`. Color flips: lines ~100/110 plain divs `>= 0 ? '#cf1322' : '#3f8600'` → `'var(--color-up)' : 'var(--color-down)'`.
  - `IndustryClusterPanel.jsx`: no outer Card (fragment) — leave the fragment. Convert the two INNER cluster stat Cards (~95–156) to `Panel` (keep their conditional `isHot` border/shadow via Panel `style`; keep the `title` with FireOutlined). The detail Card (~314–344) → `Panel` (style passthrough for the marginTop/border). COLOR FLIPS: the two `<Statistic valueStyle={{color: avg_momentum>=0 ? '#cf1322' : '#3f8600'}}>` (~117) and (avg_flow ~127) — these are `.ant-statistic !important`-pinned (color invisible), so REPLACE each `<Statistic>` with a plain markup: a label + a plain `<span style={{ color: v >= 0 ? 'var(--color-up)' : 'var(--color-down)', fontWeight:600 }}>{formattedValue}</span>` (keep the same title text + formatted value). KEEP the hot-cluster Tag (~323 `'red'`/`'blue'`) — non-directional.
  - `IndustryScoreRadarModal.jsx`: the two directional `<Statistic valueStyle={{color: changePct>=0?…}}>` (~96) and (moneyFlow ~103) — replace each `<Statistic>` with a plain label + `<span style={{ color: v >= 0 ? 'var(--color-up)' : 'var(--color-down)' }}>{value}</span>`. KEEP the score-tier Statistic (~83, `getIndustryScoreTone`) as-is (non-directional). (This modal isn't a Card; no Panel change.)
  - `industry/useIndustrySelection.js`: score-breakdown color fields — line ~244 `change >= 0 ? '#cf1322' : '#3f8600'` and ~253 `moneyFlow >= 0 ? '#cf1322' : '#3f8600'` → `'var(--color-up)' : 'var(--color-down)'`. KEEP line ~20/23 volatility severity (`'error'`/`'success'`) as-is (non-directional).
- [ ] **Step 2:** `npx vitest run src/__tests__/industry-dashboard-columns.test.jsx src/__tests__/use-industry-stocks.test.js` → PASS (and any test that renders these — run the relevant ones).
- [ ] **Step 3:** `npm test` green; `npm run lint && npm run lint:css && npm run build` clean. Commit:
```bash
git add src/components/industry/IndustryWatchlistPanel.jsx src/components/industry/IndustryResearchFocusPanel.jsx src/components/industry/IndustryClusterPanel.jsx src/components/industry/IndustryScoreRadarModal.jsx src/components/industry/useIndustrySelection.js
git commit -m "feat(industry): Card→Panel for watchlist/focus/cluster + green-up remaining directional colors" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Final verification + visual check
- [ ] **Step 1:** `npm test` green; `npm run lint && npm run lint:css && npm run build` clean; `grep -nE "(text|tracking|max-w|basis|col-span)-\[|#(cf1322|3f8600)" src/components/industry/IndustryWatchlistPanel.jsx src/components/industry/IndustryReplayPanel.jsx src/components/industry/IndustryResearchFocusPanel.jsx src/components/industry/IndustryClusterPanel.jsx src/components/industry/IndustryScoreRadarModal.jsx src/components/industry/useIndustrySelection.js` → no arbitrary classes / no leftover A-share hex.
- [ ] **Step 2 (controller):** load `http://localhost:3000/?view=industry` (dark + light); click through the 排行榜 / 聚类分析 / 提醒中心 / 历史回放 / 视图沉淀 / 政策雷达 / 龙头股 / 观察列表 tabs + select an industry (研究焦点) — confirm every sub-panel is an elevated Panel and all directional values read green-up (positive green / negative red).
- [ ] **Step 3:** fix any issue under the relevant task.

## Self-Review (plan author)
- Coverage: all 8 sub-panel Card sites → Panel (Task 2: 5, Task 3: Watchlist/Focus/Cluster); all 15 directional color spots flipped (Task 2: replay 5; Task 3: watchlist 3, focus 2, cluster 2 Statistics→span, scoreradar 2 Statistics→span, selection 2); 4 non-directional kept. Panel gains `style` passthrough (Task 1) for the bespoke gradient surfaces. ✓
- Contracts: testIds forwarded via Panel `testId`; PolicyRadar `aria-label` kept in actions; ranking/columns Tables untouched; no test edited; no test asserts color. ✓
- Consistency: pinned `Statistic`/`Text` directional colors → plain spans (gotcha pattern); token vars `var(--color-up/down)`; bespoke surfaces keep their look via Panel `style` (inline beats utilities). No arbitrary `[..]`/`col-span-N`.
