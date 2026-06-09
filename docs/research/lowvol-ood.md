# Low-Volatility — Out-of-Distribution Stress Tests

The pre-registered confirmation (`docs/research/lowvol-confirmation.md`) proved
`low_volatility@20` in-sample (2018–2024, Tushare, close-to-close vol, CSI300 +
CSI500). This stresses the signal on two axes it had **not** seen. Runner:
`scripts/research/lowvol_ood.py` (deterministic, point-in-time, survivorship-free
+ suspension-filtered, price-only panels).

## Axis 1 — Estimator robustness: **PASS**
Re-rank by **Parkinson high/low range vol** (`σ² = mean(ln(high/low)²)/(4 ln2)`)
instead of close-to-close std — a structurally different vol estimator — on the
in-sample CSI300 window.

| estimator | OOS IC | ICIR | sign-stable | gate |
|-----------|--------|------|-------------|------|
| close-to-close std (original) | 0.105 | 0.335 | yes | PASS |
| **Parkinson high/low range** | **0.128** | 0.389 | yes | **PASS** |

→ The edge is **not an artifact of one vol definition** — it is, if anything,
slightly stronger under Parkinson. Good.

## Axis 2 — Temporal forward (genuinely unseen 2024-2026): **WEAK / FAIL**
Re-run on a **fresh window the discovery never touched** (2024-01 → 2026-06,
fetched into a separate cache so no 2018-2024 prices leak), both universes.

| forward year IC | CSI300 | CSI500 |
|-----------------|--------|--------|
| 2024 | +0.062 | +0.048 |
| **2025** | **−0.031** | **−0.024** |
| 2026 (partial) | +0.070 | +0.022 |
| **forward-window mean IC** | **+0.010** | **+0.002** |
| ICIR | 0.034 | 0.007 |
| gate | ❌ FAIL | ❌ FAIL |

→ On the genuinely-unseen period the forward IC is **≈ 0 on both universes**, with
**2025 negative on both**. The strong 2019–2023 edge **did not persist** into
2024–2026. The two universes agreeing makes this more than single-universe noise.

## Verdict — a SPLIT result (recorded honestly)
- **Robust to the vol estimator** (Parkinson confirms within-sample).
- **Forward persistence is NOT confirmed** — the recent unseen window shows no
  edge (2025 actually negative). The in-sample signal was real; its continuation
  is not established and currently looks decayed/dormant.

### What this means
1. `low_volatility@20` was a **genuine in-sample cross-sectional effect** (2018–2024,
   confirmed many ways) — that part stands.
2. **It is not a guaranteed-persistent money machine.** Published anomalies
   commonly decay as they get known/crowded, and/or go dormant in regimes that
   punish defensives (2024–25 had a risk-on / small-cap-momentum flavor). Either
   fits what we see.
3. Therefore: treat the low-vol **screen and basket as a risk-reduction tilt with
   historical (not forward-guaranteed) support**, and **monitor the live IC** —
   do not assume the 0.11 in-sample IC keeps printing.

### Caveats on the forward test
- **Short window** — only 21 rebalance months; ICIR ≈ 0 means high noise, and a
  single weak year (2025) dominates. It is suggestive, not conclusive — it does
  **not** prove the signal is dead, only that persistence is **unproven and
  currently weak**.
- Same vendor/methodology (Tushare) as before — a different data source remains
  the one un-run axis (heavy: needs a new vendor integration).
- 2026 is partial (~5 months).

### Honest bottom line for the project
The low-vol work is the project's most rigorous result: a real in-sample edge,
implementable net-of-cost on CSI300, **but with weak forward persistence**. The
right posture is a clearly-disclaimed risk-reduction screen/strategy with live
monitoring — not a claim of durable alpha.
