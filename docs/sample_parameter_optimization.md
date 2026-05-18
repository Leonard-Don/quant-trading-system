# Parameter Optimization Report — rotation

- Period: 2024-01-02 → 2025-04-30
- Optimize metric: ``sharpe_ratio``
- Configs evaluated: 20 (grid requested 20)

## Optimal config per metric

| Metric | Config ID | Score | Parameters |
| --- | ---: | ---: | --- |
| annualized_return_pct | 11 | 6.9494 | gross_cap=0.8, min_score_to_hold=30.0 |
| avg_turnover_pct | 3 | 6.7315 | gross_cap=0.6, min_score_to_hold=30.0 |
| calmar_ratio | 1 | 1.0943 | gross_cap=0.6, min_score_to_hold=20.0 |
| max_drawdown_pct | 2 | 5.7255 | gross_cap=0.6, min_score_to_hold=25.0 |
| sharpe_ratio | 3 | 0.7267 | gross_cap=0.6, min_score_to_hold=30.0 |
| total_return_pct | 11 | 8.9060 | gross_cap=0.8, min_score_to_hold=30.0 |
| win_rate | 0 | 0.6190 | gross_cap=0.6, min_score_to_hold=15.0 |

## Top 5 configs by ``sharpe_ratio``

| Rank | Config ID | Sharpe | Return % | MaxDD % | Calmar | Turnover % | Parameters |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 3 | 0.727 | 8.04 | 5.80 | 1.083 | 6.73 | gross_cap=0.6, min_score_to_hold=30.0 |
| 2 | 1 | 0.724 | 8.02 | 5.73 | 1.094 | 6.73 | gross_cap=0.6, min_score_to_hold=20.0 |
| 3 | 2 | 0.722 | 7.99 | 5.73 | 1.089 | 6.75 | gross_cap=0.6, min_score_to_hold=25.0 |
| 4 | 0 | 0.719 | 7.96 | 5.74 | 1.083 | 6.73 | gross_cap=0.6, min_score_to_hold=15.0 |
| 5 | 7 | 0.704 | 8.64 | 6.82 | 0.989 | 7.19 | gross_cap=0.7, min_score_to_hold=30.0 |

## Parameter sensitivity (Sharpe variance ranking)

Per-parameter mean-Sharpe spread when the parameter is fixed at each candidate value. Larger ``sharpe_std`` and ``sharpe_range`` mean the parameter actually moves the needle; small values mean you can pick anything in the grid without noticeable impact.

| Parameter | Sharpe std | Sharpe range | Values |
| --- | ---: | ---: | --- |
| gross_cap | 0.0491 | 0.1366 | 0.6, 0.7, 0.8, 0.9, 1.0 |
| min_score_to_hold | 0.0019 | 0.0043 | 15.0, 20.0, 25.0, 30.0 |

## Bootstrap 95% CI on Sharpe (top-N configs)

Resampled the per-rebalance returns with replacement (200 iterations) and took the 2.5% / 97.5% quantiles. If the runner-up's CI overlaps the leader's point estimate, the apparent winner may be noise.

| Config ID | Point Sharpe | CI low | CI high | Parameters |
| ---: | ---: | ---: | ---: | --- |
| 3 | 0.727 | -0.113 | 0.436 | gross_cap=0.6, min_score_to_hold=30.0 |
| 1 | 0.724 | -0.128 | 0.437 | gross_cap=0.6, min_score_to_hold=20.0 |
| 2 | 0.722 | -0.119 | 0.362 | gross_cap=0.6, min_score_to_hold=25.0 |
| 0 | 0.719 | -0.148 | 0.449 | gross_cap=0.6, min_score_to_hold=15.0 |
| 7 | 0.704 | -0.124 | 0.345 | gross_cap=0.7, min_score_to_hold=30.0 |

## Caveats

- single_window_optimization_is_in_sample_by_construction
- bootstrap_ci_assumes_iid_returns_and_understates_real_uncertainty
- no_transaction_costs_modeled_for_any_config
