# 多策略对照回放报告 (5-year window, post power-analysis re-run)

窗口：`2020-01-02` → `2026-05-15` · 参赛策略 = 3 · n_rebalances = 308

> Re-generated after extending `data/etf_backtest/etf_prices_5y.csv`
> from a 2020-01 → 2024-12 cut to a full 2020-01 → 2026-05 cut, so the
> 5y comparison and the 4y CSV now share the same `2026-05-15` end-date.
> Backing data fetched via `scripts/fetch_etf_history_5y.py` — `akshare`
> Sina endpoint, 1540 bars, zero mismatches on the 968-row overlap with
> `etf_prices_4y.csv`.

## Why this re-run exists

The DM/Sharpe/bootstrap tests added in commit `fddfbf8` ended with the
caveat: *"to detect even a +3pp/yr edge at α=0.05 / power 0.80, need
~5× more periods (~6 years weekly cadence)"*. The original 4y window
gave n=193 weekly observations; this 5y re-run gives **n=307** (a 59%
gain on sample size — short of the +400% the power analysis called for,
but the biggest sample we can defensibly pull from `akshare` without
either splicing pre-CSI-300-rebase data or relaxing the asset universe).

## 头条指标 (5y)

| 策略 | 总收益 % | 年化 % | Sharpe | MaxDD % | Calmar | 平均换手 % | 命中率 | 等权基准 % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `rotation` | 63.89 | 8.42 | 0.795 | 11.58 | 0.727 | 7.10 | 52.12% | 102.02 |
| `mean_reversion` | 26.43 | 3.91 | 0.680 | 9.46 | 0.413 | 4.73 | 53.42% | 102.02 |
| `blend` | 63.89 | 8.42 | 0.795 | 11.58 | 0.727 | 7.10 | 52.12% | 102.02 |

## 4y baseline (re-run on same end-date for comparison)

Window: `2022-05-18` → `2026-05-15`, n=193 weekly observations

| 策略 | 总收益 % | 年化 % | Sharpe | MaxDD % | Calmar | 平均换手 % | 命中率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `rotation` | 38.90 | 8.93 | 0.828 | 12.15 | 0.735 | 7.29 | 52.33% |
| `mean_reversion` | 36.31 | 8.40 | 1.379 | 5.89 | 1.427 | 4.61 | 50.26% |
| `blend` | 38.90 | 8.93 | 0.828 | 12.15 | 0.735 | 7.29 | 52.33% |

## 4y vs 5y headline delta

| Strategy | tot% 4y → 5y | Ann% 4y → 5y | Sharpe 4y → 5y | MaxDD% 4y → 5y | Calmar 4y → 5y |
| --- | ---: | ---: | ---: | ---: | ---: |
| `rotation` | 38.90 → 63.89 | 8.93 → 8.42 | **0.828 → 0.795** | 12.15 → 11.58 | 0.735 → 0.727 |
| `mean_reversion` | 36.31 → 26.43 | 8.40 → 3.91 | **1.379 → 0.680** | 5.89 → 9.46 | 1.427 → 0.413 |
| `blend` | 38.90 → 63.89 | 8.93 → 8.42 | **0.828 → 0.795** | 12.15 → 11.58 | 0.735 → 0.727 |

The 4y → 5y move tells two structurally different stories per strategy:

- **rotation / blend** drift very little: Sharpe -0.033, ann-return
  -0.51 pp, MaxDD -0.57 pp. The 2020-2022 window is *additive*: more
  data, similar per-bar economics. Total-return rises monotonically
  because we're compounding over 5 years instead of 4.
- **mean_reversion** collapses: Sharpe -0.700, ann-return -4.49 pp,
  MaxDD +3.58 pp. The 2020-2022 sub-window contained the COVID
  crash + 2021 sideways grind, which is the regime mean-reversion is
  weakest on (its 4y outperformance was entirely a 2022-2024
  artefact). On the bigger sample its edge over rotation **inverts**.
- **Strategy ranking flips on Sharpe**: 4y said MR (1.38) > rotation
  (0.83). 5y says rotation (0.80) > MR (0.68). That's a real ordering
  change driven by more data — but neither change is statistically
  significant (see DM section).

## 区间体制 (5y, midpoint split)

- Trending half (`second_half`): 2023-03-09 → 2026-05-15 (R²=0.819)
- Choppy half (`first_half`): 2020-01-02 → 2023-03-08 (R²=0.004)

| 策略 | 趋势段收益 % | 震荡段收益 % |
| --- | ---: | ---: |
| `rotation` | 39.50 | 21.81 |
| `mean_reversion` | 26.95 | 0.47 |
| `blend` | 39.50 | 21.81 |

- 趋势段优胜: `rotation`  ·  震荡段优胜: `rotation`

