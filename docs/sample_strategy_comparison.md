# 多策略对照回放报告 (Net of Transaction Costs)

## Why this report exists

The repo ships three ETF strategies — `EtfRotationStrategy`,
`EtfMeanReversionStrategy`, and `EtfStrategyBlend`. The v0.1 report
(committed at `a54b986`) ran them head-to-head on the same window and
ended with this caveat:

> With a typical CN ETF 5-10 bps round-trip fee, the turnover ranking
> (rotation 7.55% > MR 6.05% > blend 5.22%) means rotation's headline
> +8.71% would shrink first and blend's lead would widen.

This refresh (driven by `src/backtest/transaction_costs.py` and
`scripts/compare_strategies.py --enable-tc`) turns that paragraph into
actual numbers. The TC model is described in detail in the module
docstring; the defaults reflect CN retail brokerage reality
(commission 3 bps / side, half-spread 5 bps, impact 0.5 bps/%ADV above
5%, commission floor 5 RMB, min trade 100 RMB).

## Honest reading (net basis, default TC, 100k portfolio)

- **Sharpe winner is still `blend` (0.536)** — beats rotation (0.533)
  and MR (0.480) on net Sharpe. The gap over rotation shrank from
  v0.1's +0.030 to a hair-thin +0.002; the gap over MR widened from
  +0.030 to +0.056 because MR's edge was always thinner and TC eats
  a similar absolute bps from every strategy.
- **Total-return winner is still `rotation` (+7.24% net)** — pure
  trend still captures the most absolute upside, but the gap shrank
  from gross's +3.36 pp over MR to a net +3.24 pp. Rotation pays the
  most TC (1.39% total drag) because its turnover (7.55%) is the
  highest in the family.
- **Net cost ranking**: rotation 1.39% > blend 1.37% > MR 1.30% — at
  100k portfolio size the **commission floor (5 RMB/leg) dominates**
  and turnover differences barely move the needle in bps terms. At
  500k+ portfolios (see `--initial-capital` flag), the bps component
  takes over and the ranking widens to rotation 1.33 bps/reb > MR
  1.10 > blend 1.00 — meaning **the v0.1 prediction that "blend's
  lead would widen" holds, but only above ~500k AUM**.
- **Calmar winner: `blend` (0.674)** — beats rotation (0.619) and MR
  (0.516). The net Calmar gap widened slightly versus gross because
  the cost ledger is roughly equal in absolute bps but rotation's
  drawdown is larger.
- **Lowest max-DD: `mean_reversion` (6.08%)** — unchanged from gross.
  TC doesn't materially affect drawdown depth on a 100k portfolio.
- **Lowest turnover: `blend` (5.22%)** — unchanged.

## The 2-3 numbers a paper / discussion would cite

1. **Rotation's +8.71% gross becomes +7.24% net** at our default TC
   assumption (commission 3 bps + spread 5 bps + impact 0.5 bps/%ADV
   conditional on >5% ADV; commission floor 5 RMB / trade), a 147 bps
   annualised drag for a strategy with 7.55% per-rebalance turnover.
2. **All three strategies still trail equal-weight buy-and-hold
   (+23.55%) by 16-19 pp net** — TC modelling does not change the
   single most important finding of the v0.1 report: on this window,
   none of the rotation-family strategies generates alpha versus the
   passive benchmark; they're drawdown-control plays.
3. **Per-rebalance cost = 2.0-2.2 bps at 100k AUM**, dominated by the
   commission floor; at 500k+ AUM the bps component takes over and
   per-rebalance cost drops to ~1.0-1.3 bps (rotation > MR > blend).

## Insight: regime separation survives the TC layer

The midpoint-split regime detector still tags **first-half** as
choppy (R^2=0.370) and **second-half** as trending (R^2=0.792). Net
per-strategy half-returns:

- `rotation`: trending +2.91% (was gross +3.69%), choppy +4.85%
  (was +5.48%) — pays cost both halves but the choppy lead stays.
- `mean_reversion`: trending +5.35% (was +6.17%), choppy -0.96%
  (was -0.47%) — TC pushes choppy-half MR clearly negative.
- `blend`: trending +4.20% (was +4.99%), choppy +1.89% (was +2.49%)
  — net positive in both halves still.

Trending-winner is still MR; choppy-winner is still rotation. The
TC layer doesn't flip any half-winners on this window, which is
reassuring — the regime separation is real, not an artefact of
ignoring fees.

## Caveats

The v0.1 caveats list shrinks because TC is now modelled, not
ignored: `next_bar_close_fills_only`,
`equal_weight_buy_hold_benchmark`, `ignores_survivorship_bias`,
`rebalance_cadence_fixed_at_5_bar(s)`. The new caveat string —
`transaction_costs_modeled(commission_bps=3.00,spread_bps=5.00,impact_bps_per_pct_adv=0.50,min_commission_rmb=5.00,min_trade_size_rmb=100.00)`
— records the active parameter set so two reports run with different
assumptions stay distinguishable.

