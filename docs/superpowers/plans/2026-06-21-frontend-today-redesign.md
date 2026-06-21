# Frontend Today-Workspace Redesign (Plan 0b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Elevate the `today` (今日研究) workspace to the design-system foundation's "Midnight Fintech" look (deep + light) by consuming the Plan 0a primitives, and fix the industry heatmap treemap text clipping — without breaking any existing Vitest spec.

**Architecture:** Restyle, not rewrite. Keep ALL of `TodayResearchDashboard.jsx` logic/state/handlers/render-helpers and the inner list rendering; swap the presentational chrome (hero, KPI cards, panels, status chips) to the Plan 0a primitives (`PageHero`, `MetricGrid`, `StatCard`, `Panel`, `StatusPill`, `Toolbar`) + Tailwind utilities, and add restrained motion (`FadeIn`/`Stagger`). The treemap fix is isolated style hardening in `HeatmapTreemap.jsx`.

**Tech Stack:** React 18, Ant Design 5 (kept for buttons/forms/selects/modals/lists), the `src/design/` foundation from Plan 0a, Tailwind v4, framer-motion, Vitest.

**Conventions:** Run from `frontend/`. Branch: `feat/frontend-today-redesign`. Every commit ends with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer. Do NOT touch repo-root `scripts/start_system.sh`.

---

## DO-NOT-BREAK contract (verified from the test suite — every item MUST still hold)

TodayResearchDashboard (`today-research-inbox.test.jsx`, `today-research-send-to-paper.test.js`):
- A heading element with accessible name `研究工作台` (`getByRole('heading', {name:'研究工作台'})`). `PageHero`'s title renders `<h2>` — that satisfies it.
- An element with `aria-label="研究工作台流程"` whose text content includes `线索收集`, `排队分层`, `回到上下文` → KEEP the `WORKBENCH_FLOW_STEPS` data and the `aria-label` verbatim; only restyle the wrapper.
- `data-testid="today-research-inbox"` on the inbox panel, containing the text `研究收件箱`, the bucket labels `需处理` and `继续观察`, the numeric tag `7`, and NOT the text `false`.
- `data-testid="today-research-actions"` on the actions panel, containing `研究行动`, `复核提醒`, `跟进行业观察`, and buttons (role=button) whose accessible names match `/稍后/`, `/忽略/`, `/完成/`.
- `data-testid="today-entry-send-to-paper"` stays on the send-to-paper button in `renderEntry()`; only backtest entries with a non-empty symbol render it.
- The reload/export/import buttons keep `aria-label` `刷新` / `导出备份` / `导入备份`. The archive filter controls keep their `aria-label`s.

HeatmapTreemap (`industry-heatmap.test.js`):
- Tile keeps `data-testid="heatmap-tile"`, `data-industry-name`, `role="button"`, `aria-label`, and its `onClick` → `onIndustryClick(name)`.
- Industry name stays rendered as visible text inside the tile.
- Do NOT touch `HeatmapControls`, `HeatmapStatsBar`, `HeatmapLegend` (other specs are coupled to their antd `Statistic`/`Select`/`Slider` internals).

If any change would violate a contract, keep the attribute/text and restyle around it.

---

## File Structure

| Path | Change |
|---|---|
| `src/components/industry/HeatmapTreemap.jsx` | Task 1 — style hardening on tile text elements + content gate (no markup/testid/handler changes) |
| `src/components/TodayResearchDashboard.jsx` | Task 2 — swap presentational chrome to design primitives + motion |
| `src/__tests__/treemap-tile-overflow.test.jsx` | Task 1 — new regression test for the leader-pill ellipsis styles |

No other files change. The `today-research-*` CSS classes in `index.css` stay (other code may reference them); Task 2 simply stops relying on them for the converted sections.

---

## Task 1: Fix industry treemap text clipping/overlap

**Files:**
- Modify: `frontend/src/components/industry/HeatmapTreemap.jsx`
- Test: `frontend/src/__tests__/treemap-tile-overflow.test.jsx`

