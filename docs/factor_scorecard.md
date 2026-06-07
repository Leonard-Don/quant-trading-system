# 因子记分卡 (Phase 1, multi-horizon)

> Universe: **csi300** (298 symbols usable). Universe 用当前成分/流动性名单近似历史池(轻微幸存者偏差)。点位时间;OOS = 后 30% 时序;门槛 OOS IC ≥ 0.03 且 ICIR>0 且 sign-stable。
> Horizons (持有天数): h=5, h=20, h=60

## factor × horizon → OOS IC

| factor | h=5 | h=20 | h=60 |
|---|--:|--:|--:|
| low_volatility | 0.0306 | 0.0559 | 0.1653 |
| momentum_12_1 | -0.0852 | -0.0610 | -0.0470 |
| short_reversal | 0.0258 | 0.0446 | 0.0065 |
| turnover_reversal | -0.0034 | 0.0230 | 0.0029 |
| roe | -0.0437 | -0.0705 | -0.1383 |
| profit_growth | -0.0450 | -0.0721 | -0.1383 |
| revenue_growth | -0.0238 | -0.0723 | -0.1720 |
| net_inflow | -0.0207 | -0.0197 | -0.0289 |

## factor × horizon → PASS / FAIL

| factor | h=5 | h=20 | h=60 |
|---|:--:|:--:|:--:|
| low_volatility | ✗ | ✗ | ✗ |
| momentum_12_1 | ✗ | ✗ | ✗ |
| short_reversal | ✗ | ✗ | ✗ |
| turnover_reversal | ✗ | ✗ | ✗ |
| roe | ✗ | ✗ | ✗ |
| profit_growth | ✗ | ✗ | ✗ |
| revenue_growth | ✗ | ✗ | ✗ |
| net_inflow | ✗ | ✗ | ✗ |

## 过关因子 (factor@horizon)

无 (none) —— 不启动 Phase 2(诚实门)

## 明细 h=5

# 因子记分卡 (Phase 1)

> Universe 用当前流动性名单近似历史池(轻微幸存者偏差)。点位时间;OOS = 后 30% 时序。

| factor | n | mean IC | ICIR | OOS IC | sign-stable | verdict |
|---|--:|--:|--:|--:|:--:|:--:|
| low_volatility | 46 | 0.0447 | 0.169 | 0.0306 | ✗ | FAIL |
| short_reversal | 46 | 0.0178 | 0.100 | 0.0258 | ✗ | FAIL |
| turnover_reversal | 46 | -0.0057 | -0.030 | -0.0034 | ✗ | FAIL |
| net_inflow | 46 | -0.0093 | -0.071 | -0.0207 | ✗ | FAIL |
| revenue_growth | 46 | -0.0250 | -0.182 | -0.0238 | ✗ | FAIL |
| roe | 46 | -0.0332 | -0.215 | -0.0437 | ✗ | FAIL |
| profit_growth | 46 | -0.0293 | -0.226 | -0.0450 | ✓ | FAIL |
| momentum_12_1 | 46 | -0.0470 | -0.214 | -0.0852 | ✓ | FAIL |

**过关因子:** 无 —— 不启动 Phase 2(诚实门)

## 明细 h=20

# 因子记分卡 (Phase 1)

> Universe 用当前流动性名单近似历史池(轻微幸存者偏差)。点位时间;OOS = 后 30% 时序。

| factor | n | mean IC | ICIR | OOS IC | sign-stable | verdict |
|---|--:|--:|--:|--:|:--:|:--:|
| low_volatility | 46 | 0.0363 | 0.142 | 0.0559 | ✗ | FAIL |
| short_reversal | 46 | 0.0098 | 0.055 | 0.0446 | ✗ | FAIL |
| turnover_reversal | 46 | 0.0236 | 0.144 | 0.0230 | ✗ | FAIL |
| net_inflow | 46 | 0.0121 | 0.090 | -0.0197 | ✗ | FAIL |
| momentum_12_1 | 46 | 0.0089 | 0.038 | -0.0610 | ✗ | FAIL |
| roe | 46 | -0.0415 | -0.298 | -0.0705 | ✗ | FAIL |
| profit_growth | 46 | -0.0394 | -0.289 | -0.0721 | ✗ | FAIL |
| revenue_growth | 46 | -0.0427 | -0.316 | -0.0723 | ✗ | FAIL |

**过关因子:** 无 —— 不启动 Phase 2(诚实门)

## 明细 h=60

# 因子记分卡 (Phase 1)

> Universe 用当前流动性名单近似历史池(轻微幸存者偏差)。点位时间;OOS = 后 30% 时序。

| factor | n | mean IC | ICIR | OOS IC | sign-stable | verdict |
|---|--:|--:|--:|--:|:--:|:--:|
| low_volatility | 44 | 0.0537 | 0.272 | 0.1653 | ✗ | FAIL |
| short_reversal | 44 | -0.0040 | -0.024 | 0.0065 | ✗ | FAIL |
| turnover_reversal | 44 | 0.0216 | 0.155 | 0.0029 | ✗ | FAIL |
| net_inflow | 44 | 0.0057 | 0.046 | -0.0289 | ✗ | FAIL |
| momentum_12_1 | 44 | 0.0290 | 0.161 | -0.0470 | ✗ | FAIL |
| profit_growth | 44 | -0.0718 | -0.508 | -0.1383 | ✗ | FAIL |
| roe | 44 | -0.0791 | -0.589 | -0.1383 | ✗ | FAIL |
| revenue_growth | 44 | -0.0823 | -0.564 | -0.1720 | ✗ | FAIL |

**过关因子:** 无 —— 不启动 Phase 2(诚实门)
