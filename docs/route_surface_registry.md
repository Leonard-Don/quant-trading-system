# Route Surface Registry

This document mirrors `backend/app/api/v1/route_surface_registry.py` and explains how to treat backend endpoints that do not have a direct production frontend call site.

## Policy

- Do not call an endpoint dead from one heuristic. A route with no frontend usage may be API-only, internal/ops, or deprecated compatibility.
- New frontend work should use the typed service helpers in `frontend/src/services/api.js` rather than hard-coding paths in components.
- Deprecated compatibility routes should not gain new UI entries. Remove them only after a compatibility window and log review.
- Product-grade engines should have at least one frontend service helper even if no large UI panel exists yet.

## Advanced ETF engines now exposed through frontend service helpers

These backend engines were present and are now reachable through the frontend service barrel:

- `POST /etf-rotation/backtest` → `postEtfRotationBacktest(payload)`
- `POST /etf-rotation/strategy-comparison` → `postEtfRotationStrategyComparison(payload)`
- `POST /etf-rotation/optimize-parameters` → `postEtfRotationOptimizeParameters(payload)`

All three use the `long` timeout profile because they synchronously run research engines over committed historical price matrices.

## API-only / ops surfaces

- `POST /analysis/comprehensive`: aggregate API for notebooks/scripts; UI should prefer narrower analysis panel endpoints.
- `POST /backtest/report/base64`: report export automation surface; UI should prefer rendered dashboard/export utilities.
- `GET /market-data/sources/health`: ops/admin diagnostic surface; only wire to UI if an explicit admin health panel is built.

## Deprecated compatibility surfaces

Do not add new frontend entries for these. Prefer infrastructure diagnostics / realtime websocket flows and retire after a compatibility window with no live callers.

- `POST /realtime/subscribe`
- `POST /realtime/unsubscribe`
- `GET /system/status`
- `GET /system/performance`
- `GET /system/health-check`
- `GET /system/metrics`
- `GET /system/dependencies`

## Guardrail

`tests/unit/test_route_surface_registry.py` statically parses FastAPI route decorators and production frontend source. Any public backend route with no frontend entry must be classified in the registry, and deprecated no-frontend routes must have a non-permanent exit plan.