Root cause (already diagnosed): (a) the leader-pill name `<span>` (≈lines 743–751) has `overflow:hidden`+`textOverflow:ellipsis` but no `minWidth:0`/`maxWidth`, so as a flex child it never shrinks and never ellipsizes; the pill `<div>` (≈lines 723–733) has no `overflow:hidden`. (b) the market-cap `<Text>` (≈lines 781–790) has no `maxWidth`/`whiteSpace`/`overflow`. (c) the smallest content gate `layout.width > 24 && layout.height > 20` (≈line 637) lets the name render in a ~21px-tall tile with no vertical room → clipping.

- [ ] **Step 1: Write the failing regression test**

Create `frontend/src/__tests__/treemap-tile-overflow.test.jsx`:

```jsx
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import IndustryHeatmap, { buildFallbackHeatmapPayload } from '../components/IndustryHeatmap';

// A wide/tall single industry forces the "large block" path (leader pill + market cap row).
const ONE_BIG_INDUSTRY = {
  industries: [
    {
      name: '半导体',
      change_pct: 2.29,
      market_cap: 1119070000000,
      stock_count: 179,
      leading_stock: '晶升股份这是一个很长的龙头股名称用于触发省略',
      money_flow: 5_000_000_000,
      market_cap_source: 'live',
    },
  ],
};

describe('treemap tile text does not overflow', () => {
  test('leader-stock name uses shrink+ellipsis styles so it cannot overflow the pill', async () => {
    render(
      <IndustryHeatmap
        initialData={buildFallbackHeatmapPayload ? buildFallbackHeatmapPayload(ONE_BIG_INDUSTRY) : ONE_BIG_INDUSTRY}
        onIndustryClick={() => {}}
        onTimeframeChange={() => {}}
      />,
    );
    const tile = await screen.findByTestId('heatmap-tile');
    const leader = tile.querySelector('[data-testid="heatmap-leader-name"]');
    expect(leader).toBeTruthy();
    expect(leader.style.textOverflow).toBe('ellipsis');
    expect(leader.style.overflow).toBe('hidden');
    expect(leader.style.minWidth).toBe('0px');
  });
});
```

Note: if the `IndustryHeatmap` prop shape for seeding data differs, adapt the seed to whatever `industry-heatmap.test.js` already uses to render a tile (it renders one tile from `initialData`); the assertion on the leader span styles is the point. The leader name span currently has NO `data-testid` — Step 3 adds `data-testid="heatmap-leader-name"` to it (additive, breaks nothing).

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run src/__tests__/treemap-tile-overflow.test.jsx`
Expected: FAIL — either no `heatmap-leader-name` element, or the styles don't include `minWidth:0`.

- [ ] **Step 3: Apply the style hardening in `HeatmapTreemap.jsx`**

Make these edits (locate by the quoted current code; line numbers are approximate):

(a) Leader pill container `<div>` (the `isLargeBlock && item.leadingStock` block, ≈line 723): add `overflow: 'hidden'` and `minWidth: 0` to its `style` object (keep all existing properties like `marginTop: 4`, `padding`, `borderRadius`, `background`, `maxWidth: '95%'`, `display: 'flex'`, `alignItems: 'center'`, `gap: 4`).

(b) The `龙头` label `<span>` inside the pill: add `flexShrink: 0` to its style (it already has `whiteSpace:'nowrap'`).

(c) The leader-name `<span>` (≈line 743): add `data-testid="heatmap-leader-name"`, and add `minWidth: 0`, `maxWidth: '100%'`, `flexShrink: 1` to its style (it already has `overflow:'hidden'`, `textOverflow:'ellipsis'`, `whiteSpace:'nowrap'`).

(d) The market-cap `<Text>` (≈line 781): add `maxWidth: '100%'`, `whiteSpace: 'nowrap'`, `overflow: 'hidden'`, `textOverflow: 'ellipsis'` to its style.

(e) The smallest content gate (≈line 637): change `(layout.width > 24 && layout.height > 20)` to `(layout.width > 30 && layout.height > 26)` so the name only renders when one line fits cleanly.

Do not change any `data-testid`, `role`, `aria-label`, `onClick`, or the squarify layout.

- [ ] **Step 4: Run the new test + the existing heatmap test**

Run: `npx vitest run src/__tests__/treemap-tile-overflow.test.jsx src/__tests__/industry-heatmap.test.js`
Expected: both PASS (new test green; existing tile-click + name-presence tests unaffected).

- [ ] **Step 5: Commit**

```bash
git add src/components/industry/HeatmapTreemap.jsx src/__tests__/treemap-tile-overflow.test.jsx
git commit -m "fix(industry): stop treemap tile text clipping (leader ellipsis + gates)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Elevate the today workspace with design-system primitives

