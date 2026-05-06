# Tech Debt Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve five maintainability debts: split `industry.py` (1,676 lines) into sub-routers, type all endpoint exceptions, expand mypy CI coverage, add 4 gap-filling integration tests, rename JSX-bearing `.js` to `.jsx`.

**Architecture:** Four sequential batches with parallel subtasks where safe. Spec at `docs/superpowers/specs/2026-05-06-tech-debt-cleanup-design.md`. Branch: `cleanup/v5.0.x-tech-debt`. Each batch ends in one commit; rollback is per-batch.

**Tech Stack:** FastAPI, pytest, mypy, ruff, Vite 5, Vitest, React 18.

---

## Pre-flight

- [ ] **Verify on cleanup branch**

```bash
git rev-parse --abbrev-ref HEAD
# Expected: cleanup/v5.0.x-tech-debt
```

- [ ] **Establish baseline — record passing test counts before any change**

```bash
pytest tests/unit tests/integration -q -m "not perf" 2>&1 | tail -5
cd frontend && CI=1 npm test -- --reporter=basic --pool=forks --poolOptions.forks.singleFork=true src/__tests__ 2>&1 | tail -5
```

Save the pass/fail counts. Any task that ends with fewer passes than baseline = regression, must be fixed before commit.

---

## PHASE 1A — Split `industry.py` into sub-router package

### Task 1: Map current routes to sub-router buckets

**Files:** Read `backend/app/api/v1/endpoints/industry.py` (1,676 lines)

- [ ] **Step 1: Enumerate all `@router.*` decorators with their paths**

```bash
grep -nE '^@router\.(get|post|put|delete|websocket)' backend/app/api/v1/endpoints/industry.py
```

- [ ] **Step 2: Bucket each route into one of three sub-routers**

Write the bucketing as a comment-block at the top of `_industry_helpers.py` (or a scratch file in `tmp/`). Buckets:

- **heatmap**: paths matching `/heatmap*`, `/snapshot*`, plus `/bootstrap` (initial heatmap data)
- **leaders**: paths matching `/leaders*`, `/leader/*`, watchlist endpoints, stock-detail endpoints
- **rotation**: everything else — `/rotation`, `/rank`, `/sectors`, `/trend`, `/cluster`, `/preferences`, `/etfs`, `/events`, `/lifecycle`

If a route is ambiguous, default it to **rotation** (the catch-all).

- [ ] **Step 3: No commit yet — this is just analysis**

### Task 2: Create the sub-router package skeleton

**Files:**
- Create: `backend/app/api/v1/endpoints/industry/__init__.py`
- Create: `backend/app/api/v1/endpoints/industry/_compat.py`
- Create: `backend/app/api/v1/endpoints/industry/heatmap.py`
- Create: `backend/app/api/v1/endpoints/industry/leaders.py`
- Create: `backend/app/api/v1/endpoints/industry/rotation.py`

- [ ] **Step 1: Create `industry/__init__.py`**

```python
"""Industry endpoints package.

Three sub-routers (heatmap / leaders / rotation) all mounted on the same
`/industry` prefix at the API aggregator level. The `_compat` module
re-exports service-layer helpers so existing tests that use
`monkeypatch.setattr(industry, "<helper>", ...)` keep working — those
re-exports are deprecated; new code imports helpers directly from
`backend.app.services.industry.runtime`.
"""

from fastapi import APIRouter

from backend.app.api.v1.endpoints.industry import heatmap, leaders, rotation
from backend.app.api.v1.endpoints.industry._compat import *  # noqa: F401, F403  (test-patch shim)

router = APIRouter()
router.include_router(heatmap.router)
router.include_router(leaders.router)
router.include_router(rotation.router)
```

- [ ] **Step 2: Create empty stub modules**

For each of `heatmap.py`, `leaders.py`, `rotation.py`:

```python
"""<bucket name> sub-router for /industry endpoints."""
import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()
```

- [ ] **Step 3: Create `_compat.py` with all monkeypatch surface symbols**

Open the original `backend/app/api/v1/endpoints/industry.py` and copy lines 56–145 (everything from the comment "Compatibility surface for tests" through the end of `_INDUSTRY_SERVICE_HELPERS` and any subsequent module-level re-binds) into `_compat.py`. Add a deprecation banner at the top:

```python
"""Test-patch compatibility shim — DEPRECATED.

These re-exports exist so unit tests that patch helpers via
`monkeypatch.setattr(industry, "_foo", ...)` keep working.
New code MUST import helpers directly from
`backend.app.services.industry.runtime` and `_industry_helpers`.

Remove this module once all tests have been migrated.
"""
```

- [ ] **Step 4: Verify import paths still resolve (no functionality moved yet)**

The original `industry.py` still has all routes. Run:

```bash
python -c "from backend.app.api.v1.endpoints import industry; print(len([r for r in industry.router.routes]))"
```

