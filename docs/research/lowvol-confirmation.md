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
*(appended after the pre-registered runs complete — see the results commit on this branch)*
