"""Net-of-cost backtest of a low-volatility long-only basket on A-shares.

Turns the VALIDATED low_volatility@20 signal (see docs/research/lowvol-confirmation.md)
into an implementable monthly-rebalanced portfolio and asks the only question that
matters for a screen-to-strategy step: **does the cross-sectional edge survive
real A-share trading frictions, and is its risk-adjusted return actually better
than naive equal-weight?**

Honesty fixes baked in (a low-vol backtest lies without these):
  * TOTAL-RETURN prices — cached Tushare `daily` is UNADJUSTED; low-vol names are
    high-dividend (banks/utilities), so price-only returns understate them. We
    fetch `adj_factor` and use adjusted close for P&L. (Ranking still uses the
    unadjusted-close vol, exactly as the validated factor defines it.)
  * Survivorship-free + suspension-filtered universe (reuses the #145 harness).
  * Point-in-time: vol from history <= D; period return D -> next rebalance.
  * Realistic A-share costs: commission + slippage + 过户费 (both sides) + 印花税
    (sell only), charged on turnover each rebalance.
  * Benchmark = EQUAL-WEIGHT of the same eligible universe (isolates the low-vol
    tilt from plain diversification), gross and net.

Deterministic, no LLM. Prints a JSON summary. adj_factor is pickle-cached under
data/_factor_cache/{sym}_adj.pkl so re-runs are fast.

Usage:
  .venv/bin/python scripts/research/lowvol_portfolio_backtest.py --index 000300.SH --baskets 20,30,50
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Realistic A-share friction rates (match the #144 cost profile + a discount broker)
COMMISSION = 0.00025   # 0.025% both sides
SLIPPAGE = 0.0005      # 0.05% both sides (liquid large/mid caps)
TRANSFER = 0.00001     # 过户费 0.001% both sides
STAMP = 0.0005         # 印花税 0.05% SELL only
BUY_RATE = COMMISSION + SLIPPAGE + TRANSFER            # 0.076%
SELL_RATE = COMMISSION + SLIPPAGE + TRANSFER + STAMP   # 0.126%
TRADING_DAYS = 252.0
PERIODS_PER_YEAR = 12.0


def monthly_rebalance_dates(trading_dates) -> list:
    s = pd.Series(1, index=pd.DatetimeIndex(trading_dates))
    return [pd.Timestamp(g.index[0]) for _, g in s.groupby([s.index.year, s.index.month])]


def _adj_close_map(symbols, panel, provider, cache_dir):
    """adjusted_close[sym] = close * adj_factor, joined exactly on trade_date.
    adj_factor is pickle-cached per symbol; fetched throttle-aware in batches."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    pro = provider._get_pro_client()
    out = {}
    to_fetch = []
    for sym in symbols:
        p = cache_dir / f"{sym}_adj.pkl"
        if p.exists():
            out[sym] = pd.read_pickle(p)
        else:
            to_fetch.append(sym)
    print(f"  adj_factor: {len(out)} cached, {len(to_fetch)} to fetch", file=sys.stderr)
    BATCH = 160
    for i in range(0, len(to_fetch), BATCH):
        batch = to_fetch[i : i + BATCH]
        for sym in batch:
            try:
                af = pro.adj_factor(ts_code=sym, start_date="20180101", end_date="20241231")
                if af is None or af.empty:
                    s = pd.Series(dtype=float)
                else:
                    af = af.copy()
                    af["trade_date"] = pd.to_datetime(af["trade_date"])
                    s = af.sort_values("trade_date").set_index("trade_date")["adj_factor"].astype(float)
            except Exception:
                s = pd.Series(dtype=float)
            s.to_pickle(cache_dir / f"{sym}_adj.pkl")
            out[sym] = s
        if i + BATCH < len(to_fetch):
            time.sleep(62)
    # build adjusted close per symbol on the panel's own price index (exact join)
    adj = {}
    for sym in symbols:
        if sym not in panel.prices:
            continue
        px = panel.prices[sym]
        af = out.get(sym)
        if af is None or af.empty:
            adj[sym] = px["close"].astype(float)  # fall back to raw (no div adj)
        else:
            factor = af.reindex(px.index)
            factor = factor.ffill().bfill()
            adj[sym] = (px["close"].astype(float) * factor).rename(sym)
    return adj


def _price_at(series: pd.Series, d: pd.Timestamp):
    """Last available adjusted close on/at-or-before d (carry across suspensions)."""
    pos = series.index.searchsorted(d, side="right") - 1
    if pos < 0:
        return None
    v = series.iloc[pos]
    return float(v) if np.isfinite(v) else None


def _vol_at(panel, sym, d, window):
    h = panel.history(sym, d)
    if len(h) < window + 1:
        return None
    rets = h["close"].pct_change().dropna().iloc[-window:]
    v = rets.std(ddof=0)
    return float(v) if np.isfinite(v) else None


def _metrics(period_returns: list[float]) -> dict:
    r = np.array([x for x in period_returns if x is not None], dtype=float)
    if len(r) == 0:
        return {}
    curve = np.cumprod(1.0 + r)
    total = float(curve[-1] - 1.0)
    n_years = len(r) / PERIODS_PER_YEAR
    cagr = float(curve[-1] ** (1.0 / n_years) - 1.0) if n_years > 0 else None
    ann_vol = float(r.std(ddof=1) * np.sqrt(PERIODS_PER_YEAR)) if len(r) > 1 else None
    sharpe = float((r.mean() * PERIODS_PER_YEAR) / ann_vol) if ann_vol else None
    peak = np.maximum.accumulate(curve)
    max_dd = float(((curve - peak) / peak).min())
    return {
        "total_return": round(total, 4),
        "cagr": round(cagr, 4) if cagr is not None else None,
        "ann_vol": round(ann_vol, 4) if ann_vol is not None else None,
        "sharpe": round(sharpe, 3) if sharpe is not None else None,
        "max_drawdown": round(max_dd, 4),
        "n_periods": len(r),
    }


