# Frontend Industry Workspace Redesign — Phase 1 (Plan 0e) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Unify the industry (行业热度) workspace to the chosen GREEN-UP / red-down convention (the treemap is the app's visual centerpiece) and elevate its hero + market-snapshot bar onto the design-system primitives — without breaking the 12-file industry test suite.

**Scope (Phase 1 of industry):** the green-up color flip (all VISIBLE directional spots) + `IndustryDashboardHero` + `IndustryMarketSnapshotBar` + the `IndustryDashboard` inline Cards. DEFERRED to a follow-up (0f), noted at the bottom: wrapping the six secondary-tab sub-panel Cards (ranking/alerts/replay/saved-views/watchlist/policy-radar/cluster) in `Panel`, and the pinned-Statistic directional colors in `IndustryClusterPanel`/`IndustryScoreRadarModal` (color is `.ant-statistic !important`-pinned, so invisible today — lower value).

**Architecture:** Mostly localized swaps + chrome restyle. Keep all logic/handlers/tables/controls. antd `Card`→`Panel`; hero metric divs→`MetricGrid`/`StatCard`.

**Tech Stack:** React 18, Ant Design 5 (kept), `src/design/` primitives, Tailwind v4, recharts, Vitest.

**Conventions:** Run from `frontend/`. Branch `feat/frontend-industry-redesign`. Every commit ends with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT touch repo-root `scripts/start_system.sh`.

---

## DO-NOT-BREAK contract (industry tests render REAL antd; NONE assert colors — flip is safe)
Verified: no industry test asserts a color/`positive=red`. Keep these intact:
- `data-testid="heatmap-tile"` + click → `onIndustryClick(name)`.
- `data-testid="heatmap-legend-slider"`; the legend text `−` (U+2212) and `+` must still render (they are leftLabel/rightLabel — semantic, NOT color; do NOT swap the label text, only the gradient direction).
- `heatmap-stats-bar.test.js` queries `.ant-statistic-content-value` for up/down/flat COUNTS → KEEP the antd `Statistic`s in `HeatmapStatsBar` (do not convert them; their valueStyle color is `!important`-pinned and invisible anyway — leave them, only the token swap applies).
- `industry-heatmap.test.js` uses `.heatmap-control-timeframe` + `.ant-select-selector` + option text `5日`, and `最近快照` fallback text → do NOT rename those classes / keep antd `Select` in `HeatmapControls` (untouched here).
- `industry-dashboard-columns.test.jsx`: `industry-score-radar-trigger`, `industry-market-cap-source-tag`, `tr.ant-table-row`, button text `详情`/`对比`/`回测`.
- `industry-ranking-policy-overlay.test.jsx`: `industry-policy-signal-column`/`-cell`/`-tag-{signal}`.
- `leader-stock-panel.test.js`: `leader-stock-row`, `mini-sparkline`, `回测` button.
- `policy-radar-panel.test.js`: text `共 N 条政策记录`, `刷新政策雷达` aria-label.
- `heatmap-stats-bar` text: `偏多`/`偏空`/`中性`, inflow tags `新能源 +50.0亿`, `💰 净流入 TOP`/`💰 主力净流入`.
Do NOT edit any test file.

---

## Task 1: Green-up color flip (all visible directional spots)

**Files:** `IndustryHeatmap.jsx`, `industry/HeatmapLegend.jsx`, `utils/industryHeatmapTokens.js`, `industry/HeatmapTreemap.jsx`, `industry/buildHotIndustryColumns.jsx`, `industry/buildStockColumns.jsx`, `IndustryTrendPanel.jsx`. (Line numbers are from the scout; verify before editing.)

