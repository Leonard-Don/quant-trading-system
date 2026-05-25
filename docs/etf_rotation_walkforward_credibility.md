# ETF Rotation Walk-Forward Credibility Report

- Generated: `2026-05-25`
- Price source: `akshare fetch 2020-01-01..2026-05-22, complete rows from 2021-06-01, default ETF universe`
- Windows: 11 (11 comparable vs benchmark)
- Benchmark: `equal_weight_buy_hold`
- Verdict: **mixed_watchlist**
- Execution contract: manual-only; not auto-ordering; no broker API calls.

## Headline

- Mean OOS return: +3.99%
- Mean benchmark return: +5.02%
- Mean OOS excess return: -1.03%
- Win rate vs benchmark: 36.36%
- Mean OOS Sharpe: 1.11
- Worst OOS drawdown: 8.27%
- Avg trades/window: 50.55

## Window Detail

| Test window | Strategy return | Benchmark return | Excess | Sharpe | Max DD | Trades |
|---|---:|---:|---:|---:|---:|---:|
| 2023-06-29 → 2023-09-25 | +1.05% | +4.02% | -2.97% | 0.81 | 3.01% | 40 |
| 2023-09-26 → 2023-12-29 | -1.32% | -3.93% | +2.62% | -2.56 | 1.65% | 29 |
| 2024-01-02 → 2024-04-09 | +7.61% | +5.84% | +1.77% | 4.34 | 1.90% | 29 |
| 2024-04-10 → 2024-07-11 | -1.82% | -0.81% | -1.01% | -0.65 | 5.67% | 49 |
| 2024-07-12 → 2024-10-17 | +4.48% | +4.79% | -0.31% | 0.99 | 7.11% | 35 |
| 2024-10-18 → 2025-01-15 | -1.92% | -1.61% | -0.31% | -0.68 | 5.65% | 52 |
| 2025-01-16 → 2025-04-23 | +2.91% | +10.26% | -7.35% | 0.88 | 6.94% | 72 |
| 2025-04-24 → 2025-07-25 | +3.74% | +8.04% | -4.30% | 2.11 | 2.13% | 67 |
| 2025-07-28 → 2025-10-30 | +17.31% | +15.55% | +1.76% | 3.84 | 2.67% | 62 |
| 2025-10-31 → 2026-01-29 | +17.32% | +16.49% | +0.83% | 4.37 | 4.76% | 75 |
| 2026-01-30 → 2026-05-12 | -5.51% | -3.44% | -2.07% | -1.25 | 8.27% | 46 |

## Interpretation

Treat `credible_watchlist` as permission to keep manually tracking the signal, not as evidence of production edge. `mixed_watchlist` means the strategy has some useful regimes but needs sizing discipline and continued audit. `not_credible` means the default scoring layer should not guide real allocation without redesign.

## Caveats

- Equal-weight buy-and-hold is a naive benchmark, not Leonard's exact executed portfolio.
- Walk-forward windows are historical and do not include future liquidity, premium/discount, tax, or execution constraints beyond the configured commission/slippage parameters.
- This report evaluates the scoring/backtest layer; live decisions must still use the manual trade plan, premium vetoes, and risk rules.
- Manual-only remains a hard contract: this project produces suggestions, not orders.
