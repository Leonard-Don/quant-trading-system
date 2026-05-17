# Market Regime Recommendation

Generated from `etf_prices_4y.csv` over the last **90** trading days (as_of = `2026-05-15`).

## Regime

- **Regime**: `choppy_high_vol`
- **Confidence**: 65%
- **Bars used**: 90
- **Assets used**: 5

### Features

| Feature | Value |
|---|---|
| trend_r2 | 0.015 |
| trend_slope (log-price / day) | -0.00018 |
| realized_vol (annualised) | 28.8% |
| return_skew | -1.26 |
| drawdown_ratio (max_dd / vol) | 0.64 |
| avg_pairwise_correlation | 0.35 |

### Why

- trend_r2 0.02 < 0.55 (choppy)
- realised_vol 28.8% >= 25% (high)

## Recommendation

- **Run strategy**: `blend`
- **Config overrides**: `gross_cap=0.85`
- **Alternatives**: `rotation`, `mean_reversion`

### Rationale

Choppy AND volatile — single-strategy edge is small; blend rotation and MR to diversify regime risk, and shave 15% off gross_cap to respect the elevated vol.

## Caveats

- Regimes change slowly; 90-day lookback may miss inflection points by ~30 days.
- Bear-regime mapping is based on portfolio-risk practice, not in-sample evidence (the empirical anchor in commit `a54b986` only covered trending vs choppy halves of an up-market window).
- Empirical anchor: in commit `a54b986`'s multi-strategy comparison (2024-01-01 → 2025-04-30), the choppy first half (R²=0.370) had `rotation` winning (+5.48%); the trending second half (R²=0.792) had `mean_reversion` winning (+6.17%). The recommender encodes that split.