Expected: prints a route count (whatever is in the original file). This proves the package hasn't broken the import yet.

### Task 3: Move heatmap routes

**Files:**
- Modify: `backend/app/api/v1/endpoints/industry/heatmap.py`
- Modify: `backend/app/api/v1/endpoints/industry.py` (delete moved routes)

- [ ] **Step 1: Identify heatmap route handlers in original `industry.py`**

Use the bucketing from Task 1, Step 2. For each route in the heatmap bucket, identify:
- The `@router.{method}(...)` decorator line
- The handler function (continues to next blank line followed by another `@router.` or end-of-file)

- [ ] **Step 2: Cut routes from `industry.py`, paste into `heatmap.py`**

Move the route handlers (decorator + function body) wholesale. Keep all imports they need — copy/duplicate into `heatmap.py` (don't try to share imports yet).

The functions reference helpers via `_compat` re-exports. Since `_compat.py` re-exports them, sub-routers can import: `from backend.app.api.v1.endpoints.industry._compat import _foo, _bar`.

- [ ] **Step 3: Run unit tests scoped to heatmap**

```bash
pytest tests/unit -q -k heatmap 2>&1 | tail -10
```

Expected: same count as baseline. If any test breaks because it patches a symbol that's now only on the sub-router, fix the test to patch via the original module path (which still works because `_compat` re-exports).

- [ ] **Step 4: No commit yet — wait for all three sub-routers to migrate**

### Task 4: Move leaders routes

Same pattern as Task 3. Cut leaders-bucket routes from `industry.py`, paste into `leaders.py`.

- [ ] **Step 1: Move leaders routes**
- [ ] **Step 2: Run leaders-scoped tests: `pytest tests/unit -q -k "leader" 2>&1 | tail -10`**
- [ ] **Step 3: Fix any breakage**

### Task 5: Move rotation routes

Same pattern. Move all remaining routes (rotation bucket = catch-all) to `rotation.py`.

- [ ] **Step 1: Move rotation routes**
- [ ] **Step 2: Run rotation-scoped tests: `pytest tests/unit -q -k "rotation or rank or sector or trend or cluster or preference" 2>&1 | tail -10`**
- [ ] **Step 3: Fix any breakage**

### Task 6: Replace `industry.py` with package init shim

**Files:**
- Modify: `backend/app/api/v1/endpoints/industry.py` → delete (replaced by package directory)

- [ ] **Step 1: Verify `industry.py` is now empty of routes**

```bash
grep -cE '^@router\.' backend/app/api/v1/endpoints/industry.py
# Expected: 0
```

- [ ] **Step 2: Delete the file**

```bash
git rm backend/app/api/v1/endpoints/industry.py
```

The package `industry/` (directory) takes precedence — `from backend.app.api.v1.endpoints import industry` resolves to the package's `__init__.py`.

- [ ] **Step 3: Run full industry test suite**

```bash
pytest tests/unit -q -k "industry or heatmap or leader or rotation" 2>&1 | tail -10
```

Expected: same pass count as baseline. Failures here = regression.

### Task 7: Verify API aggregator + commit Phase 1A

- [ ] **Step 1: Confirm `api.py` aggregator still mounts industry**

```bash
grep -n "industry" backend/app/api/v1/api.py
```

If it imports `from .endpoints.industry import router`, that still resolves. No change needed.

- [ ] **Step 2: Smoke-test API startup**

```bash
python -c "from backend.main import app; print('routes:', len([r for r in app.routes]))"
```

Expected: prints a route count. If the import errors, check for circular imports between `_compat.py` and the runtime service.

- [ ] **Step 3: Run full backend regression**

```bash
pytest tests/unit tests/integration -q -m "not perf" 2>&1 | tail -10
```

Expected: pass count >= baseline.

- [ ] **Step 4: Commit Phase 1A**

```bash
git add backend/app/api/v1/endpoints/industry/ backend/app/api/v1/endpoints/industry.py
git commit -m "$(cat <<'EOF'
refactor(industry): split 1,676-line endpoint into sub-router package

Three sub-routers (heatmap / leaders / rotation) under the same
/industry prefix. Test-patch monkeypatch surface preserved via
deprecated _compat module. No API changes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## PHASE 1B — Rename JSX-bearing `.js` to `.jsx` (parallel-safe with 1A)

### Task 8: Inventory and rename

**Files:** all `frontend/src/**/*.js` files containing JSX (excluding `__tests__/`)

- [ ] **Step 1: Generate the rename list**

```bash
cd frontend
find src -name "*.js" ! -path "*/__tests__/*" -exec grep -lE 'return\s*\(?\s*<[A-Z]|<\/?[A-Z][a-zA-Z]*' {} \; > /tmp/jsx-rename-list.txt
wc -l /tmp/jsx-rename-list.txt
# Expected: ~71 files (verify count)
```

- [ ] **Step 2: Bulk-rename via `git mv` to preserve history**

```bash
cd frontend
while IFS= read -r f; do
  git mv "$f" "${f%.js}.jsx"
done < /tmp/jsx-rename-list.txt
```

- [ ] **Step 3: Find and update explicit-`.js` imports**

```bash
cd frontend
grep -rEn "from ['\"]\\..*\\.js['\"]" src 2>/dev/null
```

For each match where the imported file was renamed, change `.js` → `.jsx` in the import statement.

```bash
# Example: if grep found `from './Foo.js'` and Foo was renamed to Foo.jsx:
# Edit the file to change the import to `from './Foo.jsx'`
# Most imports omit the extension, so this should be a small list (under 10).
```

- [ ] **Step 4: Drop the esbuild jsx loader workaround**

Edit `frontend/vite.config.js`: remove the `esbuild: { loader: "jsx", include: /src\/.*\.js$/ }` block (or the equivalent) and the optimizeDeps `loader` override if present.

```bash
grep -n "loader.*jsx" frontend/vite.config.js
# After edit: should print nothing
```

- [ ] **Step 5: Run frontend tests**

```bash
cd frontend
CI=1 npm test -- --reporter=basic --pool=forks --poolOptions.forks.singleFork=true src/__tests__ 2>&1 | tail -10
```

Expected: pass count >= baseline. Failures usually mean a missed import update — re-run grep from Step 3.

- [ ] **Step 6: Run frontend build**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds. Errors like "Cannot find module './Foo.js'" mean a missed import path update.

- [ ] **Step 7: Commit Phase 1B**

```bash
git add frontend/
git commit -m "$(cat <<'EOF'
refactor(frontend): rename JSX-bearing .js files to .jsx

71 files renamed via git mv (history preserved). Explicit .js imports
updated. esbuild { loader: jsx } workaround dropped from vite.config.js
since Vite now resolves JSX from extension.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## PHASE 2 — Type all endpoint exceptions

### Task 9: Audit `except Exception` blocks across endpoints

- [ ] **Step 1: Generate the audit list**

```bash
grep -rnE 'except\s+Exception\s+as\s+\w+:' backend/app/api/v1/endpoints/ > /tmp/except-audit.txt
wc -l /tmp/except-audit.txt
```

- [ ] **Step 2: For each match, decide the typed replacement**

Decision matrix (apply uniformly across all endpoints):

| Pattern in current code | Replace with |
|---|---|
| Catches around `data_manager.get_*` or provider calls | `DataFetchError(symbol=...)` |
| Catches around Redis / Celery / SQLAlchemy | `ExternalServiceError(service="redis"/"celery"/"db")` |
| Catches around input parsing / validation | `ValidationError(message=..., details=...)` |
| Catches around `repo.get_by_id` returning None | `NotFoundError(resource="...", identifier=...)` |
| Catches around rate-limit checks | `RateLimitError(retry_after=...)` |
| Catches that just log + re-raise generic 500 | `AppException(message=str(e), error_code=...)` (NOT silently swallowed; raise from e) |

**Hard rule:** No `except Exception:` block may end with `return JSONResponse(status_code=500, ...)` or `pass`. Every catch either: (a) raises a typed exception (the middleware in `error_handler.py` will format the response) or (b) re-raises with `raise AppException(...) from e`.

### Task 10: Type `system.py` (smallest endpoint, low risk — start here)

**Files:** `backend/app/api/v1/endpoints/system.py` (275 lines)

- [ ] **Step 1: Read the current file end-to-end** (`Read backend/app/api/v1/endpoints/system.py`)

- [ ] **Step 2: For each `except Exception as e:`, replace with the typed equivalent per the matrix in Task 9, Step 2**

Example transformation:

```python
# Before
try:
    cache_status = await get_cache_health()
except Exception as e:
    logger.error(f"cache health check failed: {e}")
    return {"status": "error", "message": str(e)}

# After
try:
    cache_status = await get_cache_health()
except (ConnectionError, TimeoutError) as e:
    raise ExternalServiceError(service="redis", message=str(e)) from e
```

Add the import at top:

```python
from backend.app.core.error_handler import (
    AppException,
    DataFetchError,
    ExternalServiceError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
```

- [ ] **Step 3: Verify no `except Exception` left in system.py**

```bash
grep -cE 'except\s+Exception' backend/app/api/v1/endpoints/system.py
# Expected: 0
```

- [ ] **Step 4: Run system tests**

```bash
pytest tests/unit -q -k "system or health" 2>&1 | tail -10
```

Expected: pass count >= baseline. If a test asserted the old `{"status": "error"}` response shape, update it to assert the new error-handler shape (`{"success": false, "error": {"code": ..., "message": ...}}`).

### Task 11: Type `backtest.py`, `analysis.py`, `optimization.py`

Apply the same pattern as Task 10 to each file in turn. After each:

- [ ] **`backtest.py` — type, run `pytest tests/unit -q -k backtest 2>&1 | tail -10`, fix breaks**
- [ ] **`analysis.py` — type, run `pytest tests/unit -q -k analysis 2>&1 | tail -10`, fix breaks**
- [ ] **`optimization.py` — type, run `pytest tests/unit -q -k optimization 2>&1 | tail -10`, fix breaks**

### Task 12: Type remaining endpoints

**Files:** `cross_market.py`, `paper_trading.py`, `realtime.py`, `market_data.py`, `events.py`, `infrastructure.py`, `policy_radar.py`, `research_journal.py`, `strategies.py`, `trading.py`, plus the three industry sub-routers from Phase 1A.

- [ ] **Step 1: For each file, apply the typing transformation from Task 10**

- [ ] **Step 2: Verify**

```bash
grep -rcE 'except\s+Exception\s+as\s+\w+:' backend/app/api/v1/endpoints/
```

Expected: each file shows `0` (or the file isn't listed).

### Task 13: Verify error-response compatibility with frontend

**Files:** `frontend/src/components/ErrorBoundary.jsx`, `frontend/src/services/api.js`

- [ ] **Step 1: Read `frontend/src/services/api.js`** — confirm error-response parsing

The existing `error_handler.py` returns:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "...",
    "timestamp": "...",
    "details": {...}
  }
}
```

If `api.js` previously parsed `response.data.error` as a plain string (legacy shape), it must handle the new object shape. Look for response error handling.

- [ ] **Step 2: If frontend parsing is incompatible, add a thin compatibility layer**

Either: (a) update `api.js` to read `error.message` (preferred) or (b) keep both shapes by having the error handler middleware also include a flat `message` field at the top level.

If (b), edit `backend/app/core/error_handler.py:create_error_response` to add `"message": message` at the top level alongside `"error"`. Update tests asserting the response shape.

- [ ] **Step 3: Run frontend tests + build**

```bash
cd frontend && CI=1 npm test -- --reporter=basic --pool=forks --poolOptions.forks.singleFork=true src/__tests__ 2>&1 | tail -10
cd frontend && npm run build 2>&1 | tail -5
```

Expected: pass + build succeed.

### Task 14: Phase 2 verification + commit

- [ ] **Step 1: Full backend regression**

```bash
pytest tests/unit tests/integration -q -m "not perf" 2>&1 | tail -10
```

- [ ] **Step 2: Full frontend regression**

```bash
cd frontend && CI=1 npm test -- --reporter=basic --pool=forks --poolOptions.forks.singleFork=true src/__tests__ 2>&1 | tail -10
```

- [ ] **Step 3: Smoke API health endpoint**

```bash
python scripts/start_backend.py &
BACKEND_PID=$!
sleep 5
curl -fsS http://localhost:8000/health | head -3
curl -fsS http://localhost:8000/api/v1/system/info | head -3
# Hit a known-error path (invalid symbol) — expect typed error response
curl -s http://localhost:8000/api/v1/realtime/quote?symbol=INVALID-SYM-X | head -5
kill $BACKEND_PID
```

Expected: error response is `{"success": false, "error": {"code": "...", ...}}`, not a generic 500.

- [ ] **Step 4: Commit Phase 2**

```bash
git add backend/app/api/v1/endpoints/ backend/app/core/error_handler.py frontend/src/services/api.js
git commit -m "$(cat <<'EOF'
refactor(errors): replace broad except Exception with typed exceptions

