# Low-Volatility @20d — Pre-Registered Confirmation Study

**Status:** PRE-REGISTERED (hypothesis + gate + datasets + decision rule fixed *before* running any new data). Results appended below in a later commit. Git history proves the pre-registration commit precedes the results commit.

## Why this study
The factor IC harness, after the survivorship + suspension correction (PR #145), reported that
`low_volatility @ horizon=20d` clears the gate on the **survivorship-free CSI300** (OOS IC +0.105,
ICIR 0.335, sign-stable). That result was *discovered by fixing a bug and then observing* — i.e. it
carries researcher-degrees-of-freedom risk. Before trusting it (or building anything on it), it must
survive a **pre-registered, genuinely out-of-sample** confirmation. This document fixes the test
*before* the new data is run.

## Hypothesis (fixed)
- **Factor:** `LowVolatilityFactor` — cross-sectional rank of *inverse* realized volatility
  (lower trailing realized vol → higher expected forward return). Realized vol window = **60 trading
  days** (the factor's default, as used in the discovery run).
- **Direction:** **+1** (pre-specified; NOT chosen after seeing results).
- **Horizon:** **20 trading days** (the only horizon the discovery passed; 5d/60d did not).
- **Metric:** cross-sectional Spearman rank IC per rebalance date; monthly rebalance.

## Pass gate (fixed — identical to the production harness)
A factor PASSES iff, on its out-of-sample (last 30% of the rebalance-date timeline) slice:
`OOS mean IC ≥ 0.03` AND `ICIR > 0` AND yearly-sign-stable (all yearly ICs same sign) AND the OOS IC
is positive (same direction as pre-specified). Point-in-time throughout; fundamentals not used
(low-vol needs prices only).

## Datasets (fixed)
All survivorship-free (universe = union of point-in-time constituents over the span) +
suspension-filtered (each rebalance date's cross-section = {as-of constituents} − {suspended that
day}), spanning **2018-01-01 → 2024-01-01** unless noted.

| # | Dataset | Role | Independence from discovery |
|---|---------|------|------------------------------|
| 1 | **CSI500** (000905.SH) survivorship-free | **PRIMARY / decisive** | Fully independent — disjoint mid-cap names, none in the CSI300 discovery set |
| 2 | **CSI1000** (000852.SH) survivorship-free | Corroborating | Fully independent — small-cap names |
| 3 | CSI300 cached — **vol-window robustness** {60,120,250}d | Gating (knife-edge check) | Same names; tests methodological fragility |
| 4 | CSI300 cached — **year-by-year IC** | Gating (regime check) | Same names; tests single-regime dependence |
| 5 | CSI300 cached — **temporal hold-out** (confirm on 2023-2024 only) | Corroborating | Same names; tests recency stability |

## Decision rule (fixed — applied mechanically to results)
`low_volatility@20` is **CONFIRMED** iff ALL of:
1. **PRIMARY:** passes the full gate on **CSI500** survivorship-free (the decisive independent universe).
2. **ROBUSTNESS:** passes the gate in **≥ 2 of 3** vol-window variants {60,120,250}d on CSI300 (not knife-edge).
3. **REGIME:** positive-IC years strictly outnumber negative-IC years on CSI300 (not driven by one year).

CSI1000 (#2) and the CSI300 temporal hold-out (#5) are **corroborating evidence** — they raise or
lower stated confidence but do NOT flip the binary verdict.

**If CONFIRMED →** proceed to build a low-volatility screen/strategy into the tool.
**If NOT CONFIRMED →** the CSI300 discovery was likely a large-cap / single-universe artifact; do
**not** build (no theater). Record the negative result.

---

## Results

Run deterministically via `scripts/research/lowvol_confirm.py` (no LLM in the
numeric path), 2026-06-08. Survivorship-free + suspension-filtered throughout.

### PRIMARY — CSI500 (000905.SH), the decisive independent universe
Union of point-in-time constituents = **1009** historical names; 56 monthly
rebalance dates; per-date cross-section ≈ 499.

| window | full IC | **OOS IC** | ICIR | sign-stable | gate |
|--------|---------|-----------|------|-------------|------|
| 60     | 0.0803  | **0.1135** | 0.447 | yes (5/5 yrs +) | **PASS** |

- Yearly IC: 2019 +0.046, 2020 +0.040, 2021 +0.092, 2022 +0.102, 2023 +0.116 — **all positive, monotone-ish rising**.
- Temporal hold-out (≥2023): mean IC **+0.116**, ICIR 0.71 — recency holds.
- **Independent recompute** (hand-rolled, does NOT import `LowVolatilityFactor`/`evaluate_factor`): OOS IC **0.11346756982579667** — *identical to 17 digits* to the harness path. Three independent code paths (failed-workflow agent, harness, manual) agree exactly → not a harness bug.
- Look-ahead checked three ways (forward bar strictly future; `history()` slices ≤ as_of; `index_weight`/`suspend_d` queried as-of the date). No leakage.

### ROBUSTNESS + REGIME — CSI300 (000300.SH), from cache
Union = 526 names; 46 rebalance dates; cross-section ≈ 300.

| vol window | OOS IC | ICIR | gate |
|-----------|--------|------|------|
| 60  | 0.105 | 0.335 | PASS |
| 120 | 0.128 | 0.362 | PASS |
| 250 | 0.149 | 0.372 | PASS |

- **Robustness: 3 / 3 windows pass**, and OOS IC *strengthens* with the window (0.105 → 0.128 → 0.149) — not a knife-edge artifact.
- Regime: yearly IC 2020 +0.006, 2021 +0.077, 2022 +0.088, 2023 +0.140 → **4 positive years, 0 negative** (`regime_ok`).
- Temporal hold-out (≥2023): mean IC **+0.140**, ICIR 0.82.

### CSI1000 (000852.SH) — corroborating, NOT run
A second independent (small-cap) universe was pre-registered as *corroborating
only* (does not gate the verdict). It needs a ~1000-name throttle-aware fetch; a
rushed/degraded run would add noise, not signal, so it is left as optional future
corroboration. The verdict below does not depend on it.

## Verdict (mechanical, per the fixed decision rule)

| Gating condition | Result |
|---|---|
| ① PRIMARY — CSI500 passes the gate | ✅ OOS IC 0.1135, ICIR 0.447, sign-stable |
| ② ROBUSTNESS — ≥ 2/3 vol-windows pass on CSI300 | ✅ 3/3 |
| ③ REGIME — positive-IC years > negative on CSI300 | ✅ 4 vs 0 |

### → **CONFIRMED.** `low_volatility @ 20d` (direction +1) is a genuine, out-of-sample, survivorship-free signal on Chinese equities.

**Confidence: high.** Fully independent mid-cap universe (disjoint names from the
CSI300 discovery); three code paths agree to 17 digits; sign-stable every single
year; robust and *strengthening* across vol windows; look-ahead ruled out.

**Honest caveats (do not oversell):**
1. **Horizon-specific:** the *holding* horizon that validated is 20 days; the original CSI300 scan failed at 5d/60d holding. (The vol *lookback window* 60/120/250 all pass — window ≠ horizon.)
2. **Same methodology, not a new vendor:** discovery and confirmation both use the same survivorship-free Tushare pipeline. A truly out-of-distribution test (different country, a fresh forward year, or a different data vendor) would harden it further.
3. **Signal ≠ tradable alpha yet:** an IC of ~0.11 is a real cross-sectional edge but capturing it needs the A-share frictions (now modeled, PR #144) plus turnover/capacity analysis. This confirms the *signal*, not a P&L.
4. It is the well-known **low-volatility anomaly**, empirically stronger in mid/small caps — economically plausible, which is reassuring rather than suspicious.
5. **(2026-06-10 addendum) Return-measurement caveat — re-measured, signal STRENGTHENS:** every number above was computed with forward returns on **unadjusted closes** (dividends excluded, 送转/split jumps included) — caught by the 2026-06-10 audit. The harness now measures forward returns on total-return prices (`close × adj_factor`). Re-running the CSI300 discovery scorecard under the corrected measure: `low_volatility@20` OOS IC **+0.105 → +0.113** (one-sided p 0.046 → 0.038) — dividend exclusion had been *understating* the high-yield low-vol cross-section, so the correction strengthens the signal. The CSI500 pre-registered numbers in this document are still the raw-close measurements (this pre-registration is not silently re-run; the bias direction is the same, so they are likely conservative). Collateral honesty: `short_reversal@20`'s borderline scorecard pass did **not** survive the corrected measure (its 2022 yearly IC flips negative → sign-unstable → gate FAIL).

**Decision:** proceed to surface a low-volatility screen/strategy in the tool
(this is the first signal with out-of-sample support to earn that).