> regime split at midpoint (trending R^2=0.819, choppy R^2=0.004)
> half-returns derived from per-strategy rebalance_log equity-after series

## 相对表现 (A vs B = A 减 B, 5y)

| 对比 | 收益差 pp | Sharpe 差 | MaxDD 差 pp |
| --- | ---: | ---: | ---: |
| `rotation` vs `mean_reversion` | +37.46 | +0.115 | +2.12 |
| `rotation` vs `blend` | +0.00 | +0.000 | +0.00 |
| `mean_reversion` vs `rotation` | -37.46 | -0.115 | -2.12 |
| `mean_reversion` vs `blend` | -37.46 | -0.115 | -2.12 |
| `blend` vs `rotation` | +0.00 | +0.000 | +0.00 |
| `blend` vs `mean_reversion` | +37.46 | +0.115 | +2.12 |

## 统计显著性检验 (Statistical hypothesis tests, 5y)

配对数 k = 6 · 显著性水平 α = 0.050 · n = 307 weekly observations

### Diebold-Mariano (1995) test (loss = -return)

| 配对 | DM stat | p (2-sided) | p (1-sided, A>B) | mean(L_a - L_b) | n |
| --- | ---: | ---: | ---: | ---: | ---: |
| `rotation_vs_mean_reversion` | -1.592 | **0.1114** | 0.0557 | -0.000996 | 307 |
| `rotation_vs_blend` | +0.000 | 1.0000 | 1.0000 | +0.000000 | 307 |
| `rotation_vs_buy_hold` | +0.967 | 0.3337 | 0.8332 | +0.000987 | 307 |
| `mean_reversion_vs_blend` | +1.592 | **0.1114** | 0.9443 | +0.000996 | 307 |
| `mean_reversion_vs_buy_hold` | +1.579 | 0.1144 | 0.9428 | +0.001983 | 307 |
| `blend_vs_buy_hold` | +0.967 | 0.3337 | 0.8332 | +0.000987 | 307 |

### Sharpe-ratio difference (Memmel 2003, 5y)

| 配对 | Sharpe_a | Sharpe_b | z | p (2-sided) | n |
| --- | ---: | ---: | ---: | ---: | ---: |
| `rotation_vs_mean_reversion` | +0.1240 | +0.1005 | +0.503 | 0.6152 | 307 |
| `rotation_vs_blend` | +0.1240 | +0.1240 | +0.000 | 1.0000 | 307 |
| `rotation_vs_buy_hold` | +0.1240 | +0.1080 | +0.390 | 0.6969 | 307 |
| `mean_reversion_vs_blend` | +0.1005 | +0.1240 | -0.503 | 0.6152 | 307 |
| `mean_reversion_vs_buy_hold` | +0.1005 | +0.1080 | -0.146 | 0.8842 | 307 |
| `blend_vs_buy_hold` | +0.1240 | +0.1080 | +0.390 | 0.6969 | 307 |

### Block bootstrap 95% CI on return differential (5y)

| 配对 | mean(A-B) | CI low | CI high | p (2-sided) | block | n_boot |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `rotation_vs_mean_reversion` | +0.000996 | -0.000189 | +0.002286 | **0.1070** | 10 | 1000 |
| `rotation_vs_blend` | +0.000000 | +0.000000 | +0.000000 | 1.0000 | 10 | 1000 |
| `rotation_vs_buy_hold` | -0.000987 | -0.002811 | +0.000777 | 0.2600 | 10 | 1000 |
| `mean_reversion_vs_blend` | -0.000996 | -0.002286 | +0.000189 | **0.1070** | 10 | 1000 |
| `mean_reversion_vs_buy_hold` | -0.001983 | -0.004524 | +0.000282 | 0.1110 | 10 | 1000 |
| `blend_vs_buy_hold` | -0.000987 | -0.002811 | +0.000777 | 0.2600 | 10 | 1000 |

### Multiple-testing correction (Bonferroni & Holm, 5y)

Bonferroni threshold α/k = 0.00833 (smallest raw p must drop below this)

| 配对 | DM raw p | DM survives Bonferroni? | DM survives Holm? | Sharpe raw p | Sharpe survives Bonferroni? | Sharpe survives Holm? |
| --- | ---: | :-: | :-: | ---: | :-: | :-: |
| `rotation_vs_mean_reversion` | 0.1114 | no | no | 0.6152 | no | no |
| `rotation_vs_blend` | 1.0000 | no | no | 1.0000 | no | no |
| `rotation_vs_buy_hold` | 0.3337 | no | no | 0.6969 | no | no |
| `mean_reversion_vs_blend` | 0.1114 | no | no | 0.6152 | no | no |
| `mean_reversion_vs_buy_hold` | 0.1144 | no | no | 0.8842 | no | no |
| `blend_vs_buy_hold` | 0.3337 | no | no | 0.6969 | no | no |