All API endpoints now raise typed exceptions from error_handler.py
(ValidationError, NotFoundError, ExternalServiceError, DataFetchError,
RateLimitError, AppException). Middleware formats responses uniformly.
Frontend api.js updated to handle the structured error envelope.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## PHASE 3A — Add 4 gap-filling integration tests

### Task 15: `test_paper_order_lifecycle.py` — paper trading order state machine

**Files:** Create `tests/integration/test_paper_order_lifecycle.py`

- [ ] **Step 1: Read existing paper-trading service to identify entry points**

```bash
grep -nE '^(def|class) ' backend/app/services/paper_trading.py | head -30
```

Capture the public functions: profile creation, order placement, order cancellation, position lookup, archive-to-research-journal.

- [ ] **Step 2: Write the integration test**

```python
"""Paper-trading order lifecycle integration test.

Exercises: create profile → place limit order → trigger price hit →
verify fill → archive position. Touches services/paper_trading.py
and src/trading/. Uses tmp_path for profile persistence (no Redis).
"""
from __future__ import annotations

import pytest
from decimal import Decimal

from backend.app.services.paper_trading import (
    create_profile,
    place_order,
    cancel_order,
    list_positions,
    archive_position_to_journal,
)


@pytest.fixture
def isolated_paper_state(tmp_path, monkeypatch):
    """Redirect paper-trading persistence to tmp_path for test isolation."""
    monkeypatch.setenv("PAPER_TRADING_DATA_DIR", str(tmp_path))
    yield tmp_path


def test_full_order_lifecycle(isolated_paper_state):
    profile = create_profile(name="test", starting_cash=Decimal("100000"))
    assert profile.cash == Decimal("100000")

    order = place_order(
        profile_id=profile.id,
        symbol="AAPL",
        side="buy",
        order_type="limit",
        quantity=10,
        limit_price=Decimal("150.00"),
    )
    assert order.status == "pending"

    # simulate price hit
    fill = order.try_fill(market_price=Decimal("149.50"))
    assert fill is not None
    assert fill.status == "filled"

    positions = list_positions(profile_id=profile.id)
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"

    journal_id = archive_position_to_journal(
        profile_id=profile.id, position_id=positions[0].id
    )
    assert journal_id is not None


def test_limit_order_cancel(isolated_paper_state):
    profile = create_profile(name="cancel-test", starting_cash=Decimal("50000"))
    order = place_order(
        profile_id=profile.id, symbol="MSFT", side="buy",
        order_type="limit", quantity=5, limit_price=Decimal("300.00"),
    )
    cancel_order(profile_id=profile.id, order_id=order.id)
    assert order.status == "cancelled"


def test_market_order_immediate_fill(isolated_paper_state):
    profile = create_profile(name="market-test", starting_cash=Decimal("10000"))
    order = place_order(
        profile_id=profile.id, symbol="GOOG", side="buy",
        order_type="market", quantity=1, market_price=Decimal("2500"),
    )
    assert order.status == "filled"
    assert profile.cash < Decimal("10000")
```

