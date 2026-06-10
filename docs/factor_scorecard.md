# 因子记分卡 (Phase 1, multi-horizon)

> Universe: **csi300 (survivorship-free union)** (526 symbols usable). **Survivorship-free + suspension-filtered (无幸存者偏差 + 停牌过滤)**:universe = 回测区间内历史成分的并集(点位时间);每个调仓日的横截面= 当日成分 − 当日停牌。点位时间;OOS = 后 30% 时序;前向收益用全收益价(close×adj_factor);门槛 OOS IC ≥ 0.03 且 ICIR>0 且 sign-stable;Holm(α=0.05) 跨全部 factor×horizon 单元控制多重检验,见 Holm 列。
> Horizons (持有天数): h=5, h=20, h=60

## factor × horizon → OOS IC

| factor | h=5 | h=20 | h=60 |
|---|--:|--:|--:|
| low_volatility | 0.0429 | 0.1131 | 0.2575 |
| momentum_12_1 | -0.0674 | -0.0144 | 0.0128 |
| short_reversal | 0.0056 | 0.0496 | -0.0178 |
| turnover_reversal | -0.0153 | -0.0361 | -0.0916 |
| roe | -0.0524 | -0.0782 | -0.1377 |
| profit_growth | -0.0697 | -0.0931 | -0.1650 |
| revenue_growth | -0.0331 | -0.1037 | -0.2093 |
| net_inflow | -0.0032 | -0.0154 | 0.0117 |

## factor × horizon → PASS / FAIL

| factor | h=5 | h=20 | h=60 |
|---|:--:|:--:|:--:|
| low_volatility | ✗ | ✓ | ✗ |
| momentum_12_1 | ✗ | ✗ | ✗ |
| short_reversal | ✗ | ✗ | ✗ |
| turnover_reversal | ✗ | ✗ | ✗ |
| roe | ✗ | ✗ | ✗ |
| profit_growth | ✗ | ✗ | ✗ |
| revenue_growth | ✗ | ✗ | ✗ |
| net_inflow | ✗ | ✗ | ✗ |

## 过关因子 (factor@horizon)

low_volatility@20 (Holm✗)

## 明细 h=5

# 因子记分卡 (Phase 1)

> Survivorship-free + suspension-filtered:universe = 历史成分并集(点位时间);横截面 = 当日成分 − 当日停牌。OOS = 后 30% 时序;前向收益用全收益价(close×adj_factor)。

| factor | n | mean IC | ICIR | OOS IC | OOS ICIR | p(OOS) | Holm | sign-stable | verdict |
|---|--:|--:|--:|--:|--:|--:|:--:|:--:|:--:|
| low_volatility | 46 | 0.0623 | 0.247 | 0.0429 | 0.164 | 0.2827 | ✗ | ✗ | FAIL |
| short_reversal | 46 | 0.0212 | 0.123 | 0.0056 | 0.035 | 0.4514 | ✗ | ✗ | FAIL |
| net_inflow | 46 | -0.0033 | -0.026 | -0.0032 | -0.025 | 0.5347 | ✗ | ✗ | FAIL |
| turnover_reversal | 46 | -0.0194 | -0.108 | -0.0153 | -0.119 | 0.6621 | ✗ | ✗ | FAIL |
| revenue_growth | 46 | -0.0324 | -0.223 | -0.0331 | -0.253 | 0.8112 | ✗ | ✓ | FAIL |
| roe | 46 | -0.0336 | -0.204 | -0.0524 | -0.386 | 0.9061 | ✗ | ✗ | FAIL |
| momentum_12_1 | 46 | -0.0422 | -0.198 | -0.0674 | -0.359 | 0.8909 | ✗ | ✓ | FAIL |
| profit_growth | 46 | -0.0360 | -0.283 | -0.0697 | -0.628 | 0.9793 | ✗ | ✓ | FAIL |

**过关因子:** 无 —— 不启动 Phase 2(诚实门)

## 明细 h=20

# 因子记分卡 (Phase 1)

> Survivorship-free + suspension-filtered:universe = 历史成分并集(点位时间);横截面 = 当日成分 − 当日停牌。OOS = 后 30% 时序;前向收益用全收益价(close×adj_factor)。

| factor | n | mean IC | ICIR | OOS IC | OOS ICIR | p(OOS) | Holm | sign-stable | verdict |
|---|--:|--:|--:|--:|--:|--:|:--:|:--:|:--:|
| low_volatility | 46 | 0.0786 | 0.331 | 0.1131 | 0.535 | 0.0379 | ✗ | ✓ | PASS |
| short_reversal | 46 | 0.0149 | 0.084 | 0.0496 | 0.291 | 0.1567 | ✗ | ✗ | FAIL |
| momentum_12_1 | 46 | 0.0210 | 0.095 | -0.0144 | -0.073 | 0.6015 | ✗ | ✗ | FAIL |
| net_inflow | 46 | 0.0170 | 0.134 | -0.0154 | -0.124 | 0.6695 | ✗ | ✗ | FAIL |
| turnover_reversal | 46 | -0.0055 | -0.031 | -0.0361 | -0.225 | 0.7836 | ✗ | ✗ | FAIL |
| roe | 46 | -0.0264 | -0.162 | -0.0782 | -0.589 | 0.9732 | ✗ | ✗ | FAIL |
| profit_growth | 46 | -0.0407 | -0.331 | -0.0931 | -0.802 | 0.9937 | ✗ | ✗ | FAIL |
| revenue_growth | 46 | -0.0456 | -0.338 | -0.1037 | -0.670 | 0.9844 | ✗ | ✗ | FAIL |

**过关因子:** low_volatility

## 明细 h=60

# 因子记分卡 (Phase 1)

> Survivorship-free + suspension-filtered:universe = 历史成分并集(点位时间);横截面 = 当日成分 − 当日停牌。OOS = 后 30% 时序;前向收益用全收益价(close×adj_factor)。

| factor | n | mean IC | ICIR | OOS IC | OOS ICIR | p(OOS) | Holm | sign-stable | verdict |
|---|--:|--:|--:|--:|--:|--:|:--:|:--:|:--:|
| low_volatility | 44 | 0.1205 | 0.601 | 0.2575 | 2.156 | 0.0000 | ✓ | ✗ | FAIL |
| momentum_12_1 | 44 | 0.0535 | 0.298 | 0.0128 | 0.070 | 0.4022 | ✗ | ✗ | FAIL |
| net_inflow | 44 | 0.0225 | 0.193 | 0.0117 | 0.109 | 0.3506 | ✗ | ✗ | FAIL |
| short_reversal | 44 | -0.0096 | -0.061 | -0.0178 | -0.139 | 0.6877 | ✗ | ✗ | FAIL |
| turnover_reversal | 44 | -0.0217 | -0.126 | -0.0916 | -0.702 | 0.9875 | ✗ | ✗ | FAIL |
| roe | 44 | -0.0395 | -0.241 | -0.1377 | -1.179 | 0.9995 | ✗ | ✗ | FAIL |
| profit_growth | 44 | -0.0604 | -0.402 | -0.1650 | -1.495 | 0.9999 | ✗ | ✗ | FAIL |
| revenue_growth | 44 | -0.0754 | -0.483 | -0.2093 | -2.143 | 1.0000 | ✗ | ✗ | FAIL |

**过关因子:** 无 —— 不启动 Phase 2(诚实门)