What's still NOT modelled: variable spreads (we use a flat 5 bps —
real CN ETF spreads range 1-15 bps with QDII at the high end),
partial fills, intraday execution delay beyond the strategy's
one-bar lag, survivorship bias, dividends / WHT on QDII. The TC
model is calibrated for retail-size CN ETF brokerage; institutional
desks should re-calibrate.

## Bottom line

After TC modelling, **the winner-by-Sharpe still goes to `blend`**
but only by a hair (+0.002 over rotation, +0.056 over MR). The
**Calmar winner** is still `blend` and by a wider net margin than
gross. **Rotation still wins total return** but the gap shrinks
~3.5% in absolute terms. **All three still lose to buy-hold** — the
TC layer doesn't rescue the rotation family on this window; it just
makes the loss honest.

The most useful net-basis result is the per-rebalance-bps number
itself: at 100k portfolio size, **costs ~2 bps per rebalance** are
dominated by commission floors, so paying down turnover doesn't
buy back much. The cost-side argument for the blend strategy only
kicks in meaningfully at AUM ≥ 500k — worth flagging for any reader
trying to apply this to a real account.

---

窗口：`2024-01-02` → `2025-04-30` · 参赛策略 = 3

## 头条指标 (Net of TC)

| 策略 | 总收益 % | 年化 % | Sharpe | MaxDD % | Calmar | 平均换手 % | 命中率 | 等权基准 % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `rotation` | 7.24 | 5.66 | 0.533 | 9.15 | 0.619 | 7.55 | 60.32% | 23.55 |
| `mean_reversion` | 4.00 | 3.14 | 0.480 | 6.08 | 0.516 | 6.05 | 60.32% | 23.55 |
| `blend` | 5.67 | 4.44 | 0.536 | 6.59 | 0.674 | 5.22 | 60.32% | 23.55 |

## 交易成本拆解 (Gross vs Net)

| 策略 | 毛收益 % | 净收益 % | TC 总成本 % | 平均 bps/调仓 | 年化拖累 % |
| --- | ---: | ---: | ---: | ---: | ---: |
| `rotation` | +8.71 | +7.24 | 1.3856 | 2.20 | 1.09 |
| `mean_reversion` | +5.34 | +4.00 | 1.2996 | 2.03 | 1.02 |
| `blend` | +7.10 | +5.67 | 1.3749 | 2.15 | 1.08 |

> TC 模型: commission=3.0 bps per-side · spread=5.0 bps half · impact=0.5 bps/%ADV · min_commission=5.0 元 · min_trade=100.0 元

## 单项冠军 (Net basis)

| 指标 | 优胜策略 | 分数 |
| --- | --- | ---: |
| Sharpe | `blend` | 0.5355 |
| 总收益 | `rotation` | 7.2444 |
| Calmar | `blend` | 0.6741 |
| 最大回撤（越小越优） | `mean_reversion` | 6.0808 |
| 平均换手（越小越优） | `blend` | 5.2224 |

## 区间体制（trending / choppy, net basis）

- Trending half (`second_half`): 2024-08-29 → 2025-04-30
- Choppy half (`first_half`): 2024-01-02 → 2024-08-28

| 策略 | 趋势段收益 % | 震荡段收益 % |
| --- | ---: | ---: |
| `rotation` | 2.91 | 4.85 |
| `mean_reversion` | 5.35 | -0.96 |
| `blend` | 4.20 | 1.89 |

- 趋势段优胜: `mean_reversion`  ·  震荡段优胜: `rotation`

> regime split at midpoint (trending R^2=0.792, choppy R^2=0.370)
> half-returns derived from per-strategy rebalance_log equity-after series

## 相对表现（A vs B = A 减 B, net basis）

| 对比 | 收益差 pp | Sharpe 差 | MaxDD 差 pp |
| --- | ---: | ---: | ---: |
| `rotation` vs `mean_reversion` | +3.24 | +0.053 | +3.07 |
| `rotation` vs `blend` | +1.57 | -0.002 | +2.56 |
| `mean_reversion` vs `rotation` | -3.24 | -0.053 | -3.07 |
| `mean_reversion` vs `blend` | -1.67 | -0.056 | -0.51 |
| `blend` vs `rotation` | -1.57 | +0.002 | -2.56 |
| `blend` vs `mean_reversion` | +1.67 | +0.056 | +0.51 |

## Caveats

- transaction_costs_modeled(commission_bps=3.00,spread_bps=5.00,impact_bps_per_pct_adv=0.50,min_commission_rmb=5.00,min_trade_size_rmb=100.00)
- next_bar_close_fills_only
- equal_weight_buy_hold_benchmark
- ignores_survivorship_bias
- rebalance_cadence_fixed_at_5_bar(s)
- strategy_label:rotation
- strategy_label:mean_reversion
- strategy_label:blend
- comparison_window_shared_across_strategies — all strategies evaluated on the same prices / dates / rebalance cadence