## 4y → 5y p-value movement (the headline question)

The original commit `fddfbf8` ended with: *"smallest p=0.345 on the 2024-2025
window — to detect a +3pp/yr edge at α=0.05 / power 0.80, need ~5x more
periods"*. The 4y baseline I re-ran for this report (2022-05-18 → 2026-05-15,
the full 4y CSV window, not the 16-month sub-window in `fddfbf8`) already
ran n=193 and gave smallest DM p=0.3077. Extending to 5y / n=307 moves
the p-values like this:

| Pair | DM p (4y, n=193) | DM p (5y, n=307) | Δp | Crossed 0.05? |
| --- | ---: | ---: | ---: | :-: |
| `rotation_vs_mean_reversion` | 0.6873 | **0.1114** | -0.5760 | no |
| `mean_reversion_vs_blend` | 0.6873 | **0.1114** | -0.5760 | no |
| `mean_reversion_vs_buy_hold` | 0.3104 | 0.1144 | -0.1961 | no |
| `rotation_vs_buy_hold` | 0.3077 | 0.3337 | +0.0260 | no |
| `blend_vs_buy_hold` | 0.3077 | 0.3337 | +0.0260 | no |
| `rotation_vs_blend` | 1.0000 | 1.0000 | 0.0000 | n/a |

| Pair | Bootstrap p (4y) | Bootstrap p (5y) | Δp | Crossed 0.05? |
| --- | ---: | ---: | ---: | :-: |
| `rotation_vs_mean_reversion` | 0.6770 | **0.1070** | -0.5700 | no |
| `mean_reversion_vs_blend` | 0.6770 | **0.1070** | -0.5700 | no |
| `mean_reversion_vs_buy_hold` | 0.3030 | 0.1110 | -0.1920 | no |

| Pair | Sharpe-diff p (4y) | Sharpe-diff p (5y) | Δp | Crossed 0.05? |
| --- | ---: | ---: | ---: | :-: |
| `rotation_vs_mean_reversion` | 0.1227 | 0.6152 | +0.4925 | no |
| `mean_reversion_vs_buy_hold` | 0.2667 | 0.8842 | +0.6175 | no |

### Honest reading

- **Zero pairwise comparisons cross α=0.05 at either window.** The
  smallest p anywhere in the 5y grid is 0.107 (block-bootstrap on
  `rotation_vs_mean_reversion`), still 2.1× the conventional threshold.
- **DM/bootstrap p-values dropped sharply for the `rotation vs MR`
  pair** (~0.69 → 0.11, a 6× tightening), driven by the 4y window
  having genuinely flipped the sign of the return spread relative
  to the longer 5y window — when you add 2020-2022 back in, rotation
  goes back to outperforming MR by +0.10 pp/week and the DM statistic
  finally points in a consistent direction across the sample. **But
  even with that improvement, p stays well above 0.05.**
- **Sharpe-difference p-values went the *wrong* way for MR-related
  pairs** (e.g. `rotation_vs_MR` 0.12 → 0.62). This is because the
  4y window flattered MR's Sharpe (1.38 vs 0.83) — over 5y MR's
  Sharpe collapses to 0.68 and the difference becomes both smaller
  in magnitude *and* noisier per Memmel's asymptotic variance estimate.
- **No correction (Bonferroni or Holm) flags any pair at either
  window.** The Bonferroni threshold α/k=0.00833 is still ~13× tighter
  than the smallest raw p in the grid.

**Verdict**: more data ruled out a few false-positive scenarios (the
sign of the rotation-vs-MR DM statistic stabilised; MR's apparent 4y
Sharpe edge over rotation evaporated), but it did **not** push any
pairwise comparison below α=0.05. The 4y "nothing-significant"
finding is reaffirmed at 5y. The strategy claim "rotation has positive
expected return after costs" remains statistically indistinguishable
from noise at the 95% confidence level.

To actually reject the noise null at +3pp/yr expected edge × 80% power,
the back-of-envelope still asks for ~6 years of *weekly-independent*
returns on a much higher Sharpe series than this universe produces.
Either the strategy needs to be tested on a daily cadence (n grows 5×
but autocorrelation eats most of the gain through the Newey-West HAC
correction) or we need a different universe with a thicker edge.

## Caveats

- no_transaction_costs_modeled
- no_bid_ask_spread_or_slippage
- no_market_impact
- next_bar_close_fills_only
- equal_weight_buy_hold_benchmark
- ignores_survivorship_bias
- rebalance_cadence_fixed_at_5_bar(s)
- strategy_label:rotation
- strategy_label:mean_reversion
- strategy_label:blend
- comparison_window_shared_across_strategies — all strategies evaluated on the same prices / dates / rebalance cadence
- 5y_window_uses_etf_prices_5y.csv_with_ffill_for_late-listed_513130_and_518680