**Files:**
- Modify: `frontend/src/components/TodayResearchDashboard.jsx`

This is a guided conversion (judgment task), not a transcription. Preserve every item in the DO-NOT-BREAK contract above. Import the primitives:

```js
import { PageHero, MetricGrid, StatCard, Panel, StatusPill, SectionHeader } from '../design/components';
import { FadeIn, Stagger } from '../design/motion';
```

### Conversion map

1. **Hero (current `<section className="today-research-hero">`, ≈lines 781–826).** Replace the hand-rolled hero with `PageHero`:
   - `eyebrow="今日线索、提醒与复盘档案"` (the current kicker text).
   - `title="研究工作台"` (PageHero renders `<h2>` → still satisfies the heading contract).
   - `subtitle={...}` = the existing subtitle text if present (keep its words).
   - `metrics={ <MetricGrid> ...four StatCards... </MetricGrid> }`, mapping the four current metrics verbatim:
     - `<StatCard label="待处理" value={summary.open_entries || 0} />`
     - `<StatCard label="回测快照" value={getMetricValue(summary, 'backtest')} accent />`
     - `<StatCard label="实时记录" value={...current expression...} />`
     - `<StatCard label="行业观察" value={...current expression...} />`
   - Render the status line (`活跃线索 N 条` / `高优先级 N 条` / `最近同步 …`) below the hero title as a small muted Tailwind row OR as `StatusPill`s (e.g. `<StatusPill tone="info">活跃线索 {n} 条</StatusPill>`). Keep the exact numbers/text.
   - Keep the action buttons (`同步当前状态` primary + the three icon `Tooltip`/`Button`s) EXACTLY (their `aria-label`s `刷新`/`导出备份`/`导入备份` are contract-bound). Place them in a `Toolbar` or a flex row inside/after the hero.

2. **Flow strip (current `<section className="today-research-flow" aria-label="研究工作台流程">`, ≈lines 828–838).** Keep the `aria-label` and the `WORKBENCH_FLOW_STEPS` mapping (text unchanged). Restyle each `today-research-flow__item` as a `Surface`/Tailwind card in a responsive grid (`grid grid-cols-1 sm:grid-cols-3 gap-3`). Keep the icon + `<strong>` title + `<span>` description.

3. **Panels.** For each antd `Card className="today-research-panel ..."` (研究收件箱 ≈line 723, 研究行动 ≈line 748, 处理队列 ≈line 851, 标的时间线 ≈line 887, 数据来源 ≈line 919, 完整档案流 ≈line 944, plus the empty-workbench and manual-entry cards): replace the `Card` wrapper with `Panel`, passing `title=` the existing panel title and `data-testid=` the existing testid (KEEP `today-research-inbox` and `today-research-actions`). Move the panel's existing head/title markup into `Panel`'s `title`/`actions` props; keep ALL body content (bucket list, action list, entry lists, filter bar, selects, buttons) intact. `Panel` already accepts `actions` for right-aligned controls.
   - Note: `Panel` currently does not forward arbitrary DOM props. If you need `data-testid` on the `Panel`'s root, add a one-line `data-testid` passthrough to `Panel` (`src/design/components/Panel.jsx`): accept a `testId` prop and put it on the `Surface` root via `Surface`'s `...rest` (Surface already spreads `...rest`). Then call `<Panel testId="today-research-inbox" ...>`. Verify `Surface` forwards it (it does — it spreads `...rest` onto its div). Keep `Panel`'s test (`design-panel.test.jsx`) green.