def _run_basket(panel, adj, dates, eligible_by_date, window, basket_n):
    """One backtest: monthly low-vol bottom-N basket vs equal-weight benchmark."""
    basket_gross, basket_net, bench_gross = [], [], []
    turnovers = []
    prev_weights: dict[str, float] = {}
    for i in range(len(dates) - 1):
        d0, d1 = pd.Timestamp(dates[i]), pd.Timestamp(dates[i + 1])
        elig = eligible_by_date.get(d0) or set()
        # rankable names: eligible, enough history, valid adj prices at both ends
        ranked = []
        period_ret: dict[str, float] = {}
        for sym in elig:
            if sym not in adj:
                continue
            p0 = _price_at(adj[sym], d0)
            p1 = _price_at(adj[sym], d1)
            v = _vol_at(panel, sym, d0, window)
            if p0 and p1 and v is not None:
                ranked.append((v, sym))
                period_ret[sym] = p1 / p0 - 1.0
        if len(ranked) < basket_n + 5:
            continue
        ranked.sort(key=lambda t: (t[0], t[1]))
        basket = [s for _, s in ranked[:basket_n]]
        all_names = [s for _, s in ranked]
        w_new = {s: 1.0 / len(basket) for s in basket}

        # gross returns
        b_g = float(np.mean([period_ret[s] for s in basket]))
        m_g = float(np.mean([period_ret[s] for s in all_names]))

        # turnover vs drifted previous weights -> cost
        if prev_weights:
            drift = {s: prev_weights.get(s, 0.0) * (1.0 + period_ret.get(s, 0.0)) for s in set(prev_weights)}
            tot = sum(drift.values()) or 1.0
            drift = {s: w / tot for s, w in drift.items()}
        else:
            drift = {}
        names = set(w_new) | set(drift)
        buys = sum(max(w_new.get(s, 0.0) - drift.get(s, 0.0), 0.0) for s in names)
        sells = sum(max(drift.get(s, 0.0) - w_new.get(s, 0.0), 0.0) for s in names)
        cost = buys * BUY_RATE + sells * SELL_RATE
        one_way_turnover = 0.5 * sum(abs(w_new.get(s, 0.0) - drift.get(s, 0.0)) for s in names)

        basket_gross.append(b_g)
        basket_net.append(b_g - cost)
        bench_gross.append(m_g)
        turnovers.append(one_way_turnover)
        prev_weights = w_new

    return {
        "basket_n": basket_n,
        "gross": _metrics(basket_gross),
        "net": _metrics(basket_net),
        "benchmark_equal_weight_gross": _metrics(bench_gross),
        "avg_annual_turnover": round(float(np.mean(turnovers) * PERIODS_PER_YEAR), 3) if turnovers else None,
        "net_excess_cagr_vs_benchmark": (
            round(_metrics(basket_net).get("cagr", 0) - _metrics(bench_gross).get("cagr", 0), 4)
            if basket_net and bench_gross else None
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="000300.SH")
    ap.add_argument("--start", default="20180101")
    ap.add_argument("--end", default="20240101")
    ap.add_argument("--window", type=int, default=60)
    ap.add_argument("--baskets", default="20,30,50", help="comma list of basket sizes N")
    ap.add_argument("--sample-freq", type=int, default=90)
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    from src.data.factor_panel import (
        build_eligible_by_date,
        build_panel,
        build_survivorship_free_universe,
    )
    from src.data.providers.tushare_provider import TushareProvider

    cache_dir = PROJECT_ROOT / "data/_factor_cache"
    provider = TushareProvider()
    symbols = build_survivorship_free_universe(
        provider, args.index, args.start, args.end, sample_freq_days=args.sample_freq
    )
    print(f"[{args.index}] union: {len(symbols)} names", file=sys.stderr)
    panel = build_panel(symbols, args.start, args.end, provider, cache_dir=cache_dir)
    print(f"[{args.index}] panel usable: {len(panel.symbols)}", file=sys.stderr)

    base_dates = monthly_rebalance_dates(panel.trading_dates)
    ref = panel.symbols[0]
    dates = [d for d in base_dates if len(panel.history(ref, d)) >= 252]

    eligible_by_date: dict = {}
    chunk = 80
    for i in range(0, len(dates), chunk):
        provider.reset_throttle()
        eligible_by_date.update(build_eligible_by_date(provider, args.index, dates[i : i + chunk]))
        if i + chunk < len(dates):
            time.sleep(62)

    adj = _adj_close_map(panel.symbols, panel, provider, cache_dir)

    baskets = [int(b) for b in args.baskets.split(",") if b.strip()]
    results = [_run_basket(panel, adj, dates, eligible_by_date, args.window, n) for n in baskets]

    out = {
        "index": args.index,
        "span": f"{args.start}..{args.end}",
        "vol_window": args.window,
        "n_rebalance_periods": len(dates) - 1,
        "cost_rates": {"buy": BUY_RATE, "sell": SELL_RATE, "note": "commission+slippage+transfer (+stamp on sell)"},
        "prices": "TOTAL-RETURN (close * adj_factor); ranking vol on unadjusted close",
        "benchmark": "equal-weight of same eligible universe (gross)",
        "results": results,
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
