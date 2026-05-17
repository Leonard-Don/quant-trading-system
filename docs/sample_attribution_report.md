# Policy Signal Factor — Attribution Report

- **Window**: `2026-04-17T07:22:48+00:00` → `2026-05-17T07:22:48+00:00` (30 days)
- **Rebalances in window**: 5 (factor ON: 5)
- **Factor-ON compounded return**: +4.5741% (proportional factor-OFF proxy: +3.8934%)
- **Factor contribution**: **+0.6807%** (hit rate: 100.00%)

### Top winner ETFs (factor added P&L)
| ETF | Contribution % | # rebalances |
|---|---:|---:|
| `515030` | +0.3470% | 4 |
| `512400` | +0.3117% | 5 |

### Per-rebalance breakdown
| Run at | Hold days | ON % | OFF % | Contribution % | Applied codes |
|---|---:|---:|---:|---:|---|
| `2026-04-18T02:00:00+00:00` | 5 | -0.0679% | -0.1136% | +0.0457% | 512400, 515030 |
| `2026-04-23T02:00:00+00:00` | 5 | +2.3702% | +2.2994% | +0.0708% | 512400 |
| `2026-04-28T02:00:00+00:00` | 5 | +1.0116% | +0.9111% | +0.1005% | 512400, 515030 |
| `2026-05-03T02:00:00+00:00` | 5 | +0.1575% | +0.0762% | +0.0814% | 512400, 515030 |
| `2026-05-08T02:00:00+00:00` | 9 | +1.0393% | +0.6790% | +0.3603% | 512400, 515030 |

---

### How to read this
- **Factor contribution = compounded ON return − proportional OFF proxy.** Positive means enabling the factor outperformed a post-overlay proxy where each touched ETF's final weight is scaled by weight_before / weight_after.
- **Hit rate** is the % of rebalances where the factor improved return that period. 50% is coin-flip; >55% over 20+ rebalances starts to look like signal.
- **Per-code contribution** sums the marginal P&L from the policy adjustment on each ETF after the same proportional final-weight scaling used by the report-level proxy.
- This is **attribution, not back-testing**: no transaction costs, no rebalance lag, cash assumed to earn zero, and the off leg is a proportional post-overlay proxy rather than a full second strategy run.