**NOTE:** The exact API of `paper_trading.py` may differ. After Step 1, adapt function names and arg shapes to match. If `archive_position_to_journal` doesn't exist, find the actual function (search for `journal` in the service module) and use that.

- [ ] **Step 3: Run the test**

```bash
pytest tests/integration/test_paper_order_lifecycle.py -v 2>&1 | tail -20
```

Expected outcome: either PASS (test matches reality) or one of:

- **AttributeError on imported function** → adjust to actual API (Step 1 result)
- **Assertion failure** → either the test's expectation is wrong (fix the test) or there's a real bug (note in commit, fix separately)

- [ ] **Step 4: Iterate until tests pass — do NOT commit yet**

### Task 16: `test_industry_heatmap_cache.py` — heatmap cache state machine

**Files:** Create `tests/integration/test_industry_heatmap_cache.py`

- [ ] **Step 1: Read `src/data/cache_manager.py` to learn its API**

- [ ] **Step 2: Read `backend/app/services/industry/runtime.py` for cache-key conventions**

- [ ] **Step 3: Write the test**

```python
"""Industry heatmap cache state machine integration test.

Exercises: cold-cache miss (computes), warm-cache hit (skips compute),
TTL expiry (recomputes), disk-snapshot reload (after process restart).
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from backend.app.services.industry import runtime as industry_runtime


@pytest.fixture
def fresh_cache(monkeypatch, tmp_path):
    """Reset module-level caches and redirect disk persistence to tmp_path."""
    monkeypatch.setattr(industry_runtime, "_endpoint_cache", {})
    monkeypatch.setattr(industry_runtime, "_heatmap_history", [])
    monkeypatch.setenv("INDUSTRY_DATA_DIR", str(tmp_path))
    yield tmp_path


def test_cold_cache_computes(fresh_cache):
    with patch.object(
        industry_runtime, "_load_live_heatmap_response",
        wraps=industry_runtime._load_live_heatmap_response
    ) as spy:
        result = industry_runtime._get_endpoint_cache("heatmap:default")
        assert result is None  # cache miss
        # caller would then compute + set; we simulate that
        industry_runtime._set_endpoint_cache("heatmap:default", {"data": "live"}, ttl=60)
        cached = industry_runtime._get_endpoint_cache("heatmap:default")
        assert cached == {"data": "live"}


def test_warm_cache_returns_without_compute(fresh_cache):
    industry_runtime._set_endpoint_cache("heatmap:warm", {"data": "cached"}, ttl=60)
    result = industry_runtime._get_endpoint_cache("heatmap:warm")
    assert result == {"data": "cached"}


def test_ttl_expiry_triggers_recompute(fresh_cache):
    industry_runtime._set_endpoint_cache("heatmap:ttl", {"data": "old"}, ttl=1)
    time.sleep(1.5)
    result = industry_runtime._get_endpoint_cache("heatmap:ttl")
    assert result is None  # expired


def test_disk_snapshot_reload(fresh_cache, tmp_path):
    """After a process 'restart' (clearing in-memory state), disk snapshot
    should restore heatmap history."""
    industry_runtime._append_heatmap_history({"timestamp": "2026-05-06", "data": "x"})
    industry_runtime._persist_heatmap_history_to_disk()

    # Simulate restart
    industry_runtime._heatmap_history.clear()
    industry_runtime._heatmap_history_loaded.clear()

    industry_runtime._load_heatmap_history_from_disk()
    assert len(industry_runtime._heatmap_history) >= 1
```

