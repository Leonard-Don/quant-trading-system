# Evaluation Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address all 7 red flags from the 2026-05-05 project evaluation: print→logger, mypy in CI, large endpoint→service extraction, large module split, Alembic introduction, deployment doc clarity, and CRA→Vite migration.

**Architecture:** The repo already has clean `src/` (algo) ↔ `backend/` (API) separation. This plan tightens existing seams rather than redesigning: extract inline indicator math out of `analysis.py` into `src/analytics/technical_indicators.py`; split `IndustryAnalyzer` god-class along its existing internal boundaries (cache / momentum / volatility / clustering); keep `sina_ths_adapter.py` whole for now (proxy/THS-fallback logic is too coupled for a safe in-session split — flag as follow-up). Backend gets Alembic with the existing TimescaleDB DDL as baseline. Frontend stays on CRA in this pass — Vite migration is scoped as a separate plan.

**Tech Stack:** Python 3.13, FastAPI, pandas, ruff/black/mypy, pytest, Alembic 1.16, React 18 (CRA), GitHub Actions.

---

## Scope notes (vs. original 7-item list)

After re-reading the actual code, three items shrink:

- **Item 3 (print()):** 49 hits, but ~33 are inside `Backtester.print_results()` (intentional CLI output) and ~14 are inside `if __name__ == "__main__":` demo blocks at file bottoms. These are not code smells. Leaving them.
- **Item 2 (endpoint god files):** `industry.py` (1676 lines) is already ~95% thin wrapper passthroughs to `_industry_helpers`. Real target is `analysis.py` where `_calculate_rsi/_calculate_macd/_calculate_bollinger` live inline.
- **Item 5 (Vite migration):** Genuinely multi-hour with regression risk on 195-file React app. Out of scope for this plan; documented as separate follow-up.

Items kept in scope: 1 (split god-class), 2 (extract indicator math), 4 (mypy in CI), 6 (Alembic), 7 (deploy docs), plus a smaller item 3 (just the policy_crawler demo block — it's not a `__main__` guard, it's loose at module scope).

---

## Task 1: Promote `_calculate_rsi/_calculate_macd/_calculate_bollinger` to `src/analytics/`

**Why:** These compute technical indicators on a DataFrame with no FastAPI / request coupling. They belong in `src/analytics/`, not in a 1239-line route file.

**Files:**
- Create: `src/analytics/technical_indicators.py`
- Modify: `backend/app/api/v1/endpoints/analysis.py:697-803` (replace local defs with import + delete)
- Test: `tests/unit/analytics/test_technical_indicators.py`

- [ ] **Step 1: Create the new module by lifting code verbatim**

Move the three functions (`_calculate_rsi` lines 697-723, `_calculate_macd` lines 724-762, `_calculate_bollinger` lines 763-802) into `src/analytics/technical_indicators.py`. Strip the leading underscore — they're now public. Keep return shape identical.

- [ ] **Step 2: Replace inline calls in `analysis.py`**

Change `result = _calculate_rsi(data, ...)` to `result = calculate_rsi(data, ...)` and add `from src.analytics.technical_indicators import calculate_rsi, calculate_macd, calculate_bollinger` near the top.

- [ ] **Step 3: Add a smoke test**

```python
import pandas as pd, numpy as np
from src.analytics.technical_indicators import calculate_rsi, calculate_macd, calculate_bollinger

def test_indicators_return_expected_shape():
    df = pd.DataFrame({"close": np.linspace(100, 110, 30)})
    rsi = calculate_rsi(df)
    macd = calculate_macd(df)
    bb = calculate_bollinger(df)
    assert "current_rsi" in rsi or "rsi" in rsi  # match actual key
    assert "macd" in macd or "current_macd" in macd
    assert "upper" in bb or "bollinger_upper" in bb
```

(Read the original code to confirm exact key names before writing the assertions.)

- [ ] **Step 4: Run the focused test + the existing analysis integration**

