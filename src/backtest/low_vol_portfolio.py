"""Pure, network-free low-volatility long-only portfolio backtest.

The testable heart of the screen→strategy step: it turns the VALIDATED
``low_volatility`` signal into an implementable monthly-rebalanced bottom-N
basket and computes its net-of-cost performance against an equal-weight
benchmark of the same eligible universe.

This module does NO I/O — callers supply the already-built panel, the
adjusted-close (total-return) series per symbol, the rebalance dates and the
per-date eligible sets. The logic (vol ranking, period returns on adjusted
prices, drift-aware turnover cost, metrics) is lifted verbatim from
``scripts/research/lowvol_portfolio_backtest.py`` so production matches research.

Honesty invariants baked in (a low-vol backtest lies without these):
  * P&L on TOTAL-RETURN prices (``close × adj_factor``); ranking vol on the
    panel's UNADJUSTED close, exactly as the validated factor defines it.
  * Point-in-time: vol from history <= D; period return D -> next rebalance.
  * Realistic A-share costs charged on turnover each rebalance.
  * Benchmark = equal-weight of the same eligible (ranked) universe.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# Realistic A-share friction rates (match the #144 cost profile + a discount broker).
COMMISSION = 0.00025   # 0.025% both sides
SLIPPAGE = 0.0005      # 0.05% both sides (liquid large/mid caps)
TRANSFER = 0.00001     # 过户费 0.001% both sides
STAMP = 0.0005         # 印花税 0.05% SELL only
BUY_RATE = COMMISSION + SLIPPAGE + TRANSFER            # 0.076%
SELL_RATE = COMMISSION + SLIPPAGE + TRANSFER + STAMP   # 0.126%
TRADING_DAYS = 252.0
PERIODS_PER_YEAR = 12.0

DEFAULT_COST_RATES = {"buy": BUY_RATE, "sell": SELL_RATE}


def _price_at(series: pd.Series, d: pd.Timestamp) -> Optional[float]:
    """Last available adjusted close on/at-or-before ``d`` (carry across suspensions)."""
    pos = series.index.searchsorted(d, side="right") - 1
    if pos < 0:
        return None
    v = series.iloc[pos]
    return float(v) if np.isfinite(v) else None


def _vol_at(panel, sym: str, d: pd.Timestamp, window: int) -> Optional[float]:
    """Trailing realized vol of UNADJUSTED close over the last ``window`` returns."""
    h = panel.history(sym, d)
    if len(h) < window + 1:
        return None
    rets = h["close"].pct_change().dropna().iloc[-window:]
    v = rets.std(ddof=0)
    return float(v) if np.isfinite(v) else None


def _metrics(period_returns: list) -> dict:
    """CAGR / ann-vol / Sharpe / max-drawdown from a list of per-period returns."""
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


def run_low_vol_portfolio_backtest(
    panel,
    adj_close_by_symbol: dict,
    rebalance_dates,
    eligible_by_date: dict,
    *,
    window: int = 60,
    basket_n: int = 30,
    cost_rates: Optional[dict] = None,
    select_high_vol: bool = False,
) -> dict:
    """Backtest a monthly long-only bottom-N lowest-vol basket vs equal-weight.

    Args:
        panel: a ``FactorPanel`` (provides ``history`` for vol ranking on the
            UNADJUSTED close).
        adj_close_by_symbol: ``{symbol -> pd.Series}`` of TOTAL-RETURN adjusted
            close indexed by trade date (used for P&L).
        rebalance_dates: ordered iterable of rebalance ``Timestamp``s. The
            backtest runs over consecutive pairs (D -> next D).
        eligible_by_date: ``{Timestamp -> set[str]}`` survivorship-free,
            suspension-filtered eligible names per rebalance date.
        window: realized-vol lookback in trading days (matches the factor).
        basket_n: number of names in the long-only basket.
        cost_rates: ``{"buy": rate, "sell": rate}``; defaults to the A-share
            friction profile (commission + slippage + transfer (+ stamp on sell)).
        select_high_vol: if True, select the HIGHEST-vol names instead (for
            tests / the inverse leg) — production always uses the default.

    Returns:
        ``{
            "equity_curve": [{date, basket_gross, basket_net, benchmark}, ...],
            "metrics": {"gross": {...}, "net": {...}, "benchmark": {...}},
            "avg_annual_turnover": float | None,
            "n_periods": int,
        }``  Equity-curve values are cumulative growth-of-1 series.
    """
    rates = cost_rates or DEFAULT_COST_RATES
    buy_rate = float(rates.get("buy", BUY_RATE))
    sell_rate = float(rates.get("sell", SELL_RATE))
    dates = [pd.Timestamp(d) for d in rebalance_dates]

    basket_gross: list[float] = []
    basket_net: list[float] = []
    bench_gross: list[float] = []
    period_dates: list[pd.Timestamp] = []
    turnovers: list[float] = []
    prev_weights: dict[str, float] = {}

    for i in range(len(dates) - 1):
        d0, d1 = dates[i], dates[i + 1]
        elig = eligible_by_date.get(d0) or set()
        ranked: list[tuple[float, str]] = []
        period_ret: dict[str, float] = {}
        for sym in elig:
            if sym not in adj_close_by_symbol:
                continue
            p0 = _price_at(adj_close_by_symbol[sym], d0)
            p1 = _price_at(adj_close_by_symbol[sym], d1)
            v = _vol_at(panel, sym, d0, window)
            if p0 and p1 and v is not None:
                ranked.append((v, sym))
                period_ret[sym] = p1 / p0 - 1.0
        if len(ranked) < basket_n + 5:
            continue
        # ascending vol = calmest first; tie-break by symbol for determinism.
        ranked.sort(key=lambda t: (t[0], t[1]), reverse=select_high_vol)
        basket = [s for _, s in ranked[:basket_n]]
        all_names = [s for _, s in ranked]
        w_new = {s: 1.0 / len(basket) for s in basket}

        b_g = float(np.mean([period_ret[s] for s in basket]))
        m_g = float(np.mean([period_ret[s] for s in all_names]))

        # turnover vs drifted previous weights -> cost
        if prev_weights:
            drift = {
                s: prev_weights.get(s, 0.0) * (1.0 + period_ret.get(s, 0.0))
                for s in set(prev_weights)
            }
            tot = sum(drift.values()) or 1.0
            drift = {s: w / tot for s, w in drift.items()}
        else:
            drift = {}
        names = set(w_new) | set(drift)
        buys = sum(max(w_new.get(s, 0.0) - drift.get(s, 0.0), 0.0) for s in names)
        sells = sum(max(drift.get(s, 0.0) - w_new.get(s, 0.0), 0.0) for s in names)
        cost = buys * buy_rate + sells * sell_rate
        one_way_turnover = 0.5 * sum(abs(w_new.get(s, 0.0) - drift.get(s, 0.0)) for s in names)

        basket_gross.append(b_g)
        basket_net.append(b_g - cost)
        bench_gross.append(m_g)
        turnovers.append(one_way_turnover)
        period_dates.append(d1)
        prev_weights = w_new

    # Cumulative growth-of-1 curves, aligned on the period END dates.
    equity_curve = []
    cg = np.cumprod(1.0 + np.array(basket_gross, dtype=float)) if basket_gross else np.array([])
    cn = np.cumprod(1.0 + np.array(basket_net, dtype=float)) if basket_net else np.array([])
    cb = np.cumprod(1.0 + np.array(bench_gross, dtype=float)) if bench_gross else np.array([])
    for idx, d in enumerate(period_dates):
        equity_curve.append(
            {
                "date": pd.Timestamp(d).strftime("%Y-%m-%d"),
                "basket_gross": round(float(cg[idx]), 6),
                "basket_net": round(float(cn[idx]), 6),
                "benchmark": round(float(cb[idx]), 6),
            }
        )

    return {
        "equity_curve": equity_curve,
        "metrics": {
            "gross": _metrics(basket_gross),
            "net": _metrics(basket_net),
            "benchmark": _metrics(bench_gross),
        },
        "avg_annual_turnover": (
            round(float(np.mean(turnovers) * PERIODS_PER_YEAR), 3) if turnovers else None
        ),
        "n_periods": len(period_dates),
    }