4. **Status / count chips.** Convert the inbox bucket counts (需处理/继续观察/稍后/稍后阅读/已归档) and the action summary (需处理/继续观察/稍后/高优先级) to a row of small `StatCard`s or token-styled chips so the numbers read as elevated KPIs. KEEP the label text and the numeric values (contract: `需处理`, `继续观察`, the tag `7` must still render inside the inbox testid). Convert the `数据来源` sync-status `Alert` and any state badges to `StatusPill` where natural.

5. **Motion.** Wrap the hero in `<FadeIn>` and the panel grid children in `<Stagger>` (restrained; reduced-motion auto-degrades). Do not wrap elements that tests query by role/testid in a way that hides them.

6. **Spacing/typography.** Use Tailwind utilities (`flex flex-col gap-4`, `text-muted`, `text-subtle`, `tabular-nums`) on the converted sections to match the elevated sample (consistent gaps, hairline borders via the primitives, tabular numbers on counts).

### Acceptance criteria for Task 2
- Every DO-NOT-BREAK contract item holds.
- The four KPIs render via `StatCard`/`MetricGrid`; panels render via `Panel`; the hero via `PageHero`.
- No new `!important`; no design colors hardcoded (use tokens/Tailwind utilities).

- [ ] **Step 1: Implement the conversion** per the map above (single coherent edit of `TodayResearchDashboard.jsx`, plus the optional one-line `Panel` `testId` passthrough).

- [ ] **Step 2: Run the today specs**

Run: `npx vitest run src/__tests__/today-research-inbox.test.jsx src/__tests__/today-research-send-to-paper.test.js src/__tests__/design-panel.test.jsx`
Expected: all PASS. If a contract assertion fails, fix the markup to restore the attribute/text (do NOT edit the test).

- [ ] **Step 3: Run the FULL suite + lint + build**

Run: `npm test` (all green), then `npm run lint && npm run lint:css && npm run build` (all clean).

- [ ] **Step 4: Commit**

```bash
git add src/components/TodayResearchDashboard.jsx src/design/components/Panel.jsx
git commit -m "feat(today): rebuild 今日研究 workspace on the design-system primitives" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Final verification + visual check (deep + light)

**Files:** none (verification only).

- [ ] **Step 1: Full gates** — `npm test` (all green), `npm run lint`, `npm run lint:css`, `npm run build` (all clean).
- [ ] **Step 2: Visual check (controller does this via the browser).** Load `http://localhost:3000/?view=today` in DEV; confirm the hero/KPIs/panels render in the elevated style in BOTH dark and light (toggle the header sun/moon). Load `http://localhost:3000/?view=industry`, scroll the heatmap; confirm small tiles no longer clip/overlap their text.
- [ ] **Step 3:** If anything is off, fix under the relevant task. No commit needed for verification.

---

## Self-Review (plan author)
- Spec coverage: today rebuild on primitives (Task 2) ✓; treemap clipping fix (Task 1) ✓; both themes + keep-suite-green (Tasks 2–3) ✓. These are exactly the two Plan-0b deliverables deferred from the Phase-0 spec.
- Placeholder scan: Task 1 has concrete edits + a real test; Task 2 is a guided conversion with an explicit, contract-bound acceptance list and a concrete primitive-usage map (appropriate altitude for restyling an existing 1026-line file — full-file transcription would be noise). No "TBD".
- Consistency: primitive names/props (`PageHero`/`MetricGrid`/`StatCard`/`Panel`/`StatusPill` + `FadeIn`/`Stagger`) match the Plan 0a barrels; the `Panel` `testId` passthrough relies on `Surface`'s existing `...rest` spread (verified in Plan 0a). Contract list is quoted from the actual specs.