```bash
pytest tests/unit/analytics/test_technical_indicators.py tests/integration/test_analysis_endpoints.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/analytics/technical_indicators.py backend/app/api/v1/endpoints/analysis.py tests/unit/analytics/test_technical_indicators.py
git commit -m "refactor(analytics): extract RSI/MACD/Bollinger from analysis endpoint"
```

---

## Task 2: Split `IndustryAnalyzer` god-class into focused modules

**Files:**
- Create: `src/analytics/industry/cache.py` (cache mixin or helper functions: `_get_cache_key`, `_update_cache`, `_get_from_cache`, `_get_stale_cache`, `_run_singleflight`, `_clear_cache`, `_is_cache_valid`)
- Create: `src/analytics/industry/volatility.py` (`_weighted_std`, `_ensure_industry_volatility`, `_apply_historical_volatility`, `calculate_industry_historical_volatility`)
- Create: `src/analytics/industry/money_flow.py` (`_merge_momentum_and_flow`, `_normalize_money_flow_dataframe`, `analyze_money_flow`, `_load_lightweight_money_flow`, `_try_sina_fallback`, `_momentum_from_money_flow_fallback`)
- Modify: `src/analytics/industry_analyzer.py` (becomes thin facade re-exporting `IndustryAnalyzer` that composes the helpers)

**Decision recorded:** keep the public class name `IndustryAnalyzer` and its method signatures unchanged so callers don't need to be touched. Internal methods become module-level helpers receiving `self`-extracted state explicitly.

- [ ] **Step 1: Confirm no callers reach into private methods**

```bash
grep -rn "IndustryAnalyzer()._" src backend tests
grep -rn "_calculate_rank_score_series\|_ensure_industry_volatility\|_normalize_money_flow_dataframe" src backend tests
```

If callers depend on private internals: stop and adjust the boundary.

- [ ] **Step 2: Create `src/analytics/industry/__init__.py` re-exporting nothing yet**

- [ ] **Step 3: Move cache plumbing to `src/analytics/industry/cache.py`**

Lift `_get_cache_key`, `_update_cache`, `_get_from_cache`, `_get_stale_cache`, `_run_singleflight`, `_clear_cache`, `_is_cache_valid` from `industry_analyzer.py` lines 182-269 + 485-487. Convert to free functions that take an explicit cache dict + lock as args. In `IndustryAnalyzer` keep instance methods that delegate.

- [ ] **Step 4: Move volatility logic to `src/analytics/industry/volatility.py`**

Lift `_weighted_std`, `_ensure_industry_volatility`, `_apply_historical_volatility`, `calculate_industry_historical_volatility` (lines 405-907 selectively). Same pattern: free functions, instance methods delegate.

- [ ] **Step 5: Move money-flow logic to `src/analytics/industry/money_flow.py`**

Lift the analyze_money_flow chain (lines 489-907 minus volatility).

- [ ] **Step 6: Run unit + integration tests**

```bash
pytest tests/unit/analytics tests/integration -k industry -q
```

- [ ] **Step 7: Commit**

```bash
git add src/analytics/industry_analyzer.py src/analytics/industry/
git commit -m "refactor(analytics): split IndustryAnalyzer into focused submodules"
```

---

## Task 3: Add mypy job to CI (non-blocking initially)

**Why:** mypy is installed and configured loose, but never runs in CI. Add it as a separate job that doesn't fail the build yet — gives us a baseline error count to drive down.

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `pyproject.toml` (tighten mypy config slightly)

- [ ] **Step 1: Inspect current mypy config**

```bash
grep -A20 "tool.mypy" pyproject.toml
```

- [ ] **Step 2: Add mypy job to CI**

Append after the `backend` job:

```yaml
  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: |
            requirements.txt
            requirements-dev.txt
      - run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt
      - name: Run mypy (non-blocking)
        continue-on-error: true
        run: mypy backend/app/services src/analytics/technical_indicators.py
```

The narrow target is intentional: start where it's likely to pass, expand outward. `continue-on-error: true` makes it informational.

