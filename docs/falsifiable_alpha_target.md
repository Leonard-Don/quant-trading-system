# Falsifiable alpha target (power-analysis inversion)

This doc is the **inversion** of the statistical-falsification layer. `docs/walkforward_stat_tests_summary.md` established the honest negative result — the ETF rotation strategy is statistically indistinguishable from buy-and-hold on the 5y sample. A null result is *not* a zero edge, so the natural follow-up is: **how large would a true edge have to be before this sample could detect it?** That threshold — the Minimum Detectable Effect (MDE) — is computed below. It is a falsifiable target, not a claim that the strategy *has* an edge.

## Inputs

- Strategy: `rotation` vs equal-weight buy-and-hold
- Period: `2020-01-02` -> `2026-05-15`
- Sample size: **307** rebalance periods (weekly cadence, 5 business days)
- Test: two-sided Diebold-Mariano (loss = negative-return, Newey-West HAC h=1) at alpha = **0.05**
- Target power: **80%**
- Annualisation: **52** rebalance periods per year

## What the sample actually shows

| Quantity | Value |
| --- | ---: |
| Observed Information Ratio | -0.3979 |
| Observed annualised excess return | -5.13%/yr |
| Terminal-period DM statistic | +0.967 |
| Terminal-period DM p-value (2-sided) | 0.3337 |
| Annualised tracking error | 12.90% |

## The falsifiable target — Minimum Detectable Effect

On this 307-period sample, holding the observed HAC variance structure fixed, the DM test reaches **80% power** at alpha = 0.05 only if the strategy's *true* edge is at least:

| MDE (the target) | Value |
| --- | ---: |
| **Information Ratio** | **1.1530** |
| Annualised excess return | **+14.88%/yr** |
| Per-rebalance excess return | +0.29%/period |
| Required non-centrality (z_(1-a/2) + z_power) | 2.8016 |

## Honest interpretation

The strategy's observed IR (-0.3979) is **inside the noise floor** — its magnitude is below the MDE IR of 1.1530. This is the load-bearing conclusion: on this sample the strategy **cannot be told apart from buy-and-hold**, and 'no statistically significant edge' carries *no* information about whether a smaller real edge exists. The sample would need a true IR of **>= 1.15** before the DM test could reliably (>= 80%) reject the null.

A useful frame: an IR of 1.15 is an *institutional-grade* bar — sustained Information Ratios above 1.0 are rare even for professional managers. The reason the bar is this high is the strategy's large tracking error (12.9% annualised) relative to any plausible alpha: the rotation strategy deviates substantially from the benchmark, so it needs a *correspondingly large* mean excess return to clear the noise. Shrinking the tracking error (tighter active weights, lower turnover) lowers the MDE just as effectively as raising raw alpha.

Equivalently: to detect the rotation strategy's currently *observed* point-estimate edge (-5.13%/yr) at 80% power you would need roughly `(required_ncp / observed_IR)^2 * periods_per_year` rebalance periods — far more than the 307 this 5y sample provides. The honest move is to either (a) collect a longer / higher-frequency sample, (b) re-engineer the strategy for a thinner tracking error, or (c) accept that the edge — if any — is below this sample's resolution and stop treating the backtest spread as signal.

## Per walk-forward window

Each 2.0-year walk-forward window inverted independently. Shorter windows have fewer observations and therefore a *higher* MDE — they can detect even less.

| window | start | end | n | MDE IR | MDE excess return/yr | observed IR |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 0 | 2020-01-09 | 2022-01-08 | 97 | 2.0513 | +29.41% | -0.8018 |
| 1 | 2020-07-09 | 2022-07-08 | 97 | 2.0513 | +27.10% | -0.9510 |
| 2 | 2021-01-09 | 2023-01-08 | 97 | 2.0513 | +27.27% | -0.3923 |
| 3 | 2021-07-09 | 2023-07-08 | 97 | 2.0513 | +26.02% | -0.1506 |
| 4 | 2022-01-09 | 2024-01-08 | 97 | 2.0513 | +25.01% | -0.0749 |
| 5 | 2022-07-09 | 2024-07-08 | 97 | 2.0513 | +22.01% | +0.1366 |
| 6 | 2023-01-09 | 2025-01-08 | 97 | 2.0513 | +28.61% | +0.2144 |
| 7 | 2023-07-09 | 2025-07-08 | 96 | 2.0619 | +27.18% | +0.0903 |
| 8 | 2024-01-09 | 2026-01-08 | 97 | 2.0513 | +25.58% | +0.0099 |

## Code integration

The reusable power-analysis primitive lives in `src.backtest.strategy_statistical_tests.minimum_detectable_effect`. `scripts/power_target.py` applies it to the ETF rotation vs buy-and-hold comparison and renders this falsifiable-alpha report. The generic `src.backtest.batch_backtester.WalkForwardAnalyzer` uses the same inversion for its `statistical_power_diagnostics` payload, so batch walk-forward output can flag `observed_effect_inside_noise_floor` instead of over-reading noisy sample-out windows.

## Method

The Diebold-Mariano statistic for the negative-return loss is `DM = d_mean / sqrt(hac_var / n)`, where `d_mean` is the mean loss differential, `-d_mean` is the per-period excess return, and `hac_var` is the per-period Newey-West HAC variance of the differential. The annualised Information Ratio relates to it by `IR = DM * sqrt(periods_per_year / n)`. Under the alternative the two-sided test at level alpha reaches power `1-b` when the non-centrality of `|DM|` solves the same two-tail power equation used by the forward check:

```
power = Phi(required_ncp - z_(1-a/2)) + Phi(-required_ncp - z_(1-a/2))
mde_ir = required_ncp * sqrt(periods_per_year / n)
mde_excess_return_per_period = required_ncp * sqrt(hac_var / n)
```

The inversion is solved numerically (no simulation). It is implemented in `src.backtest.strategy_statistical_tests.minimum_detectable_effect` and round-trip-verified: feeding `mde_ir` back through `dm_power_for_information_ratio` recovers the requested power (80%) to within floating-point tolerance. Regenerate this doc with `python scripts/power_target.py --csv data/etf_backtest/etf_prices_5y.csv --output-md docs/falsifiable_alpha_target.md`.