**NOTE:** The functions referenced here are private (`_set_endpoint_cache`, `_get_endpoint_cache`, etc.) — they exist per the `_compat` shim in industry/__init__.py. If exact signatures differ, adapt.

- [ ] **Step 4: Run + iterate**

```bash
pytest tests/integration/test_industry_heatmap_cache.py -v 2>&1 | tail -20
```

### Task 17: `test_realtime_websocket_lifecycle.py` — WebSocket end-to-end

**Files:** Create `tests/integration/test_realtime_websocket_lifecycle.py`

- [ ] **Step 1: Read `backend/app/websocket/` for WS handler entry points**

- [ ] **Step 2: Read `src/data/realtime_manager.py` for subscription / broadcast API**

- [ ] **Step 3: Write the test using FastAPI TestClient WebSocket support**

```python
"""Realtime WebSocket lifecycle integration test.

Exercises: connect → subscribe → receive broadcast → multi-client
broadcast fanout → unsubscribe → disconnect. No external data
providers — broadcasts are injected via RealtimeManager.publish().
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from src.data.realtime_manager import RealtimeManager


@pytest.fixture
def client():
    return TestClient(app)


def test_single_client_subscribe_receive(client):
    with client.websocket_connect("/ws/realtime") as ws:
        ws.send_json({"action": "subscribe", "symbols": ["AAPL"]})
        ack = ws.receive_json()
        assert ack.get("status") == "subscribed"

        # Inject a quote broadcast
        manager = RealtimeManager.get_instance()
        manager.publish("AAPL", {"price": 150.0, "ts": 1234567890})

        msg = ws.receive_json()
        assert msg["symbol"] == "AAPL"
        assert msg["price"] == 150.0


def test_multi_client_broadcast_fanout(client):
    with client.websocket_connect("/ws/realtime") as ws_a, \
         client.websocket_connect("/ws/realtime") as ws_b:
        ws_a.send_json({"action": "subscribe", "symbols": ["MSFT"]})
        ws_b.send_json({"action": "subscribe", "symbols": ["MSFT"]})
        ws_a.receive_json()  # ack
        ws_b.receive_json()  # ack

        manager = RealtimeManager.get_instance()
        manager.publish("MSFT", {"price": 300.0, "ts": 1234567891})

        msg_a = ws_a.receive_json()
        msg_b = ws_b.receive_json()
        assert msg_a["symbol"] == "MSFT" == msg_b["symbol"]
        assert msg_a["price"] == 300.0 == msg_b["price"]


def test_unsubscribe_stops_receiving(client):
    with client.websocket_connect("/ws/realtime") as ws:
        ws.send_json({"action": "subscribe", "symbols": ["GOOG"]})
        ws.receive_json()  # ack

        ws.send_json({"action": "unsubscribe", "symbols": ["GOOG"]})
        ws.receive_json()  # ack

        manager = RealtimeManager.get_instance()
        manager.publish("GOOG", {"price": 2500.0, "ts": 1234567892})

        # No message should arrive — use a short timeout via receive_json
        # If TestClient doesn't support timeout, send a ping and expect ack only
        ws.send_json({"action": "ping"})
        msg = ws.receive_json()
        assert msg.get("type") == "pong" or msg.get("action") == "ping"
```

