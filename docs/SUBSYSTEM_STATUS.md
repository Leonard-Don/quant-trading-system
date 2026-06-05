# Subsystem Status Audit

This document records the real, observed status of two backend subsystems that
are easy to misread as either duplicate or load-bearing: the **two simulated
trading layers** (`/trade/*` vs `/paper/*`) and the **auth / OAuth / users
subsystem** (`/infrastructure/auth/*`, `backend/app/core/auth/*`).

It is a *status* document, not a change. Nothing described here is being
modified, enforced, or deleted by the PR that introduces this file. The goal is
to stop future audits from re-discovering the same questions and to record the
recommended direction.

Last audited: 2026-06-05 (commit base `0ce5161`).

---

## 1. Trade vs Paper — two parallel simulated trading layers

> **✅ RESOLVED (2026-06-05) — consolidated and retired.** The parallelism
> described in this section has been eliminated. `TradePanel` was re-pointed at
> the persistent `/paper/*` engine (scoped to the realtime profile, poll-after-
> action replacing the trade WebSocket). `/trade/*` was first reduced to a
> deprecated compat shim, then **fully removed** along with its ephemeral engine
> (`src/trading/trade_manager.py`), the `/ws/trades` WebSocket stack
> (`trade_connection_manager.py`, `trade_stream.py`), the frontend
> `tradeWebsocket.js`, and their tests/registry entries. There is now a **single
> simulated-trading engine** (`backend/app/services/paper_trading.py`). The
> analysis below is retained as historical context for how the decision was made.

### Verdict (historical)

`/trade/*` and `/paper/*` *were* **two independent simulated-trading
implementations that coexisted**. Both were wired to the frontend, both had
tests, and they shared no state. They were **not** a built-but-dead pair. The
real issue was *unintentional parallelism* (two account models, two reset flows,
two storage strategies) — now consolidated onto `/paper/*`.

### Side-by-side map

| Aspect | `/trade/*` (legacy) | `/paper/*` (current) |
|--------|---------------------|----------------------|
| Router | `backend/app/api/v1/endpoints/trading.py`, prefix `/trade` | `backend/app/api/v1/endpoints/paper_trading.py`, prefix `/paper` |
| Engine | `src/trading/trade_manager.py` (`trade_manager`) | `backend/app/services/paper_trading.py` (`paper_trading_store`) |
| State model | **Process-global singleton** (`TradeManager.__new__` enforces one instance). One shared account for the whole server. | **Per-profile, file-backed.** One JSON ledger per `profile_id` under `data/paper_trading/`. Profile resolved from `X-Research-Profile` / `X-Realtime-Profile` / `profile_id` query (defaults to `default`). |
| Persistence | **None.** In-memory only; resets on restart. | JSON file per profile, `threading.RLock` for intra-process consistency (mirrors `ResearchJournalStore`). |
| Initial capital | `100000.0` (hardcoded) | `10000.0` default, overridable per reset request |
| Order semantics | Immediate fill at supplied/looked-up price; market BUY/SELL only; weighted-avg cost basis; rejects oversell / insufficient funds. | Immediate fill at user-supplied `fill_price`; supports pending LIMIT orders (cancelable) and a `pending_orders` field; per-position sell-exit handling; no bid/ask sim, no shorting, no leverage. |
| Realtime price lookup | Yes — `/trade/execute` falls back to `realtime_manager` / `data_manager` to source a price when none is supplied. | No — caller supplies `fill_price`; engine does not fetch quotes. |
| WebSocket broadcast | Yes — broadcasts `trade_executed` / `account_reset` via `trade_ws_manager`. | No WS broadcast. |
| Frontend caller | `frontend/src/components/TradePanel.jsx` (lazy-mounted inside `RealTimePanel.jsx`) via `getPortfolio` / `executeTrade` / `getTradeHistory` / `resetAccount` in `services/api.js`. | `frontend/src/components/PaperTradingPanel.jsx` (lazy-mounted in `App.jsx`, the `paper` route) via `/paper/account|orders|reset`. |
| Tests | `tests/unit/test_trade_manager.py`, `tests/unit/test_trading_endpoint.py`, `tests/unit/test_trade_stream.py` | `tests/unit/test_paper_trading.py`, `tests/unit/test_paper_trading_engine.py`, `tests/integration/test_paper_trading_lifecycle.py` |
| `route_surface_registry` entry | **None** — but it is *not* dead (has frontend + tests), so it correctly does not need a registry row. | None needed (frontend-wired). |

