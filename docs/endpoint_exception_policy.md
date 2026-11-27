# Endpoint Exception Policy — Broad Catch Follow-up

**Date:** 2026-05-07
**Status:** Approved for v5.0.x tech-debt cleanup follow-up
**Scope:** Remaining broad `except Exception` handlers under `backend/app/api/v1/endpoints/` after the typed-exception cleanup rounds.

---

## Goal

Finish the endpoint-exception cleanup with an explicit policy instead of continuing mechanical rewrites. The earlier design targeted a full sweep, but the remaining handlers are mostly response-contract, stale-cache, health-probe, or local-first degradation boundaries. Changing them blindly risks breaking API behavior while providing little maintainability gain.

## Current State

As of commit `0c88347 [verified] Type backtest history report exceptions`, the remaining broad handlers are:

- `analysis.py`: 14
- `backtest.py`: 11
- `industry/rotation.py`: 9
- `policy_radar.py`: 2, already annotated with `# noqa: BLE001`
- `infrastructure.py`: 1
- `realtime.py`: 1

This is down from roughly 70 endpoint broad catches before the cleanup rounds. The count uses `except Exception` with or without an `as <name>` binding.

## Decision Summary

1. Stop treating every broad catch as automatically removable.
2. Preserve broad catches only at explicit degradation/contract boundaries.
3. Convert remaining broad catches only when the target response contract has a test proving the new behavior.
4. Prefer small follow-up helpers over more one-off typed tuples when the same policy repeats.
5. Do not change HTTP status / response-shape contracts in the same PR as exception narrowing.

---

## Policy Categories

### P1 — Typed exception required

Use typed exception tuples or `AppException`/`HTTPException` when the endpoint is a normal request/response operation and failure should be surfaced as a server/client error.

Examples already completed:

- `system.py` performance/metrics/provider status failures
- `events.py`, `trading.py`, `market_data.py`, `optimization.py`, `cross_market.py`
- Safe slices in `analysis.py`, `backtest.py`, and `industry/*`

Rules:

- Re-raise `HTTPException` unchanged.
- Re-raise `AppException` unchanged when the endpoint is using the centralized error handler.
- Do not catch `AttributeError`, `TypeError`, or `KeyError` unless the test names why those are expected runtime data-shape errors.
- Add or update tests before narrowing the catch.

### P2 — Legacy envelope boundary

Some endpoints intentionally return HTTP 200 with `{ "success": false, "error": "..." }` for runtime failures. Keep that response shape until a dedicated API-contract migration changes callers and tests together.

Current examples:

- `backtest.py` main execution endpoints:
  - `run_batch_backtest`
  - `run_walk_forward_backtest`
  - `run_market_regime_backtest`
  - `run_portfolio_strategy_backtest`
  - `run_backtest`
  - `compare_strategies_post`
  - `run_backtest_monte_carlo`
  - `compare_strategy_significance`
  - `run_multi_period_backtest`
  - `run_market_impact_analysis`

Design rule:

- Do **not** convert these to `AppException` piecemeal.
- First decide whether backtest execution endpoints should keep the legacy envelope or migrate to 4xx/5xx structured errors.
- If migrating, update frontend callers, tests, and docs in the same slice.

### P3 — Degrade-to-fallback boundary

Some endpoints should serve stale cache or empty local-first payloads rather than fail hard. Broad catches may be valid here because the purpose is to keep the UI available when optional providers, caches, snapshots, or upstream feeds are absent.

Current examples:

- `analysis.py` overview fallback/cache path
- `industry/rotation.py` intelligence/network stale-cache fallback
- `policy_radar.py` signal/records empty-payload fallback
- `realtime.py` optional symbol-display metadata enrichment

Design rule:

- Keep the degradation behavior.
- If touched, extract a small helper that documents the policy, for example:

```python
def _return_stale_or_raise(cache_key: str, exc: Exception, message: str):
    logger.error(message, exc_info=True)
    stale = _get_stale_endpoint_cache(cache_key)
    if stale is not None:
        return stale
    raise HTTPException(status_code=500, detail=str(exc)) from exc
```