**NOTE:** WS API names (`subscribe`/`publish`/`get_instance`) are guesses. Adapt to actual signatures from Steps 1–2. If `RealtimeManager` is not a singleton, look for the connection-manager singleton in `backend/app/websocket/connection_manager.py` or similar.

- [ ] **Step 4: Run + iterate**

```bash
pytest tests/integration/test_realtime_websocket_lifecycle.py -v 2>&1 | tail -20
```

### Task 18: `test_research_journal_persistence.py` — journal disk round-trip

**Files:** Create `tests/integration/test_research_journal_persistence.py`

- [ ] **Step 1: Read research-journal service for write/list/archive entry points**

```bash
grep -nE '^(def|class) ' backend/app/services/research_journal.py 2>/dev/null || \
grep -rn "research_journal" backend/app/services/ | head -10
```

- [ ] **Step 2: Write the test**

```python
"""Research-journal persistence integration test.

Exercises: snapshot write → list → read → archive → delete
with disk round-trip via tmp_path. Different from
test_research_journal_contracts.py (which only validates schemas).
"""
from __future__ import annotations

import pytest

from backend.app.services.research_journal import (
    write_snapshot,
    list_snapshots,
    read_snapshot,
    archive_snapshot,
    delete_snapshot,
)


@pytest.fixture
def isolated_journal(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_JOURNAL_DATA_DIR", str(tmp_path))
    yield tmp_path


def test_snapshot_write_read_round_trip(isolated_journal):
    snap_id = write_snapshot(
        kind="backtest",
        title="MA crossover on AAPL",
        payload={"strategy": "ma_cross", "symbol": "AAPL", "sharpe": 1.4},
    )
    assert snap_id

    # Should appear in list
    snaps = list_snapshots(kind="backtest")
    assert any(s.id == snap_id for s in snaps)

    # Read by ID returns same payload
    snap = read_snapshot(snap_id)
    assert snap.payload["strategy"] == "ma_cross"
    assert snap.payload["sharpe"] == 1.4


def test_archive_then_delete(isolated_journal):
    snap_id = write_snapshot(
        kind="backtest", title="to-archive",
        payload={"sharpe": 0.5},
    )
    archive_snapshot(snap_id)
    snap = read_snapshot(snap_id)
    assert snap.archived is True

    delete_snapshot(snap_id)
    with pytest.raises(Exception):  # NotFoundError after typed-exception sweep
        read_snapshot(snap_id)


def test_list_filters_by_kind(isolated_journal):
    write_snapshot(kind="backtest", title="bt", payload={})
    write_snapshot(kind="alert", title="a1", payload={})
    write_snapshot(kind="alert", title="a2", payload={})

    bts = list_snapshots(kind="backtest")
    alerts = list_snapshots(kind="alert")
    assert len(bts) == 1
    assert len(alerts) == 2
```