- [ ] **Step 1: Apply the swaps**

  a. `src/components/IndustryHeatmap.jsx` `redGreenGradient` (≈lines 381–384): swap the `value > 0` and `else` branch bodies so positive→the green `rgb(...)` formula and negative→the red `rgb(...)` formula. (The two rgb expressions are the green and red families; swap which branch returns which.)

  b. `src/components/industry/HeatmapLegend.jsx` (≈line 37): reverse the non-turnover gradient endpoints — `'linear-gradient(to right, rgb(235, 20, 20), #6B6B6B, rgb(20, 180, 40))'` (now left=red/negative → right=green/positive). Keep the `−`/`+` labels unchanged.

  c. `src/utils/industryHeatmapTokens.js` (≈lines 16–17): swap the aliases →
     `export const HEATMAP_POSITIVE = 'var(--accent-success)';` (green)
     `export const HEATMAP_NEGATIVE = 'var(--accent-danger)';` (red)
     This single swap fixes all token-driven spots (treemap tooltip rows, HeatmapStatsBar Tags/Progress/banner).

  d. `src/components/industry/HeatmapTreemap.jsx`:
     - arrowColor (≈line 260): swap operands → `displayValue >= 0 ? '#b7eb8f' : '#ff9c9c'` (green for up).
     - tooltip Tag (≈line 340): `item.value >= 0 ? 'success' : 'error'`.
     - policy color-mode override (≈lines 244–246): swap so bullish→green `rgb(60, 140, 80)`, bearish→red `rgb(200, 60, 60)`.

  e. `src/components/industry/buildHotIndustryColumns.jsx` (≈lines 121, 148, 163) and `src/components/industry/buildStockColumns.jsx` (≈lines 65, 80): these are plain `<span>` cells with hardcoded `value >= 0 ? '#cf1322' : '#3f8600'`. Change to green-up using token vars: `value >= 0 ? 'var(--color-up)' : 'var(--color-down)'` (plain spans, so the var resolves).

  f. `src/components/IndustryTrendPanel.jsx`:
     - constants (≈lines 46–47): `const POSITIVE = 'var(--accent-success)';` / `const NEGATIVE = 'var(--accent-danger)';` (this flips the recharts line/cell + the plain-span cells).
     - Tag ternaries (≈lines 701, 704, 722): `>= 0 ? 'success' : 'error'`.
     - `insightTone` (≈lines 560–563): swap so positive→`'green'`, negative→`'red'`.
     - The two section-header antd `<Text>` (≈822 涨幅前5, ≈857 跌幅前5) are `.ant-typography !important`-pinned (their color never shows). Convert ONLY these two to plain `<span style={{ color: POSITIVE }}>` / `<span style={{ color: NEGATIVE }}>` so the green/red shows. Leave the plain-span data cells (≈834, 869) as-is (they already use the constants and now resolve green-up).

  g. Leave NON-directional colors alone: score-tone helpers (`getIndustryScoreTone`), volatility severity, alert severity, cluster quadrant/hot-cluster tags, `IndustryRotationChart` series palette — none are sign-of-return colors.

- [ ] **Step 2: Run the industry suite**

Run: `npx vitest run src/__tests__/industry-heatmap.test.js src/__tests__/heatmap-legend.test.js src/__tests__/heatmap-stats-bar.test.js src/__tests__/industry-dashboard-columns.test.jsx src/__tests__/industry-ranking-policy-overlay.test.jsx`
Expected: all PASS (no test asserts color).

- [ ] **Step 3: Full suite + build, then commit**

