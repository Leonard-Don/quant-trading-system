# Tech Debt Cleanup — Design

**Date:** 2026-05-06
**Status:** Approved (scope: "全部做")
**Origin:** Project evaluation surfaced five items; user confirmed "do all five, in your suggested order."

---

## Goals

Resolve five maintainability debts identified during the v5.0.0 evaluation:

1. Split `backend/app/api/v1/endpoints/industry.py` (1,676 lines) into focused sub-routers.
2. Replace broad `except Exception` handlers in API endpoints with the typed exceptions already defined in `backend/app/core/error_handler.py`.
3. Expand mypy blocking coverage from the current narrow set to `src/backtest/`, `src/data/realtime_manager.py`, and the hot-path service modules.
4. Add integration tests for the four most state-prone areas: backtest pipeline e2e, realtime provider fallback, paper-trading order lifecycle, industry heatmap cache.
5. Rename JSX-bearing `frontend/src/**/*.js` (production source files) to `.jsx`, leaving test files alone.

## Non-Goals

- API contract changes (response shapes, route prefixes — all preserved).
- Touching the algorithm library (`src/strategy/`, `src/analytics/` outside what mypy catches).
- Reworking the frontend test framework (already on Vitest; only file renames).
- Docker / containerization (out of repo scope per user).
- New features.

---

## Design Decisions

### D1. industry.py split — preserve test-patch compatibility via deprecation shim

**Current state:** `backend/app/api/v1/endpoints/industry.py` is 1,676 lines. Lines 57–100 re-export 50+ helper functions from service modules so existing unit tests can `monkeypatch.setattr(industry, "<helper>", ...)`. Removing the shim would break every test in `tests/unit/test_industry_*.py`.

**Decision:** Split route handlers into three sub-routers, all mounted under the same `/industry` prefix:

```
backend/app/api/v1/endpoints/industry/
├── __init__.py          # exports the aggregated router + deprecated re-exports
├── _compat.py           # test-patch compatibility shim (marked deprecated)
├── heatmap.py           # GET /heatmap, GET /heatmap/history, GET /heatmap/snapshot
├── leaders.py           # GET /leaders, GET /leaders/{symbol}, watchlist endpoints
└── rotation.py          # GET /rotation, GET /sectors, ranking endpoints
```

The `__init__.py` re-imports symbols from `_compat.py` so `from backend.app.api.v1.endpoints import industry; industry.<helper>` keeps working. New code imports directly from service modules.

**Why not full break:** Tests use the shim heavily. Rewriting tests is out of scope for this cleanup; deprecating the shim signals the future direction without breaking the present.

### D2. Exception typing — typed sweep plus explicit policy boundaries

**Initial decision:** Replace broad `except Exception as e:` blocks in ordinary `backend/app/api/v1/endpoints/*.py` error paths with the appropriate typed exception from `backend/app/core/error_handler.py`:

- `ValidationError` (400) — request payload / param violations
- `NotFoundError` (404) — entity lookup failures (symbol, profile, backtest_id)
- `RateLimitError` (429) — rate limiter trips
- `ExternalServiceError` (503) — Redis / Celery / DB / generic upstream failures
- `DataFetchError` (502) — data provider failures (more specific than ExternalServiceError, takes a `symbol` arg)
- `AuthenticationError` (401) — auth failures
- `AppException` (500) — genuinely unknown errors when the endpoint is already on the centralized error-handler path

**2026-05-07 amendment:** The cleanup discovered that the remaining broad catches are not all equivalent. Some are intentional response-contract or degradation boundaries and should not be mechanically converted. The follow-up policy is documented in `docs/superpowers/specs/2026-05-07-endpoint-exception-policy.md`.

Accepted policy boundaries:

- Legacy backtest execution envelopes that intentionally return HTTP 200 with `{success:false,error:...}`.
- Stale-cache, empty-payload, best-effort enrichment, or other local-first degradation paths that keep the UI available when optional data is unavailable.
- Provider health probes that must continue probing after one provider fails.
- OAuth popup bridge callbacks that must render a postMessage HTML result instead of raising.

**Frontend impact check:** Audit `frontend/src/components/ErrorBoundary.js` and `frontend/src/services/api.js` to confirm they handle the 4xx/5xx structure produced by `error_handler.py`. If the new typed errors return a different JSON shape than what the frontend currently expects, add a thin compat layer in `api.js`/`error_handler.py` to keep the response body backward-compatible (key fields: `error`, `message`, `detail`).

**Why not force a final mechanical sweep:** Mixed old/new patterns are bad when they are accidental, but response-contract boundaries are different. For the remaining catches, changing exception shape without contract tests would risk breaking callers more than it improves maintainability.

### D3. mypy expansion — add three module groups to blocking

**Current state:** CI blocking mypy targets:
- `src/analytics/technical_indicators.py`
- `src/analytics/industry/`

**Decision:** Add to blocking list:
1. `src/backtest/` — entire backtesting engine. Hot path, frequently changed.
2. `src/data/realtime_manager.py` — single high-traffic file, well-bounded.
3. `backend/app/services/realtime_alerts.py`, `backend/app/services/preferences.py`, `backend/app/services/runtime_state.py` — small, well-defined service modules.

**Approach:** Add modules one-by-one to the blocking list in CI. For each, run mypy locally first; if it produces >20 errors, fix in-place; if it produces an unmanageable number, defer that module to non-blocking and note in the plan.

**Skip for this round:** `backend/app/api/v1/endpoints/*` (will type these after the industry.py split — no point typing code about to be moved).

### D4. Integration tests — four targeted scenarios filling actual gaps

