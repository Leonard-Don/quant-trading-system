"""Out-of-distribution stress tests for the confirmed low_volatility@20 signal.

Discovery + the pre-registered confirmation both used 2018-2024 Tushare,
close-to-close vol. This probes axes the signal has NOT seen:
  * TEMPORAL forward — a fresh, genuinely-unseen window (e.g. 2024-2026) via a
    SEPARATE cache dir (the per-symbol cache is not span-aware, so a forward run
    MUST use --cache-dir or it would reload stale 2018-2024 prices).
  * ESTIMATOR — Parkinson high/low range vol instead of close-to-close std, to
    check the edge isn't an artifact of one vol definition.

Reuses the production harness (survivorship-free + suspension-filtered, point-in-
time). Prints JSON: yearly IC, OOS IC, ICIR, gate, and (if --forward-from) the
mean IC over the genuinely-unseen sub-window.

Usage:
  # forward / unseen years (fresh cache -> fetches 2023-2026):
  .venv/bin/python scripts/research/lowvol_ood.py --index 000300.SH --start 20230701 \
      --end 20260601 --cache-dir data/_factor_cache_ood --forward-from 2024-01-01
  # estimator robustness on the cached in-sample window:
  .venv/bin/python scripts/research/lowvol_ood.py --index 000300.SH --estimator parkinson
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


def monthly_rebalance_dates(trading_dates) -> list:
    s = pd.Series(1, index=pd.DatetimeIndex(trading_dates))
    return [pd.Timestamp(g.index[0]) for _, g in s.groupby([s.index.year, s.index.month])]


class ParkinsonVolFactor:
    """Low-vol ranked by Parkinson high/low range vol (different estimator).
    Parkinson sigma^2 = mean( ln(high/low)^2 ) / (4 ln 2). Value = -sigma so calmer
    = higher; direction +1, exactly like LowVolatilityFactor."""

    name = "low_volatility_parkinson"
    direction = 1

    def __init__(self, window: int = 60):
        self.window = window

    def compute(self, panel, as_of) -> pd.Series:
        out = {}
        k = 1.0 / (4.0 * np.log(2.0))
        for sym in panel.symbols:
            h = panel.history(sym, as_of)
            if len(h) < self.window + 1 or "high" not in h or "low" not in h:
                continue
            tail = h.iloc[-self.window :]
            hl = np.log(tail["high"].astype(float) / tail["low"].astype(float))
            hl = hl.replace([np.inf, -np.inf], np.nan).dropna()
            if len(hl) < self.window // 2:
                continue
            var = k * float((hl**2).mean())
            if np.isfinite(var) and var >= 0:
                out[sym] = -float(np.sqrt(var))
        return pd.Series(out, dtype=float)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="000300.SH")
    ap.add_argument("--start", default="20180101")
    ap.add_argument("--end", default="20240101")
    ap.add_argument("--window", type=int, default=60)
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--train-frac", type=float, default=0.7)
    ap.add_argument("--sample-freq", type=int, default=90)
    ap.add_argument("--estimator", choices=["close", "parkinson"], default="close")
    ap.add_argument("--cache-dir", default="data/_factor_cache")
    ap.add_argument("--forward-from", default=None, help="report mean IC over rebalance dates >= this (e.g. 2024-01-01)")
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    from src.analytics.factors.evaluation import (
        evaluate_factor,
        factor_ic_series,
        passes_ic_gate,
    )
    from src.analytics.factors.price import LowVolatilityFactor
    from src.data.factor_panel import (
        FactorPanel,
        build_eligible_by_date,
        build_survivorship_free_universe,
    )
    from src.data.providers.tushare_provider import TushareProvider

    cache_dir = PROJECT_ROOT / args.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    provider = TushareProvider()
    symbols = build_survivorship_free_universe(
        provider, args.index, args.start, args.end, sample_freq_days=args.sample_freq
    )
    print(f"[{args.index}] union: {len(symbols)} names; cache={cache_dir.name}", file=sys.stderr)
    # PRICE-ONLY panel: low-vol needs only prices, and this sidesteps build_panel's
    # fundamentals path (which crashes on a None ann_date in fresh forward data).
    prices = {}
    for sym in symbols:
        p = cache_dir / f"{sym}_px.pkl"
        if p.exists():
            px = pd.read_pickle(p)
        else:
            px = provider.get_historical_data(sym, args.start, args.end)
            if px is not None and not px.empty:
                px.to_pickle(p)
        if px is None or getattr(px, "empty", True):
            continue
        px = px.copy()
        px.index = pd.DatetimeIndex(pd.to_datetime(px.index, errors="coerce"))
        px = px[px.index.notna()].sort_index()
        if not px.empty:
            prices[sym] = px
    panel = FactorPanel(prices=prices)
    print(f"[{args.index}] panel usable: {len(panel.symbols)}", file=sys.stderr)

    base_dates = monthly_rebalance_dates(panel.trading_dates)
    ref = panel.symbols[0]
    base_dates = [d for d in base_dates if len(panel.history(ref, d)) >= 252]
    dates = base_dates[:-1] if base_dates else []

    eligible_by_date: dict = {}
    chunk = 80
    for i in range(0, len(dates), chunk):
        provider.reset_throttle()
        eligible_by_date.update(build_eligible_by_date(provider, args.index, dates[i : i + chunk]))
        if i + chunk < len(dates):
            time.sleep(62)

    factor = (
        ParkinsonVolFactor(args.window)
        if args.estimator == "parkinson"
        else LowVolatilityFactor(args.window)
    )
    rep = evaluate_factor(
        factor, panel, dates, args.horizon, args.train_frac, eligible_by_date=eligible_by_date
    )
    out = {
        "index": args.index,
        "span": f"{args.start}..{args.end}",
        "estimator": args.estimator,
        "vol_window": args.window,
        "horizon": args.horizon,
        "n_rebalance_dates": rep["n_dates"],
        "full_ic": round(rep["mean_ic"], 4) if np.isfinite(rep["mean_ic"]) else None,
        "oos_ic": round(rep["oos_mean_ic"], 4) if np.isfinite(rep["oos_mean_ic"]) else None,
        "icir": round(rep["icir"], 3) if np.isfinite(rep["icir"]) else None,
        "sign_stable": rep["sign_stable"],
        "yearly_ic": {str(k): round(float(v), 4) for k, v in rep["yearly_ic"].items()},
        "passes_gate": bool(rep["passes"]),
    }
    if args.forward_from:
        ser = factor_ic_series(factor, panel, dates, args.horizon, eligible_by_date=eligible_by_date)
        fwd = ser[ser.index >= pd.Timestamp(args.forward_from)]
        out["forward_window"] = {
            "from": args.forward_from,
            "n_dates": len(fwd),
            "mean_ic": round(float(fwd.mean()), 4) if len(fwd) else None,
            "icir": round(float(fwd.mean() / fwd.std(ddof=0)), 3) if len(fwd) and fwd.std(ddof=0) else None,
            "passes_rough": bool(len(fwd) and fwd.mean() >= 0.03),
        }
    _ = passes_ic_gate
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