Run: `npm test` (green), `npm run lint && npm run build` (clean).
```bash
git add src/components/IndustryHeatmap.jsx src/components/industry/HeatmapLegend.jsx src/utils/industryHeatmapTokens.js src/components/industry/HeatmapTreemap.jsx src/components/industry/buildHotIndustryColumns.jsx src/components/industry/buildStockColumns.jsx src/components/IndustryTrendPanel.jsx
git commit -m "feat(industry): flip heatmap + trend colors to green-up convention" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Elevate the industry hero + market-snapshot bar + dashboard cards

**Files:** `industry/IndustryDashboardHero.jsx`, `industry/IndustryMarketSnapshotBar.jsx`, `IndustryDashboard.jsx`

- [ ] **Step 1: Implement**
  - `IndustryDashboardHero.jsx`: replace the outer `<Card className="app-page-hero app-page-hero--industry" variant="borderless">` with `Panel` (variant `raised`). Keep the eyebrow (行业指挥席) + `<Title>行业轮动大屏</Title>` (keep a heading element) + subtitle + the sentiment/coverage `Tag` chips. Replace the four `.app-page-metric-card` divs (热力覆盖/上涨占比/市值覆盖/观察+新提醒) with `<MetricGrid>` + four `<StatCard>` (same label + value text). Import `Panel, MetricGrid, StatCard` from `'../../design/components'` (note the path depth from `components/industry/`).
  - `IndustryMarketSnapshotBar.jsx`: replace the outer `<Card className="industry-market-snapshot-bar" size="small">` with `Panel` (keep the snapshot title/timestamp/sentiment Tag/up-ratio/health pills/inflow-outflow-turnover pills as children). Keep its market-direction colors consistent with green-up if any are sign-driven (check: up-ratio / inflow — if they use HEATMAP_POSITIVE token they already flipped in Task 1; if hardcoded, align to green-up).
  - `IndustryDashboard.jsx`: replace the inline `<Card title="行业聚类分析" extra={…}>` (≈291–333) and the two empty-state `<Card size="small"><Empty/></Card>` fallbacks (≈433–436, 478–480) with `Panel`. Keep the cluster Select + reload control in the Panel `actions`. Import the primitives.
  - Use Tailwind utilities for spacing; NO arbitrary `[..]` classes; NO `md:col-span-N` (use `md:grid-cols-*`); NO new hardcoded hex. Keep all `data-testid`s and the antd `Tabs`/`Select`/`Table`/`Tag` intact.
  - If a `Panel` needs a `data-testid` (none of the elevated ones are asserted, but preserve if present), use Panel's `testId` prop.

- [ ] **Step 2: Run industry render tests + full suite + build**

Run: `npx vitest run src/__tests__/industry-heatmap.test.js src/__tests__/industry-dashboard-columns.test.jsx` then `npm test` (green) and `npm run lint && npm run lint:css && npm run build` (clean).

- [ ] **Step 3: Commit**
```bash
git add src/components/industry/IndustryDashboardHero.jsx src/components/industry/IndustryMarketSnapshotBar.jsx src/components/IndustryDashboard.jsx
git commit -m "feat(industry): elevate hero + snapshot bar + dashboard cards onto primitives" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Final verification + visual check

- [ ] **Step 1:** `npm test` green; `npm run lint && npm run lint:css && npm run build` clean; `grep -nE "(text|tracking|max-w|basis|col-span)-\[" src/components/industry/IndustryDashboardHero.jsx src/components/industry/IndustryMarketSnapshotBar.jsx src/components/IndustryDashboard.jsx` → no matches.
- [ ] **Step 2 (controller):** load `http://localhost:3000/?view=industry` (dark + light). Confirm: the treemap now shows GREEN for positive change% / RED for negative (green-up); the legend gradient reads red(left)→green(right); the hero is the elevated Panel + KPI StatCards; the market-snapshot bar is a Panel. Verify a tile's computed bg is green for a positive industry if needed.
- [ ] **Step 3:** fix any issue under the relevant task. No commit for verification.

---

## Deferred to follow-up (Plan 0f — industry Phase 2)
- Wrap the six secondary-tab sub-panel Cards in `Panel` (with `testId` passthrough): `IndustryRankingPanel`, `IndustryAlertsPanel` (`industry-alerts-card`), `IndustryReplayPanel` (`industry-replay-card`), `IndustrySavedViewsPanel` (`industry-saved-views-panel`), `IndustryWatchlistPanel` (`industry-watchlist-card`), `PolicyRadarPanel`, `IndustryClusterPanel`.
- The pinned directional `Statistic` colors in `IndustryClusterPanel` (≈112–128) and `IndustryScoreRadarModal` (≈91–103) — convert to plain spans + green-up (currently `.ant-statistic !important`-pinned, so invisible; low value).
- `LeaderStockPanel` / `IndustryRankingPanel` / `IndustryRotationChart` chrome elevation.

## Self-Review (plan author)
- Coverage: green-up flip for every VISIBLE directional spot (treemap bg ★, legend, token alias, arrows, tooltip tag, policy override, column builders, trend panel) — Task 1; hero + snapshot + dashboard cards elevated — Task 2. Sub-panel Card→Panel + pinned-Statistic colors explicitly deferred to 0f. ✓
- Contracts: keeps `heatmap-tile`, legend slider + `−`/`+` labels (only gradient direction swapped), the `.ant-statistic-content-value` counts in HeatmapStatsBar (Statistics untouched), `.heatmap-control-timeframe`/Select, all column/policy/leader testids. No test asserts color → flip safe (verified by the test-contract scout). ✓
- Consistency: green-up via the same token approach as 0c/0d (plain spans / token vars / antd Tag color props, never `.ant-typography`/`.ant-statistic`-pinned elements for the visible ones); primitives + props per 0a–0d; no arbitrary `[..]` or `col-span-N` classes.
