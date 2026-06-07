# 因子记分卡 (Phase 1)

> Universe 用当前流动性名单近似历史池(轻微幸存者偏差)。点位时间;OOS = 后 30% 时序。

| factor | n | mean IC | ICIR | OOS IC | sign-stable | verdict |
|---|--:|--:|--:|--:|:--:|:--:|
| low_volatility | 45 | 0.0089 | 0.026 | 0.0512 | ✗ | FAIL |
| short_reversal | 45 | -0.0251 | -0.091 | 0.0434 | ✗ | FAIL |
| net_inflow | 45 | 0.0218 | 0.109 | -0.0278 | ✗ | FAIL |
| momentum_12_1 | 45 | 0.0596 | 0.192 | -0.0341 | ✓ | FAIL |
| turnover_reversal | 45 | -0.0191 | -0.082 | -0.0423 | ✗ | FAIL |
| roe | 45 | -0.0597 | -0.290 | -0.0695 | ✗ | FAIL |
| profit_growth | 45 | -0.0470 | -0.187 | -0.0822 | ✗ | FAIL |
| revenue_growth | 45 | -0.0640 | -0.252 | -0.1448 | ✗ | FAIL |

**过关因子:** 无 —— 不启动 Phase 2(诚实门)