### What each is *for*, in practice

- **`/trade/*`** is the older "live-feeling" trading widget bolted onto the
  realtime panel: one shared paper account, server-global, with realtime price
  fill and WS push so the UI updates instantly. It behaves like a quick
  "execute against the live quote" toy. Because state is a process-global
  singleton with no persistence, it is single-user by construction and loses
  everything on restart.
- **`/paper/*`** is the newer, deliberately-scoped paper-trading workspace:
  per-profile, persisted, with order history and cancelable LIMIT orders. It is
  the surface the "send to paper" research flows target
  (`utils/paperTradingPrefill`, `TodayResearchDashboard`, `ResultsDisplay`).

So they overlap heavily in *intent* (both are simulated A-share trading) but
diverge in *architecture* (global+ephemeral vs per-profile+persisted) and in
*UX role* (inline realtime widget vs standalone workspace).

### Recommendation

**Consolidate toward `/paper/*`, but do not rush a removal.** The `/paper/*`
layer is the strictly more capable design (per-profile identity, persistence,
order history, LIMIT support, registry-aligned profile resolution). The
recommended sequence, for a *future* change set, is:

1. Re-point `TradePanel.jsx` at the `/paper/*` API (add the realtime-price
   auto-fill and WS broadcast behaviours to the paper layer if the inline widget
   still wants them), so there is a single account model.
2. Once nothing in the frontend calls `getPortfolio` / `executeTrade` /
   `getTradeHistory` / `resetAccount`, add a `route_surface_registry` row for
   `/trade/*` marking it `deprecated_compat` with a removal window.
3. After a compatibility window with no callers, retire `trading.py` +
   `src/trading/trade_manager.py` and their tests together.

**Do not** simply delete `/trade/*` today: it is reachable from the live UI
(`RealTimePanel` → `TradePanel`) and covered by unit tests. Deleting it now
would break the realtime trade widget and its suite.

If consolidation is declined, the alternative is to **keep both but document the
split explicitly** (this table) and rename for clarity — e.g. surface `/trade/*`
in docs as the "realtime quick-trade widget (global, ephemeral)" and `/paper/*`
as the "paper-trading workspace (per-profile, persisted)" so the parallelism is
intentional rather than accidental.

### Deletion / consolidation candidates (noted, NOT actioned)

- `/trade/*` + `trade_manager` are a **consolidation** candidate (fold into
  `/paper/*`), *not* a dead-code deletion candidate — they have a live frontend
  caller and tests. No action taken in this PR.

---

## 2. Auth / OAuth / Users — built but not enforced

### Verdict

The auth subsystem is **fully built but not enforced anywhere on the research
API**. The application is, in its default and shipped configuration,
**effectively unauthenticated** — which is appropriate for a single-user local
research tool. Calling it "secured" would be a false-security signal.

### Evidence

- **No research endpoint requires a user.** A grep of
  `backend/app/api/v1/endpoints/` for `Depends(get_current_user`,
  `Depends(require…`, `Security(`, etc. returns hits in exactly **one file**:
  `infrastructure.py` — and only on the auth subsystem's *own* admin endpoints.
  Every analysis / backtest / market-data / realtime / strategy / paper-trading
  / journal endpoint has **zero** auth dependency.
- **Even where a dependency exists, it is non-blocking.** The only dependency
  used is `get_current_user_optional` (`backend/app/core/auth/runtime.py`). Its
  contract:
  - If `API_KEY` is set *and* a matching `X-API-Key` header is sent → service
    user.
  - If a valid `Bearer` access token is sent → that user.
  - **Otherwise**, it returns an *anonymous* researcher
    (`{"sub": "anonymous", "role": "researcher", "auth_method": "optional"}`)
    *unless* `auth_required` policy is on.
- **`auth_required` defaults to off.** `get_auth_policy()["required"]` derives
  from `_env_auth_required()` (`backend/app/core/auth/secrets.py`), which reads
  `AUTH_REQUIRED` and defaults to **`False`**. With no env override, anonymous
  access is granted, so even the auth-aware infrastructure endpoints do not
  reject unauthenticated callers.
