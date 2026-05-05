# Follow-up Plan: Frontend CRA → Vite Migration

> **Status:** Stubbed during the 2026-05-05 evaluation follow-up. Execute as a dedicated session — multi-hour scope with regression risk.
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `react-scripts` (CRA, officially deprecated) with Vite as the dev server and build tool, preserving the existing 5 workspaces (today / backtest / realtime / industry / paper) and 54 Jest-based unit tests.

**Why this is a separate plan:** CRA → Vite is genuinely multi-hour, touches build/dev/test/CI/E2E, and has non-trivial regression risk on a 195-file production frontend. Doing it inline alongside backend refactors would couple unrelated risks.

**Tech Stack target:**
- Vite 7 (latest as of 2026-05) + `@vitejs/plugin-react`
- Vitest as the test runner (replaces CRA's bundled Jest)
- `vite-plugin-svgr` if any inline SVG imports remain
- Keep React 18 + Ant Design 5 + Recharts + Lightweight-Charts unchanged
- Keep Playwright e2e suite (`tests/e2e/`) unchanged — only the dev/build commands change

**Repo facts at planning time:**
- `frontend/package.json` declares `react-scripts: 5.0.1`
- 14 `REACT_APP_*` env-var references inside `frontend/src/**/*.js[x]` (they all need a `VITE_*` rename or a compatibility shim)
- 54 test files under `frontend/src/__tests__/` written for `@testing-library/react` + Jest matchers — Vitest is API-compatible with minor config tweaks
- `frontend/public/index.html` uses CRA's `%PUBLIC_URL%` convention (Vite uses raw `/` paths)
- CI job `frontend` in `.github/workflows/ci.yml` runs `CI=1 npm test -- --runInBand --watch=false src/__tests__` and `npm run build`
- E2E job `research-e2e` in CI starts the local stack via `scripts/start_system.sh` which invokes `npm start` indirectly

---

## Task 1: Install Vite + Vitest, write configs (no CRA removal yet)

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/vitest.config.js` (or merge into vite.config.js with `test:` block)
- Modify: `frontend/public/index.html` → `frontend/index.html` at frontend root

- [ ] Add devDependencies: `vite`, `@vitejs/plugin-react`, `vitest`, `jsdom`, `@vitest/ui` (dev-only).
- [ ] Write `vite.config.js` with: `react()` plugin, `server.port = 3000`, `server.proxy['/api'] -> http://localhost:8000`, `server.proxy['/ws'] -> ws://localhost:8000` (for the WebSocket route).
- [ ] Move `frontend/public/index.html` to `frontend/index.html`, replace `%PUBLIC_URL%/` with `/`, add `<script type="module" src="/src/index.js"></script>` (Vite expects script tag, not auto-injection).
- [ ] Add `package.json` scripts: `"dev": "vite"`, `"build": "vite build"`, `"preview": "vite preview"`, `"test:vitest": "vitest run"`. Keep CRA scripts as-is for now so we can A/B.
- [ ] Run `npm install` and verify lockfile diff.

## Task 2: Migrate env vars `REACT_APP_*` → `VITE_*`

**Files:**
- Search and replace in: `frontend/src/**/*.js`, `frontend/src/**/*.jsx`
- Modify: `.env*` files at frontend root
- Modify: `docs/DEPLOYMENT.md` (env var section)

- [ ] Run `grep -rln 'REACT_APP_' frontend/src` to enumerate the 14 hits — there are typically: `REACT_APP_API_URL`, `REACT_APP_API_TIMEOUT`, plus per-feature flags.
- [ ] Replace `process.env.REACT_APP_X` with `import.meta.env.VITE_X` at each call site.
- [ ] Rename env vars in `frontend/.env*`.
- [ ] Update DEPLOYMENT.md so the documented var names match.

## Task 3: Switch tests to Vitest

**Files:**
- Modify: `frontend/src/setupTests.js` (CRA's auto-loaded jest-dom setup)
- Create: `frontend/vitest.setup.js`
- Modify: `frontend/package.json` test script

- [ ] In `vite.config.js`, add a `test:` block: `environment: 'jsdom'`, `setupFiles: ['./vitest.setup.js']`, `globals: true`.
- [ ] Move the contents of `setupTests.js` into `vitest.setup.js` (mostly `import '@testing-library/jest-dom'`).
- [ ] Run `npm run test:vitest` and triage — typical issues: `jest.fn()` → `vi.fn()`, timers (`jest.useFakeTimers` → `vi.useFakeTimers`), `require.context` (Vite has `import.meta.glob`).
- [ ] Once green, replace the `test` script: `"test": "vitest run --reporter=default src/__tests__"`.

## Task 4: Update CI

**Files:**
- Modify: `.github/workflows/ci.yml` (frontend job)

- [ ] Update the regression command in the `frontend` job from `npm test -- --runInBand --watch=false src/__tests__` to `npm test -- --reporter=default src/__tests__` (Vitest equivalent).
- [ ] Verify the build step `npm run build` still produces `frontend/build/` (Vite default is `dist/` — either point CI to `dist/` or set `build.outDir = 'build'` in `vite.config.js`).
- [ ] Confirm the e2e job's `start_system.sh` still works since `npm start` now means Vite. If `start_system.sh` greps for CRA-specific output, update it.

## Task 5: Remove CRA, smoke-test all 5 workspaces

- [ ] Delete `react-scripts` from `package.json`, run `npm prune`.
- [ ] Delete `frontend/public/index.html` (already moved).
- [ ] `npm run dev` and click through: today → backtest → realtime → industry → paper. Watch console for missing-asset warnings (CRA's loose import behavior is stricter in Vite).
- [ ] `npm run build` and serve `dist/` (or `build/`); repeat the click-through against the production bundle.
- [ ] Run the full Playwright e2e suite: `cd tests/e2e && npm run verify:all`.

## Task 6: Document the migration

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/DEPLOYMENT.md` (build commands section)
- Modify: `README.md` (any CRA-specific badge or instruction)

- [ ] Note `BREAKING:` env-var rename in CHANGELOG.
- [ ] Update build-command snippets.

## Risk Register

- **WebSocket proxy in dev:** CRA's `proxy` field in package.json silently handles WS upgrades; Vite needs explicit `server.proxy` config with `ws: true`.
- **Lazy imports / code-split chunks:** CRA names them by route; Vite uses content hashes. Any code that hardcoded a chunk filename will break.
- **`require.context` for dynamic loading** of strategy/component lists: must convert to `import.meta.glob`.
- **Service worker / PWA:** if registered via CRA's default `registerServiceWorker`, that's CRA-specific and needs `vite-plugin-pwa` or removal.
- **Snapshot tests:** any Jest snapshots need re-generation under Vitest.

## Acceptance criteria

- [ ] `npm run dev` serves the app at `:3000` with HMR working
- [ ] `npm run build` produces a working production bundle
- [ ] All 54 unit tests pass under Vitest
- [ ] All Playwright e2e suites green
- [ ] CI green on a feature branch before merging
