# 因子记分卡 (Phase 1, multi-horizon)

> Universe: **csi300 (survivorship-free union)** (526 symbols usable). **Survivorship-free + suspension-filtered (无幸存者偏差 + 停牌过滤)**:universe = 回测区间内历史成分的并集(点位时间);每个调仓日的横截面= 当日成分 − 当日停牌。点位时间;OOS = 后 30% 时序;门槛 OOS IC ≥ 0.03 且 ICIR>0 且 sign-stable。
> Horizons (持有天数): h=5, h=20, h=60

## factor × horizon → OOS IC

| factor | h=5 | h=20 | h=60 |
|---|--:|--:|--:|
| low_volatility | 0.0402 | 0.1050 | 0.2453 |
| momentum_12_1 | -0.0665 | -0.0103 | 0.0252 |
| short_reversal | 0.0071 | 0.0478 | -0.0185 |
| turnover_reversal | -0.0146 | -0.0356 | -0.0960 |
| roe | -0.0527 | -0.0884 | -0.1691 |
| profit_growth | -0.0663 | -0.0933 | -0.1750 |
| revenue_growth | -0.0301 | -0.1063 | -0.2204 |
| net_inflow | -0.0042 | -0.0164 | 0.0104 |

## factor × horizon → PASS / FAIL

| factor | h=5 | h=20 | h=60 |
|---|:--:|:--:|:--:|
| low_volatility | ✗ | ✓ | ✗ |
| momentum_12_1 | ✗ | ✗ | ✗ |
| short_reversal | ✗ | ✓ | ✗ |
| turnover_reversal | ✗ | ✗ | ✗ |
| roe | ✗ | ✗ | ✗ |
| profit_growth | ✗ | ✗ | ✗ |
| revenue_growth | ✗ | ✗ | ✗ |
| net_inflow | ✗ | ✗ | ✗ |

## 过关因子 (factor@horizon)

low_volatility@20, short_reversal@20

## 明细 h=5

# 因子记分卡 (Phase 1)

> Survivorship-free + suspension-filtered:universe = 历史成分并集(点位时间);横截面 = 当日成分 − 当日停牌。OOS = 后 30% 时序。

| factor | n | mean IC | ICIR | OOS IC | sign-stable | verdict |
|---|--:|--:|--:|--:|:--:|:--:|
| low_volatility | 46 | 0.0603 | 0.240 | 0.0402 | ✗ | FAIL |
| short_reversal | 46 | 0.0247 | 0.143 | 0.0071 | ✗ | FAIL |
| net_inflow | 46 | -0.0064 | -0.050 | -0.0042 | ✗ | FAIL |
| turnover_reversal | 46 | -0.0203 | -0.113 | -0.0146 | ✗ | FAIL |
| revenue_growth | 46 | -0.0321 | -0.220 | -0.0301 | ✓ | FAIL |
| roe | 46 | -0.0356 | -0.218 | -0.0527 | ✗ | FAIL |
| profit_growth | 46 | -0.0352 | -0.279 | -0.0663 | ✓ | FAIL |
| momentum_12_1 | 46 | -0.0423 | -0.200 | -0.0665 | ✓ | FAIL |

**过关因子:** 无 —— 不启动 Phase 2(诚实门)

## 明细 h=20

# 因子记分卡 (Phase 1)

> Survivorship-free + suspension-filtered:universe = 历史成分并集(点位时间);横截面 = 当日成分 − 当日停牌。OOS = 后 30% 时序。

| factor | n | mean IC | ICIR | OOS IC | sign-stable | verdict |
|---|--:|--:|--:|--:|:--:|:--:|
| low_volatility | 46 | 0.0777 | 0.335 | 0.1050 | ✓ | PASS |
| short_reversal | 46 | 0.0206 | 0.120 | 0.0478 | ✓ | PASS |
| momentum_12_1 | 46 | 0.0191 | 0.088 | -0.0103 | ✗ | FAIL |
| net_inflow | 46 | 0.0124 | 0.100 | -0.0164 | ✗ | FAIL |
| turnover_reversal | 46 | -0.0108 | -0.062 | -0.0356 | ✗ | FAIL |
| roe | 46 | -0.0373 | -0.238 | -0.0884 | ✗ | FAIL |
| profit_growth | 46 | -0.0428 | -0.354 | -0.0933 | ✗ | FAIL |
| revenue_growth | 46 | -0.0493 | -0.369 | -0.1063 | ✗ | FAIL |

**过关因子:** low_volatility, short_reversal

## 明细 h=60

# 因子记分卡 (Phase 1)

> Survivorship-free + suspension-filtered:universe = 历史成分并集(点位时间);横截面 = 当日成分 − 当日停牌。OOS = 后 30% 时序。

| factor | n | mean IC | ICIR | OOS IC | sign-stable | verdict |
|---|--:|--:|--:|--:|:--:|:--:|
| low_volatility | 44 | 0.1220 | 0.651 | 0.2453 | ✗ | FAIL |
| momentum_12_1 | 44 | 0.0469 | 0.276 | 0.0252 | ✗ | FAIL |
| net_inflow | 44 | 0.0149 | 0.131 | 0.0104 | ✗ | FAIL |
| short_reversal | 44 | -0.0034 | -0.022 | -0.0185 | ✗ | FAIL |
| turnover_reversal | 44 | -0.0328 | -0.201 | -0.0960 | ✗ | FAIL |
| roe | 44 | -0.0672 | -0.434 | -0.1691 | ✗ | FAIL |
| profit_growth | 44 | -0.0739 | -0.521 | -0.1750 | ✗ | FAIL |
| revenue_growth | 44 | -0.0880 | -0.587 | -0.2204 | ✗ | FAIL |

**过关因子:** 无 —— 不启动 Phase 2(诚实门)