- **The frontend never logs in.** There is no token acquisition / `Authorization`
  header injection in the research data flows; the app works fully without
  credentials. All backend and frontend tests run unauthenticated.

### What is built

`backend/app/core/auth/` is a complete, real implementation —
`users.py` (local user directory), `tokens.py` (access/refresh tokens),
`oauth_flow.py` / `oauth_providers.py` / `oauth_states.py` (OAuth2 authorize /
exchange / callback), `policy.py`, `runtime.py`, `secrets.py`, `_crypto.py`. It
is exposed through ~15 `/infrastructure/auth/*` and `/infrastructure/oauth/*`
routes (token issue, login, refresh, user CRUD, OAuth provider CRUD, provider
authorize/exchange/callback, session revoke, policy update). These endpoints
*work* — they just gate nothing else, because nothing else depends on them.

### Is this a security hole?

No — **by design**, for a single-user local research tool. The risk is purely
*documentation drift*: someone reading "OAuth providers", "users", "refresh
sessions", "auth policy" could reasonably assume the API is access-controlled.
It is not. This document is the corrective record.

### `SECURITY.md` accuracy

`SECURITY.md` was reviewed. It is a **vulnerability-reporting policy only** —
supported versions plus a private-disclosure process. **It makes no claim that
the API is authenticated or access-controlled**, so there is no false-security
statement to correct there. No change to `SECURITY.md` is warranted by this
audit. (If `SECURITY.md` is ever expanded to describe runtime protections, it
must state that the API is unauthenticated by default and that auth is an
opt-in, non-enforced subsystem.)

### Decision (2026-06-05)

**Resolved by the product owner: this is a single-user local tool.** The auth /
OAuth / users subsystem stays **in place and non-enforced** (the "keep as opt-in"
stance below). It is **not** being deleted: `get_current_user_optional` is
load-bearing — it supplies the anonymous-researcher identity that endpoints read,
so removing the subsystem would mean unwinding that shim from every endpoint for
no benefit on a local tool. `AUTH_REQUIRED` stays `False`. Multi-user / login is
explicitly **out of scope** until that product decision changes.

### Recommendation

The decision above selected the first of the two stances originally laid out here
(kept for context):

- **Selected — keep as opt-in, document the switch.** Leave the subsystem
  in place, enforcement off by default. Document that setting `AUTH_REQUIRED=1`
  (optionally `API_KEY=…`) turns it on, and that turning it on **will break the
  no-login frontend and the test suite** until the frontend learns to
  authenticate. This makes the capability discoverable without pretending it is
  active.
- **Alternative — mark speculative.** If there is no near-term intent to enforce
  auth, label `backend/app/core/auth/*` and the `/infrastructure/auth|oauth/*`
  routes as a speculative/future subsystem in the route inventory so it is not
  mistaken for active protection.

**Do not enforce auth in this change** — flipping `AUTH_REQUIRED` on, or adding
`get_current_user` (non-optional) dependencies, would break the unauthenticated
frontend and every test. No deletion either; the subsystem is coherent and may
be wanted later.

### Deletion candidates (noted, NOT actioned)

- None recommended for deletion. The auth subsystem is internally consistent and
  is a plausible future feature; it is simply dormant. If a decision is made to
  *never* support multi-user auth, the whole of `backend/app/core/auth/*` plus
  the `/infrastructure/auth|oauth/*` routes would become removal candidates —
  but that is a product decision, not a code-cleanup one, and is out of scope
  here.

---

## Summary

| Subsystem | Status | Action recommended (future) | Actioned here |
|-----------|--------|------------------------------|---------------|
| `/trade/*` (global, ephemeral) | **Removed (2026-06-05)** — engine + WS stack + routes deleted | — | ✅ Consolidated into `/paper/*` and retired |
| `/paper/*` (per-profile, persisted) | Live — the single simulated-trading engine | Keep | ✅ Now the sole trading layer (absorbed the `/trade/*` UI) |
| Auth / OAuth / users | Built, **not enforced** (anonymous by default) | **Decided 2026-06-05: single-user tool → keep as non-enforced opt-in, not deleted** (`get_current_user_optional` is load-bearing) | None — documented only |
| `SECURITY.md` | Accurate (reporting policy only; no false auth claim) | No change needed | None |