- [ ] **Step 3: Run mypy locally to confirm it works**

```bash
mypy backend/app/services src/analytics/technical_indicators.py
```

Capture the error count for the commit message.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add non-blocking mypy job scoped to backend services + new analytics module"
```

---

## Task 4: Initialize Alembic with TimescaleDB schema as baseline

**Why:** `alembic==1.16.4` is in `requirements-dev.txt` but never initialized. Schema lives as a single `timescale_schema.sql` with no version tracking. Adding Alembic now (with the current schema as baseline) gives migrations going forward without disrupting anything live.

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/0001_baseline.py`
- Modify: `docs/DEPLOYMENT.md` (add migration section)

- [ ] **Step 1: Generate skeleton**

```bash
cd backend && alembic init alembic
```

- [ ] **Step 2: Wire `env.py` to use the existing config**

Edit `backend/alembic/env.py` to read DATABASE_URL from env (fallback to settings module).

- [ ] **Step 3: Write baseline migration that no-ops**

`0001_baseline.py` upgrade function: `pass` (assumes the DB is already at the schema in `timescale_schema.sql`). downgrade: `pass`. Comment notes that this stamps existing DBs as version 1.

- [ ] **Step 4: Document the bootstrap step**

In `docs/DEPLOYMENT.md`, add: "First-time setup on an existing DB: `cd backend && alembic stamp head`."

- [ ] **Step 5: Commit**

```bash
git add backend/alembic* docs/DEPLOYMENT.md
git commit -m "feat(db): introduce Alembic with current schema as baseline"
```

---

## Task 5: Clarify Celery/Redis as production-required in DEPLOYMENT.md

**Why:** Health check shows 4 warnings around Celery/Redis being absent. The current DEPLOYMENT.md doesn't mention them at all in the production section, leaving deployers to guess.

**Files:**
- Modify: `docs/DEPLOYMENT.md`

- [ ] **Step 1: Read existing deployment doc end to end**

- [ ] **Step 2: Add a "Production async task queue" section**

Cover: when Celery is required (any backtest >2s, multi-period, walk-forward, async industry refresh), how to start Redis (docker run hint), `scripts/start_celery_worker.sh`, env vars (`CELERY_BROKER_URL`, `REDIS_URL`).

- [ ] **Step 3: Commit**

```bash
git add docs/DEPLOYMENT.md
git commit -m "docs: clarify Celery/Redis are production-required for async tasks"
```

---

## Task 6: Trim policy_crawler module-level demo print

**Files:**
- Modify: `src/data/alternative/policy_radar/policy_crawler.py:143`

- [ ] **Step 1: Inspect lines 130-160**

Confirm whether the `print(f"[{p['date']}] {p['title']}")` is in a `__main__` guard or module-level. If module-level loose, replace with a logger call.

- [ ] **Step 2: Commit (only if change made)**

---

## Task 7: Vite migration — scoped out

**Decision recorded:** Out of scope for this plan. Reasons:
- Frontend has 195 files using `react-scripts`. CRA → Vite involves: new `vite.config.js`, env var convention change (`REACT_APP_*` → `VITE_*`), test runner switch (CRA uses Jest, Vite is Vitest-friendly), Playwright e2e sanity-pass, dev/prod build verification.
- Estimated 4-8 hours with non-trivial regression risk on the 5 production workspaces.

**Action:** Create a follow-up plan stub at `docs/superpowers/plans/followup-cra-to-vite.md` with the migration checklist.

---

## Self-review

- [x] All 7 evaluation items addressed: 1 (Task 2), 2 (Task 1), 3 (Task 6), 4 (Task 3), 5 (Task 7-stub), 6 (Task 4), 7 (Task 5)
- [x] No "TBD" placeholders — every task has concrete file paths and code intent
- [x] Test steps reference actual test paths and pytest invocations
- [x] Commit messages defined per task
- [x] Decision rationale captured for skipped/shrunk items (print, Vite, sina_ths_adapter)