**Audit finding:** `tests/integration/` already contains 7 files. Two of the originally-proposed tests already have strong coverage:
- `test_backtest_pipeline.py` — already covers `DataManager → Strategy → Backtester` e2e with synthetic data fixtures
- `test_provider_failover.py` — already covers `DataProviderFactory` priority/failover/empty-frame behaviors

**Decision:** Drop those two and add four tests that fill actual gaps:

1. **`test_paper_order_lifecycle.py`** — Create profile → place limit order → simulate price hit → verify fill → archive to research journal. Exercises `backend/app/services/paper_trading.py` + `src/trading/`. Currently only unit-level coverage.
2. **`test_industry_heatmap_cache.py`** — Cold cache miss (computes), warm cache hit (skips compute), TTL expiry (recomputes), disk-snapshot reload after restart. Uses real `CacheManager` with a `tmp_path` fixture.
3. **`test_realtime_websocket_lifecycle.py`** — Connect → subscribe → receive broadcast → unsubscribe → disconnect, with multiple concurrent clients. Exercises `backend/app/websocket/` + `src/data/realtime_manager.py`. Different layer from `test_provider_failover.py` (which tests data-fetch layer).
4. **`test_research_journal_persistence.py`** — Backtest snapshot write → list → read → archive → delete. The existing `test_research_journal_contracts.py` only tests response schemas; this tests the actual persistence cycle including disk round-trip.

**Why these four:** Each exercises a state-machine or persistence cycle that unit tests cannot fully cover (multi-step, multi-component, cache/persistence/WebSocket interactions).

**No DB-backed tests yet:** Alembic baseline exists but we don't have a test seed harness. Defer to a follow-up; for now, integration tests use real disk (tmp_path) for persistence and synthetic providers for data.

### D5. .js → .jsx rename — scope to production source only

**Decision:**
- **Rename** all `frontend/src/**/*.js` files that contain JSX (top-level `<...>` syntax in returns / declarations).
- **Leave alone** `frontend/src/__tests__/*.test.js` (tests run via Vitest config, file extension irrelevant; less churn).
- **Leave alone** `frontend/src/services/*.js`, `frontend/src/utils/*.js`, `frontend/src/contexts/*.js` if they contain no JSX (most don't).
- **Update** any explicit-extension imports (`from './Foo.js'` → `from './Foo.jsx'`). Vite resolves extensionless imports automatically.
- **Drop** the `esbuild: { loader: "jsx" }` workaround from `frontend/vite.config.js` once renames complete.

**Detection:** Use `grep -rE 'return \(?<[A-Z]|<\/?[A-Z]' frontend/src --include="*.js"` to find JSX-bearing `.js` files.

---

## Execution Strategy

```
Batch 1 (parallel):
  - industry.py split            (backend, isolated)
  - .js → .jsx rename            (frontend, isolated)
  ↓ verify: pytest unit + frontend test pass

Batch 2 (sequential):
  - Exception typing sweep       (depends on Batch 1: stable endpoints)
  ↓ verify: pytest unit + manual API smoke

Batch 3 (parallel):
  - 4 integration tests          (writes new files, no merge conflict)
  - mypy expansion + CI update   (config + type fixes)
  ↓ verify: full CI suite

Batch 4 (sequential):
  - Final regression: pytest + frontend + e2e
  - Single commit per batch (4 commits total) on a feature branch
```

**Branch:** `cleanup/v5.0.x-tech-debt` (or worktree per user preference).

**Rollback points:** Each batch is one commit. If Batch N fails verification, revert only Batch N — earlier batches stay.

---

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| industry.py split breaks monkeypatch tests | High | Compat shim in `_compat.py`; run full `tests/unit/test_industry_*.py` before commit |
| Typed exceptions change JSON response shape | Medium | Audit `ErrorBoundary.js` + `api.js`; preserve key fields (`error`, `message`, `detail`) |
| mypy expansion reveals unfixable type errors in some module | Medium | Per-module gate: if too red, defer to non-blocking, note in plan |
| .js → .jsx rename breaks dynamic / glob imports | Low | grep all `import.*\.js'` patterns first; update before rename |
| Integration test flakiness from real provider calls | Medium | Use httpretty / responses for HTTP mocking; only the *backtester / cache* layers are real |

---

## Acceptance Criteria

- `pytest tests/unit tests/integration -q` all green
- `cd frontend && npm test` all green
- CI pipeline (backend + frontend + e2e + mypy) all green on the cleanup branch
- `industry.py` no longer exists as a single file (replaced by `industry/` package); each sub-router < 700 lines
- Ordinary endpoint runtime failures use typed exceptions when a response-contract test proves the response shape is safe to preserve
- Remaining broad catches are classified in `docs/superpowers/specs/2026-05-07-endpoint-exception-policy.md` as legacy envelope, degradation, health-probe, or OAuth popup bridge boundaries
- mypy CI blocking list includes the modules in D3
- 4 new integration test files exist and pass: `test_paper_order_lifecycle.py`, `test_industry_heatmap_cache.py`, `test_realtime_websocket_lifecycle.py`, `test_research_journal_persistence.py`
- No JSX in `.js` files under `frontend/src/` (excluding `__tests__/`)
- `frontend/vite.config.js` no longer needs `esbuild: { loader: "jsx" }`
- Design + plan + each batch committed; no force-pushes; main untouched until ready

---

## Out of Scope (Explicitly Deferred)

- Refactoring `tests/unit/test_industry_*.py` to remove monkeypatch reliance
- DB-backed integration tests (need test fixture harness first)
- Typing `backend/app/api/v1/endpoints/*` (after this round)
- Renaming non-JSX `.js` files to `.ts` / `.tsx`
- Reducing `--legacy-peer-deps` in CI (separate dependency hygiene task)