**NOTE:** Function names are placeholders — adapt to the actual service API found in Step 1.

- [ ] **Step 3: Run + iterate**

```bash
pytest tests/integration/test_research_journal_persistence.py -v 2>&1 | tail -20
```

### Task 19: All-tests verification before mypy phase

- [ ] **Step 1: Run full integration suite**

```bash
pytest tests/integration -q -m "not perf" 2>&1 | tail -10
```

Expected: 4 new test files all passing. Pre-existing tests still passing.

---

## PHASE 3B — Expand mypy CI blocking scope

### Task 20: Run mypy on `src/backtest/` locally

- [ ] **Step 1: Run mypy on the directory**

```bash
mypy --explicit-package-bases --namespace-packages --follow-imports=silent src/backtest/ 2>&1 | tee /tmp/mypy-backtest.txt | tail -20
```

- [ ] **Step 2: Count errors**

```bash
grep -cE '^src/backtest/.*:.*: error:' /tmp/mypy-backtest.txt
```

- [ ] **Step 3: Decide expansion vs defer**

- If error count ≤ 20 → fix in-place (next step).
- If error count > 20 but ≤ 50 → fix the obvious wins (missing return type annotations, easy `Optional[X]` for `None`-defaulted args), then promote.
- If error count > 50 → keep `src/backtest/` in non-blocking probe; document why in a follow-up.

- [ ] **Step 4: Fix errors (if applicable)**

Common fixes:
- Add return type annotations: `def foo(x):` → `def foo(x: int) -> bool:`
- Add `Optional` to None-defaulted params: `def foo(x=None):` → `def foo(x: Optional[int] = None):`
- Fix `Union` returns: explicitly annotate when a function can return `Union[X, None]`

- [ ] **Step 5: Re-run mypy until clean**

```bash
mypy --explicit-package-bases --namespace-packages --follow-imports=silent src/backtest/ 2>&1 | tail -5
# Expected: "Success: no issues found in N source files"
```

### Task 21: Run mypy on `src/data/realtime_manager.py`

- [ ] **Step 1: Same approach as Task 20**

```bash
mypy --explicit-package-bases --namespace-packages --follow-imports=silent src/data/realtime_manager.py 2>&1 | tee /tmp/mypy-realtime.txt | tail -10
```

- [ ] **Step 2: Fix or defer per same threshold rules**

### Task 22: Run mypy on services modules

**Targets:** `backend/app/services/realtime_alerts.py`, `backend/app/services/preferences.py`, `backend/app/services/runtime_state.py`

- [ ] **Step 1: Run mypy on all three**

```bash
mypy --explicit-package-bases --namespace-packages --follow-imports=silent \
  backend/app/services/realtime_alerts.py \
  backend/app/services/preferences.py \
  backend/app/services/runtime_state.py \
  2>&1 | tee /tmp/mypy-services.txt | tail -20
```

- [ ] **Step 2: Fix or defer per same threshold rules**

### Task 23: Update CI mypy blocking step

**Files:** `.github/workflows/ci.yml` (the typecheck job at lines 47–78)

- [ ] **Step 1: Edit the "Mypy on clean modules (must pass)" step**

```yaml
      - name: Mypy on clean modules (must pass)
        run: |
          mypy --explicit-package-bases --namespace-packages --follow-imports=silent \
            src/analytics/technical_indicators.py \
            src/analytics/industry/ \
            src/backtest/ \
            src/data/realtime_manager.py \
            backend/app/services/realtime_alerts.py \
            backend/app/services/preferences.py \
            backend/app/services/runtime_state.py
```

