# Walk-forward statistical-tests summary

- Period: `2020-01-02` → `2026-05-15`
- Window length: **2.0 year(s)** · Step: **6 month(s)** · alpha = **0.05** (Holm step-down across all tests)
- Strategies tested vs buy-and-hold: `blend`, `mean_reversion`, `rotation`
- Total window tests: **27 rows** — but only **18 are independent** (per strategy: {'blend': 9, 'mean_reversion': 9, 'rotation': 9}; `blend`'s 9 rows are byte-identical duplicates of `rotation` — see below).

## ⚠️ Degenerate blend comparison

- `blend_regime` = `unknown` (the CLI default) → the blender resolves α=1.00 (pure trend).
- `blend`'s per-window DM statistic **and** p-value are **byte-identical** to `rotation`'s across all 9 windows. Compare rows in `walkforward_stat_tests.csv`: e.g. window 0 is `dm_stat = 1.0950547684937213` for *both* `rotation` and `blend`.
- This is the documented α=1.00 contract — `DEFAULT_REGIME_BLEND_WEIGHTS["unknown"] = 1.0` in `src/strategy/etf_strategy_blend.py` makes `EtfStrategyBlend` mathematically equivalent to `EtfRotationStrategy` when no regime is classified. It is pinned by `test_blend_pure_trend_alpha_matches_pure_trend_strategy_output` and `test_etf_strategy_comparison.py` — **this is by design, not a bug** (a caller that has not classified the regime should get pure trend back, not a silent 50/50 mean-reversion bet).
- **Consequence for this report: the 27 rows are really 18 independent tests + 9 duplicates.** `blend`'s 9 rows are the same test as `rotation`, reported under a second label; they are not independent evidence and they inflate the Holm family size without adding information.
- For a *non-degenerate* blend test re-run with `--blend-regime sideways` (α=0.5) or any non-trend label.

## Headline numbers

- Windows with raw DM p < 0.05: **0** of **27 rows** (0 of the **18 independent** tests).
- Windows surviving Holm correction: **0**. Note the Holm family is nominally 27 but only 18 distinct — the 9 duplicate `blend` rows make the correction marginally *more* conservative than warranted; it does not change the all-null outcome.
- Minimum p-value: **0.1299** — strategy `mean_reversion`, window 2020-07-09 → 2022-07-08 (window_id=1)

## Direction consistency (does strategy beat buy-hold?)

Fraction of walk-forward windows where the DM statistic is negative (loss-of-strategy < loss-of-buy-hold, i.e. strategy *beat* buy-hold on the window). 50% = coin-flip; 70%+ = a consistent direction even if individual windows aren't significant.

| Strategy | Windows beating buy-hold | Fraction |
| --- | ---: | ---: |
| `blend` | 4 / 9 | 44% |
| `mean_reversion` | 3 / 9 | 33% |
| `rotation` | 4 / 9 | 44% |

## Per-window detail

| strategy | window_id | start | end | n | DM stat | DM p | Sharpe z | Sharpe p | boot p | Holm reject |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | :-: |
| `rotation` | 0 | 2020-01-09 | 2022-01-08 | 97 | +1.095 | 0.2735 | -0.285 | 0.7759 | 0.1600 | no |
| `rotation` | 1 | 2020-07-09 | 2022-07-08 | 97 | +1.299 | 0.1940 | -0.705 | 0.4806 | 0.0630 | no |
| `rotation` | 2 | 2021-01-09 | 2023-01-08 | 97 | +0.536 | 0.5921 | -0.488 | 0.6255 | 0.3800 | no |
| `rotation` | 3 | 2021-07-09 | 2023-07-08 | 97 | +0.206 | 0.8370 | -0.013 | 0.9898 | 0.7880 | no |
| `rotation` | 4 | 2022-01-09 | 2024-01-08 | 97 | +0.102 | 0.9185 | -0.079 | 0.9372 | 0.9160 | no |
| `rotation` | 5 | 2022-07-09 | 2024-07-08 | 97 | -0.187 | 0.8520 | +0.224 | 0.8226 | 0.8560 | no |
| `rotation` | 6 | 2023-01-09 | 2025-01-08 | 97 | -0.293 | 0.7697 | +0.329 | 0.7425 | 0.7700 | no |
| `rotation` | 7 | 2023-07-09 | 2025-07-08 | 96 | -0.123 | 0.9024 | +0.488 | 0.6257 | 0.8930 | no |
| `rotation` | 8 | 2024-01-09 | 2026-01-08 | 97 | -0.014 | 0.9892 | +1.361 | 0.1736 | 0.9880 | no |
| `mean_reversion` | 0 | 2020-01-09 | 2022-01-08 | 97 | +1.451 | 0.1468 | -1.104 | 0.2696 | 0.1080 | no |
| `mean_reversion` | 1 | 2020-07-09 | 2022-07-08 | 97 | +1.515 | 0.1299 | -1.347 | 0.1779 | 0.0520 | no |
| `mean_reversion` | 2 | 2021-01-09 | 2023-01-08 | 97 | +0.735 | 0.4626 | -1.151 | 0.2499 | 0.2830 | no |
| `mean_reversion` | 3 | 2021-07-09 | 2023-07-08 | 97 | +0.582 | 0.5606 | -1.379 | 0.1679 | 0.5240 | no |
| `mean_reversion` | 4 | 2022-01-09 | 2024-01-08 | 97 | +0.234 | 0.8153 | -0.724 | 0.4690 | 0.7990 | no |
| `mean_reversion` | 5 | 2022-07-09 | 2024-07-08 | 97 | -0.023 | 0.9814 | -0.164 | 0.8701 | 0.9770 | no |
| `mean_reversion` | 6 | 2023-01-09 | 2025-01-08 | 97 | -0.197 | 0.8440 | +0.135 | 0.8928 | 0.8220 | no |
| `mean_reversion` | 7 | 2023-07-09 | 2025-07-08 | 96 | -0.129 | 0.8971 | +1.023 | 0.3062 | 0.8770 | no |
| `mean_reversion` | 8 | 2024-01-09 | 2026-01-08 | 97 | +0.478 | 0.6330 | +1.824 | 0.0682 | 0.5740 | no |
| `blend` | 0 | 2020-01-09 | 2022-01-08 | 97 | +1.095 | 0.2735 | -0.285 | 0.7759 | 0.1600 | no |
| `blend` | 1 | 2020-07-09 | 2022-07-08 | 97 | +1.299 | 0.1940 | -0.705 | 0.4806 | 0.0630 | no |
| `blend` | 2 | 2021-01-09 | 2023-01-08 | 97 | +0.536 | 0.5921 | -0.488 | 0.6255 | 0.3800 | no |
| `blend` | 3 | 2021-07-09 | 2023-07-08 | 97 | +0.206 | 0.8370 | -0.013 | 0.9898 | 0.7880 | no |
| `blend` | 4 | 2022-01-09 | 2024-01-08 | 97 | +0.102 | 0.9185 | -0.079 | 0.9372 | 0.9160 | no |
| `blend` | 5 | 2022-07-09 | 2024-07-08 | 97 | -0.187 | 0.8520 | +0.224 | 0.8226 | 0.8560 | no |
| `blend` | 6 | 2023-01-09 | 2025-01-08 | 97 | -0.293 | 0.7697 | +0.329 | 0.7425 | 0.7700 | no |
| `blend` | 7 | 2023-07-09 | 2025-07-08 | 96 | -0.123 | 0.9024 | +0.488 | 0.6257 | 0.8930 | no |
| `blend` | 8 | 2024-01-09 | 2026-01-08 | 97 | -0.014 | 0.9892 | +1.361 | 0.1736 | 0.9880 | no |

## Honest conclusion

Every single one of the 27 walk-forward window rows has raw DM p-value above α=0.05 (minimum p = 0.1299); only 18 of those rows are independent tests (`blend` ≡ `rotation` under the default regime). After Holm correction zero windows reject. There is no walk-forward regime in which the active strategies are statistically distinct from buy-and-hold on this 5y sample. The terminal-period finding (commit fddfbf8) generalises temporally: the 16-19pp raw spread is indistinguishable from noise no matter how you slice the window.

How underpowered, precisely? `scripts/power_target.py` inverts this exact HAC variance structure (see `docs/falsifiable_alpha_target.md`): on the 307-period terminal sample the **Minimum Detectable Effect is an Information Ratio of ≈ 1.15** (≈ +14.9 pp/yr excess return) at 80% power. The strategy would need a *true* IR at or above that bar before the DM test could reliably reject the null — below it, the sample cannot tell the strategy apart from buy-and-hold. The bar is high mainly because the strategy's tracking error is large (≈12.9% annualised); a thinner-tracking-error variant would lower the MDE without needing more raw alpha.

---

Methodology: each window runs Diebold-Mariano (loss=negative-return, Newey-West HAC h=1), Memmel (2003) closed-form Sharpe-difference test, and Politis-Romano circular block bootstrap on the per-period return differential vs equal-weight buy-and-hold sampled at the same rebalance cadence. Windows overlap by design — Holm correction treats them as a family, which is the right multi-test correction for 'are any windows significantly different from buy-hold?'.