- Add tests for both branches:
  - fresh path fails + stale exists → stale response returned
  - fresh path fails + no stale → original error contract preserved

### P4 — Health probe boundary

Health endpoints should report per-provider status and continue probing other providers even if one provider import or network call fails.

Current examples:

- `industry/rotation.py::health_check` AKShare/Sina/THS probes

Design rule:

- Broad catches are acceptable if the exception is converted into a provider-specific status such as `blocked`, `error`, `not_installed`, or `degraded`.
- Prefer small probe helpers over inlining multiple `try/except Exception` blocks.
- Do not let one provider failure make `/industry/health` fail wholesale.

### P5 — OAuth popup bridge boundary

OAuth popup callback endpoints may need to render an HTML bridge with `{ success: false, error: ... }` instead of throwing an exception, because the browser popup must post a terminal result back to the opener.

Current example:

- `infrastructure.py::oauth_provider_callback`

Design rule:

- Preserve the HTML bridge behavior.
- If changed, catch expected OAuth exchange errors explicitly and keep a final carefully-documented fallback for popup rendering failures.
- Never include tokens, authorization codes, refresh tokens, or credential material in the posted payload or logs.

---

## Next Implementation Plan

### Task 1 — Document accepted broad catches inline

**Objective:** Make the remaining broad catches auditable without changing runtime behavior.

**Files:**

- Modify: `backend/app/api/v1/endpoints/backtest.py`
- Modify: `backend/app/api/v1/endpoints/analysis.py`
- Modify: `backend/app/api/v1/endpoints/industry/rotation.py`
- Modify: `backend/app/api/v1/endpoints/infrastructure.py`

**Steps:**

1. Add short comments near preserved broad catches explaining the category (`legacy envelope`, `stale-cache fallback`, `health probe`, or `OAuth popup bridge`).
2. Keep behavior unchanged.
3. Run:

```bash
.venv/bin/python -m ruff check backend/app/api/v1/endpoints/backtest.py backend/app/api/v1/endpoints/analysis.py backend/app/api/v1/endpoints/industry/rotation.py backend/app/api/v1/endpoints/infrastructure.py
.venv/bin/python -m pytest tests/unit tests/integration -q -m "not perf"
```

### Task 2 — Optional helper extraction for duplicated stale-cache fallback

**Objective:** Reduce repeated error/stale-cache logic in `industry/rotation.py` without changing response shape.

**Files:**

- Modify: `backend/app/api/v1/endpoints/industry/rotation.py`
- Test: existing industry endpoint tests, plus one focused stale-cache test if missing

**TDD:**

1. Add a test proving stale cache is returned when the fresh intelligence/network computation fails.
2. Add a test proving no-stale still raises HTTP 500 with the current detail.
3. Extract a helper only after tests are green.

### Task 3 — Optional backtest execution-envelope migration design

**Objective:** Decide whether the backtest execution endpoints should keep legacy `{success:false}` or migrate to centralized structured errors.

**Files:**

- Modify docs first: `docs/backtest-result-contract.md`
- Then only after approval/clear migration target, modify `backtest.py`, frontend callers, and tests.

**Do not combine with catch narrowing.**

---

## Updated Acceptance Criteria

For the v5.0.x typed-exception cleanup, success is now:

- No broad catch remains in ordinary endpoint error paths where typed exceptions are safe.
- Remaining broad catches are classified as one of:
  - legacy envelope boundary
  - degrade-to-fallback boundary
  - health probe boundary
  - OAuth popup bridge boundary
- Every future removal of a remaining broad catch must include a contract test proving the response shape.
- Backend regression remains green:

```bash
.venv/bin/python -m pytest tests/unit tests/integration -q -m "not perf"
```

---

## Deferred Work

- Backtest execution response contract migration.
- Shared stale-cache fallback helper extraction.
- Shared provider health probe helper extraction.
- Removing `policy_radar.py` `# noqa: BLE001` only if local-first empty-payload fallback is redesigned.
