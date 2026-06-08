# Low-Volatility Strategy — Net-of-Cost Portfolio Backtest

Turns the **confirmed** `low_volatility@20` signal (`docs/research/lowvol-confirmation.md`)
into an implementable long-only basket and asks the screen→strategy question:
**does the cross-sectional edge survive real A-share frictions, and does it beat
naive equal-weight?**

Runner: `scripts/research/lowvol_portfolio_backtest.py` (deterministic). Monthly
rebalance, long the bottom-N lowest-`60d`-realized-vol names (equal weight),
2018→2024, survivorship-free + suspension-filtered. **Total-return prices**
(`close × adj_factor` — dividends matter, low-vol names are high-yield) for P&L;
ranking vol on unadjusted close (exactly as the validated factor defines it).
Costs charged on turnover each rebalance: commission 0.025% + slippage 0.05% +
过户费 0.001% both sides, + 印花税 0.05% on sells (~0.20% round-trip). Benchmark =
equal-weight of the same eligible universe (gross — a conservative bar, since it
pays no costs).

## Headline: the signal is real, but tradability is **universe-dependent**

| Universe | basket | **net CAGR** | net Sharpe | bench Sharpe | net ann-vol | bench vol | net maxDD | bench maxDD | turnover/yr | net excess CAGR |
|----------|--------|-------------|-----------|--------------|-------------|-----------|-----------|-------------|-------------|-----------------|
| **CSI300** (large/mid) | 30 | 4.78% | **0.44** | 0.22 | 12.3% | 18.6% | −13.0% | −23.0% | 2.7× | **+2.3%** |
| CSI300 | 50 | 5.35% | 0.45 | 0.22 | 13.7% | 18.6% | −15.1% | −23.0% | 2.6× | +2.9% |
| **CSI500** (mid/small) | 30 | 0.59% | 0.12 | 0.21 | 16.8% | 19.7% | −14.9% | −20.8% | 4.1× | **−1.7%** |
| CSI500 | 50 | 2.04% | 0.20 | 0.21 | 16.9% | 19.7% | −13.5% | −20.8% | 3.6× | −0.2% |

### CSI300 — it works
Net of costs the low-vol basket delivers **~2× the risk-adjusted return of
equal-weight** (Sharpe 0.44 vs 0.22), with **a third less volatility** and **half
the drawdown**. The win is mostly *risk reduction*, the classic low-vol anomaly —
absolute return is modest (the 2019–24 CSI300 was roughly flat). Crucially,
**costs barely dent it**: low-vol is a *low-turnover* strategy (~2.7×/yr, because
volatility is persistent), so the cost drag is only **~0.56% CAGR** (gross 5.34% →
net 4.78%). The edge clears even the conservative gross benchmark.

### CSI500 — it does NOT clearly survive costs
On mid/small-caps the long-only basket **fails to beat equal-weight net of
costs**: N=30 *underperforms* by −1.7% CAGR, N=50 only matches. The signal is
present *gross* (N=50 gross Sharpe 0.247 vs 0.211), but **turnover is ~50% higher
(3.6–4.1×/yr)** — small-cap vol ranks are less persistent, so the basket churns
more — and the extra ~0.8% CAGR of cost erases the edge. The basket still cuts
drawdown (−13/−15% vs −21%), so risk reduction survives even where the return
edge doesn't.

## The lesson (the actual answer to "扣完成本还剩多少")
**A validated cross-sectional IC ≠ a tradable long-only strategy.** The same
signal with IC ≈ 0.11 in *both* universes becomes a solid net strategy on liquid
large-caps (CSI300) and a marginal one on smaller-caps (CSI500), purely because of
**turnover × cost** and the long-only constraint (which discards the high-vol
short leg the IC partly rewards). Implementation — not signal strength — decides it.

Net takeaway: a **CSI300 low-volatility basket is the implementable form** of this
project's one confirmed edge; its value is steadier, lower-drawdown returns rather
than outsized P&L.

## Honest caveats
1. **Regime:** 2019–24 was a single, defensive-favoring window (large-cap/growth
   bear). Low-vol's edge is partly a defensive tilt; a momentum/risk-on regime
   would compress it.
2. **Benchmark is gross** equal-weight; netting its (low) turnover would shave a
   little off its return — a minor, conservative-for-low-vol simplification.
3. **Costs are a fixed-rate model** (no market impact / capacity). Turnover is
   low for CSI300 so capacity on large/mid-caps is reasonable; sizing on CSI500
   small-caps would face more impact than modeled — i.e. CSI500 is, if anything,
   *worse* than shown.
4. **Same vendor/methodology** as discovery+confirmation (Tushare, this pipeline).
5. Smarter turnover control (no-trade buffer, quarterly rebalance) *might* rescue
   CSI500 — but testing implementation variants until one passes is researcher
   degrees-of-freedom; that would need its own pre-registration, not a tweak here.
