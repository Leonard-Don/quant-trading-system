# 多策略对照回放报告

窗口：`2020-01-02` → `2024-12-31` · 参赛策略 = 3

## 头条指标

| 策略 | 总收益 % | 年化 % | Sharpe | MaxDD % | Calmar | 平均换手 % | 命中率 | 等权基准 % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `rotation` | 23.21 | 4.43 | 0.503 | 9.09 | 0.488 | 6.60 | 50.00% | 38.02 |
| `mean_reversion` | 1.82 | 0.37 | 0.108 | 9.46 | 0.040 | 4.08 | 48.35% | 38.02 |
| `blend` | 23.21 | 4.43 | 0.503 | 9.09 | 0.488 | 6.60 | 50.00% | 38.02 |

## 单项冠军

| 指标 | 优胜策略 | 分数 |
| --- | --- | ---: |
| Sharpe | `rotation` | 0.5026 |
| 总收益 | `rotation` | 23.2056 |
| Calmar | `rotation` | 0.4880 |
| 最大回撤（越小越优） | `rotation` | 9.0875 |
| 平均换手（越小越优） | `mean_reversion` | 4.0765 |

## 区间体制（trending / choppy）

- Trending half (`second_half`): 2022-07-06 → 2024-12-31
- Choppy half (`first_half`): 2020-01-02 → 2022-07-05

| 策略 | 趋势段收益 % | 震荡段收益 % |
| --- | ---: | ---: |
| `rotation` | 3.74 | 24.30 |
| `mean_reversion` | 0.81 | 1.62 |
| `blend` | 3.74 | 24.30 |

- 趋势段优胜: `rotation`  ·  震荡段优胜: `rotation`

> regime split at midpoint (trending R^2=0.613, choppy R^2=0.066)
> half-returns derived from per-strategy rebalance_log equity-after series

## 相对表现（A vs B = A 减 B）

| 对比 | 收益差 pp | Sharpe 差 | MaxDD 差 pp |
| --- | ---: | ---: | ---: |
| `rotation` vs `mean_reversion` | +21.39 | +0.395 | -0.37 |
| `rotation` vs `blend` | +0.00 | +0.000 | +0.00 |
| `mean_reversion` vs `rotation` | -21.39 | -0.395 | +0.37 |
| `mean_reversion` vs `blend` | -21.39 | -0.395 | +0.37 |
| `blend` vs `rotation` | +0.00 | +0.000 | +0.00 |
| `blend` vs `mean_reversion` | +21.39 | +0.395 | -0.37 |

## 统计显著性检验 (Statistical hypothesis tests)

配对数 k = 6 · 显著性水平 α = 0.050

### Diebold-Mariano (1995) test (loss = -return)

| 配对 | DM stat | p (2-sided) | p (1-sided, A>B) | mean(L_a - L_b) | n |
| --- | ---: | ---: | ---: | ---: | ---: |
| `rotation_vs_mean_reversion` | -1.231 | 0.2185 | 0.1093 | -0.000872 | 242 |
| `rotation_vs_blend` | +0.000 | 1.0000 | 1.0000 | +0.000000 | 242 |
| `rotation_vs_buy_hold` | +0.591 | 0.5547 | 0.7227 | +0.000738 | 242 |
| `mean_reversion_vs_blend` | +1.231 | 0.2185 | 0.8907 | +0.000872 | 242 |
| `mean_reversion_vs_buy_hold` | +1.067 | 0.2859 | 0.8570 | +0.001610 | 242 |
| `blend_vs_buy_hold` | +0.591 | 0.5547 | 0.7227 | +0.000738 | 242 |

### Sharpe-ratio difference (Memmel 2003)

| 配对 | Sharpe_a | Sharpe_b | z | p (2-sided) | n |
| --- | ---: | ---: | ---: | ---: | ---: |
| `rotation_vs_mean_reversion` | +0.0737 | +0.0153 | +0.955 | 0.3395 | 242 |
| `rotation_vs_blend` | +0.0737 | +0.0737 | +0.000 | 1.0000 | 242 |
| `rotation_vs_buy_hold` | +0.0737 | +0.0647 | +0.184 | 0.8543 | 242 |
| `mean_reversion_vs_blend` | +0.0153 | +0.0737 | -0.955 | 0.3395 | 242 |
| `mean_reversion_vs_buy_hold` | +0.0153 | +0.0647 | -0.804 | 0.4216 | 242 |
| `blend_vs_buy_hold` | +0.0737 | +0.0647 | +0.184 | 0.8543 | 242 |

### Block bootstrap 95% CI on return differential

| 配对 | mean(A-B) | CI low | CI high | p (2-sided) | block | n_boot |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `rotation_vs_mean_reversion` | +0.000872 | -0.000414 | +0.002331 | 0.2090 | 10 | 1000 |
| `rotation_vs_blend` | +0.000000 | +0.000000 | +0.000000 | 1.0000 | 10 | 1000 |
| `rotation_vs_buy_hold` | -0.000738 | -0.002747 | +0.001536 | 0.5040 | 10 | 1000 |
| `mean_reversion_vs_blend` | -0.000872 | -0.002331 | +0.000414 | 0.2090 | 10 | 1000 |
| `mean_reversion_vs_buy_hold` | -0.001610 | -0.004363 | +0.001410 | 0.2450 | 10 | 1000 |
| `blend_vs_buy_hold` | -0.000738 | -0.002747 | +0.001536 | 0.5040 | 10 | 1000 |

### Multiple-testing correction (Bonferroni & Holm)

Bonferroni threshold α/k = 0.00833

| 配对 | DM raw p | DM survives Bonferroni? | DM survives Holm? | Sharpe raw p | Sharpe survives Bonferroni? | Sharpe survives Holm? |
| --- | ---: | :-: | :-: | ---: | :-: | :-: |
| `rotation_vs_mean_reversion` | 0.2185 | no | no | 0.3395 | no | no |
| `rotation_vs_blend` | 1.0000 | no | no | 1.0000 | no | no |
| `rotation_vs_buy_hold` | 0.5547 | no | no | 0.8543 | no | no |
| `mean_reversion_vs_blend` | 0.2185 | no | no | 0.3395 | no | no |
| `mean_reversion_vs_buy_hold` | 0.2859 | no | no | 0.4216 | no | no |
| `blend_vs_buy_hold` | 0.5547 | no | no | 0.8543 | no | no |

> DM loss_fn=negative_return (H1: strategy A's expected return differs from B's)
> Sharpe difference via Memmel (2003) closed-form, asymptotic z-test
> Block bootstrap: Politis-Romano (1994) circular, block_size=10, n_bootstrap=1000
> Multiple-testing correction over k=6 unordered pairs
> buy_hold synthesised from equal-weight passive return over window

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