(Drop any modules deferred in Tasks 20–22; only include modules that were brought to clean state.)

- [ ] **Step 2: Re-run mypy locally with the exact CI command**

```bash
mypy --explicit-package-bases --namespace-packages --follow-imports=silent \
  src/analytics/technical_indicators.py \
  src/analytics/industry/ \
  src/backtest/ \
  src/data/realtime_manager.py \
  backend/app/services/realtime_alerts.py \
  backend/app/services/preferences.py \
  backend/app/services/runtime_state.py 2>&1 | tail -5
# Expected: Success
```

### Task 24: Phase 3 verification + commit

- [ ] **Step 1: Full backend regression**

```bash
pytest tests/unit tests/integration -q -m "not perf" 2>&1 | tail -10
```

- [ ] **Step 2: Mypy must-pass step**

```bash
# Same command as Task 23 Step 2
```

- [ ] **Step 3: Commit Phase 3**

```bash
git add tests/integration/ .github/workflows/ci.yml src/backtest/ src/data/realtime_manager.py backend/app/services/
git commit -m "$(cat <<'EOF'
test+types: integration test gaps + expand mypy blocking scope

Integration tests added:
- test_paper_order_lifecycle.py
- test_industry_heatmap_cache.py
- test_realtime_websocket_lifecycle.py
- test_research_journal_persistence.py

Mypy blocking scope expanded to: src/backtest/, realtime_manager,
and the realtime_alerts/preferences/runtime_state services.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## PHASE 4 — Final regression

### Task 25: Full local CI dry-run

- [ ] **Step 1: Run every CI job's command locally in sequence**

```bash
# backend job
pytest tests/unit tests/integration -q -m "not perf" --cov=src --cov=backend --cov-report=xml 2>&1 | tail -10

# typecheck job (must-pass step)
mypy --explicit-package-bases --namespace-packages --follow-imports=silent \
  src/analytics/technical_indicators.py \
  src/analytics/industry/ \
  src/backtest/ \
  src/data/realtime_manager.py \
  backend/app/services/realtime_alerts.py \
  backend/app/services/preferences.py \
  backend/app/services/runtime_state.py 2>&1 | tail -5

# frontend job
cd frontend && npm ci --legacy-peer-deps && \
  CI=1 npm test -- --reporter=basic --pool=forks --poolOptions.forks.singleFork=true src/__tests__ 2>&1 | tail -10 && \
  npm run build 2>&1 | tail -5
cd ..
```

Expected: every command exits 0.

- [ ] **Step 2: Optional — local e2e (skip if no port-3000 / port-8000 capacity)**

```bash
./scripts/start_system.sh --force-port-cleanup &
sleep 10
curl -fsS http://localhost:3000 >/dev/null && curl -fsS http://localhost:8000/health >/dev/null && echo "stack up"
./scripts/stop_system.sh
```

### Task 26: Push branch (DO NOT merge to main)

- [ ] **Step 1: Verify branch has 4 commits ahead of main**

```bash
git log --oneline main..HEAD
# Expected: 4 commits (spec + 3 batch commits + this final summary commit if any)
```

- [ ] **Step 2: Push**

```bash
git push -u origin cleanup/v5.0.x-tech-debt
```

- [ ] **Step 3: Surface PR-creation question to user**

User decides whether to open a PR or merge locally. **Do not auto-create a PR or merge to main without explicit user approval** — this is a destructive cross-stakeholder action per the instruction-priority guidance.

---

## Acceptance Verification (run before declaring done)

- [ ] `pytest tests/unit tests/integration -q -m "not perf"` exits 0
- [ ] `cd frontend && npm test` exits 0
- [ ] Mypy must-pass command (Task 23) exits 0
- [ ] `cd frontend && npm run build` exits 0
- [ ] `industry.py` (file) does not exist; `industry/` (package) exists with three sub-routers
- [ ] `grep -rcE 'except\s+Exception\s+as\s+\w+:' backend/app/api/v1/endpoints/` shows 0 across the directory
- [ ] 4 new integration test files exist and pass
- [ ] `frontend/vite.config.js` no longer has `esbuild: { loader: "jsx" }`
- [ ] `find frontend/src -name "*.js" ! -path "*/__tests__/*" -exec grep -lE 'return\s*\(?\s*<[A-Z]' {} \;` returns no files

---

## Out-of-Scope Reminders (do NOT do these)

- Refactoring `tests/unit/test_industry_*.py` to remove monkeypatch reliance
- DB-backed integration tests (no test seed harness yet)
- Typing `backend/app/api/v1/endpoints/*` (deferred — touched too heavily this round)
- Renaming non-JSX `.js` to `.ts` / `.tsx`
- Reducing `--legacy-peer-deps` in CI
- **Docker / docker-compose / containerization** (out of repo scope per user)
