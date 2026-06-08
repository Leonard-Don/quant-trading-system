"""Pre-registered confirmation of low_volatility@20 on an arbitrary index universe.

Deterministic (no LLM agent) re-run of the FIXED pre-registration in
docs/research/lowvol-confirmation.md. For one index it builds the
survivorship-free + suspension-filtered panel once, then reports:
  - per vol-window {--windows} the gate result @ --horizon (robustness),
  - year-by-year IC regime (positive vs negative years),
  - a temporal hold-out (mean IC over a recent sub-period),
  - (optional --manual) an INDEPENDENT hand-rolled OOS IC that does NOT import
    LowVolatilityFactor / evaluate_factor — a cross-check against harness bugs.

Prints a single JSON blob to stdout. Network only for index_weight/suspend_d
(light) + any not-yet-cached prices; per-name daily prices are pickle-cached
under data/_factor_cache/, so re-runs on a cached universe are fast.

Usage:
  .venv/bin/python scripts/research/lowvol_confirm.py --index 000905.SH --windows 60 --manual
  .venv/bin/python scripts/research/lowvol_confirm.py --index 000300.SH --windows 60,120,250
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def monthly_rebalance_dates(trading_dates) -> list:
    s = pd.Series(1, index=pd.DatetimeIndex(trading_dates))
    return [pd.Timestamp(g.index[0]) for _, g in s.groupby([s.index.year, s.index.month])]


def _manual_oos_ic(panel, dates, eligible_by_date, window: int, horizon: int, train_frac: float):
    """INDEPENDENT recompute — mirrors LowVolatilityFactor(window) but via its own
    code path (no factor/evaluate_factor import): score = -std(pct_change[-window:]),
    cross-sectional Spearman IC vs forward `horizon`-day return, OOS = last 30%."""
    ic_rows = {}
    for d in dates:
        d = pd.Timestamp(d)
        elig = eligible_by_date.get(d) if eligible_by_date is not None else None
        scores, fwd = {}, {}
        for sym in panel.symbols:
            if elig is not None and sym not in elig:
                continue
            df = panel.prices[sym]
            pos = df.index.searchsorted(d)
            if pos >= len(df) or df.index[pos] != d:
                continue
            h = df.iloc[: pos + 1]
            if len(h) < window + 1:
                continue
            rets = h["close"].pct_change().dropna().iloc[-window:]
            vol = rets.std(ddof=0)
            fpos = pos + horizon
            if fpos >= len(df):
                continue
            c0, c1 = df["close"].iloc[pos], df["close"].iloc[fpos]
            if np.isfinite(vol) and c0 and np.isfinite(c0) and np.isfinite(c1):
                scores[sym] = -float(vol)
                fwd[sym] = float(c1 / c0 - 1.0)
        common = sorted(set(scores) & set(fwd))
        if len(common) >= 5:
            rho, _ = spearmanr([scores[s] for s in common], [fwd[s] for s in common])
            if np.isfinite(rho):
                ic_rows[d] = float(rho)
    ic = pd.Series(ic_rows, dtype=float).sort_index()
    if ic.empty:
        return {"oos_ic": None, "icir": None, "n_dates": 0}
    split = int(len(ic) * train_frac)
    oos = ic.iloc[split:]
    icir = float(ic.mean() / ic.std(ddof=0)) if ic.std(ddof=0) else None
    return {
        "oos_ic": float(oos.mean()) if len(oos) else None,
        "full_ic": float(ic.mean()),
        "icir": icir,
        "n_dates": len(ic),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True, help="index code, e.g. 000905.SH (CSI500)")
    ap.add_argument("--start", default="20180101")
    ap.add_argument("--end", default="20240101")
    ap.add_argument("--windows", default="60", help="comma list of vol windows")
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--train-frac", type=float, default=0.7)
    ap.add_argument("--sample-freq", type=int, default=90)
    ap.add_argument("--max-symbols", type=int, default=0)
    ap.add_argument("--temporal-from", default="2023-01-01", help="recent hold-out start")
    ap.add_argument("--manual", action="store_true", help="add independent hand-rolled cross-check")
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
        build_eligible_by_date,
        build_panel,
        build_survivorship_free_universe,
    )
    from src.data.providers.tushare_provider import TushareProvider

    windows = [int(w) for w in args.windows.split(",") if w.strip()]
    provider = TushareProvider()

    symbols = build_survivorship_free_universe(
        provider, args.index, args.start, args.end, sample_freq_days=args.sample_freq
    )
    if args.max_symbols and args.max_symbols > 0:
        symbols = symbols[: args.max_symbols]
    print(f"[{args.index}] survivorship-free union: {len(symbols)} names", file=sys.stderr)

    panel = build_panel(
        symbols, args.start, args.end, provider, cache_dir=PROJECT_ROOT / "data/_factor_cache"
    )
    usable = len(panel.symbols)
    print(f"[{args.index}] panel usable: {usable}", file=sys.stderr)

    base_dates = monthly_rebalance_dates(panel.trading_dates)
    ref_sym = panel.symbols[0]
    base_dates = [d for d in base_dates if len(panel.history(ref_sym, d)) >= 252]
    dates = base_dates[:-1] if base_dates else []

    # eligibility: {as-of constituents on D} - {suspended on D}
    eligible_by_date: dict = {}
    chunk = 80
    for i in range(0, len(dates), chunk):
        provider.reset_throttle()
        eligible_by_date.update(build_eligible_by_date(provider, args.index, dates[i : i + chunk]))
        if i + chunk < len(dates):
            time.sleep(62)
    xs_sizes = [len(v) for v in eligible_by_date.values() if v]
    print(f"[{args.index}] {len(dates)} dates; xs size median={int(np.median(xs_sizes)) if xs_sizes else 0}", file=sys.stderr)

    # per-window gate (robustness)
    variants = []
    base_report = None
    for w in windows:
        rep = evaluate_factor(
            LowVolatilityFactor(w), panel, dates, args.horizon, args.train_frac,
            eligible_by_date=eligible_by_date,
        )
        if base_report is None:
            base_report = rep
        variants.append({
            "vol_window": w,
            "full_ic": rep["mean_ic"],
            "oos_ic": rep["oos_mean_ic"],
            "icir": rep["icir"],
            "sign_stable": rep["sign_stable"],
            "n_dates": rep["n_dates"],
            "passed": bool(rep["passes"]),
        })
    robustness_passed = sum(1 for v in variants if v["passed"])

    # regime: positive vs negative years (from first/default window)
    yearly = base_report["yearly_ic"] if base_report else {}
    pos_years = sum(1 for v in yearly.values() if v > 0)
    neg_years = sum(1 for v in yearly.values() if v < 0)

    # temporal hold-out: mean IC over the recent sub-period (default window)
    ser = factor_ic_series(
        LowVolatilityFactor(windows[0]), panel, dates, args.horizon, eligible_by_date=eligible_by_date
    )
    recent = ser[ser.index >= pd.Timestamp(args.temporal_from)]
    temporal = {
        "holdout": f">= {args.temporal_from}",
        "mean_ic": float(recent.mean()) if len(recent) else None,
        "icir": (float(recent.mean() / recent.std(ddof=0)) if len(recent) and recent.std(ddof=0) else None),
        "n_dates": len(recent),
        "passed": bool(len(recent) and recent.mean() >= 0.03 and (recent.std(ddof=0) == 0 or recent.mean() > 0)),
    }

    out = {
        "index": args.index,
        "span": f"{args.start}..{args.end}",
        "horizon": args.horizon,
        "universe_union_size": len(symbols),
        "panel_usable": usable,
        "n_rebalance_dates": len(dates),
        "xs_size_median": int(np.median(xs_sizes)) if xs_sizes else 0,
        "robustness": variants,
        "robustness_passed_count": robustness_passed,
        "regime": {
            "yearly_ic": {str(k): round(float(v), 4) for k, v in yearly.items()},
            "positive_years": pos_years,
            "negative_years": neg_years,
            "regime_ok": pos_years > neg_years,
        },
        "temporal": temporal,
        "gate_def": "OOS IC >= 0.03 AND ICIR > 0 AND sign_stable",
        "primary_pass_default_window": bool(variants[0]["passed"]) if variants else False,
    }
    if args.manual:
        out["manual_crosscheck"] = _manual_oos_ic(
            panel, dates, eligible_by_date, windows[0], args.horizon, args.train_frac
        )
        # sanity echo of the gate on the manual number
        m = out["manual_crosscheck"]
        out["manual_crosscheck"]["passes_gate_rough"] = bool(
            m.get("oos_ic") is not None and m["oos_ic"] >= 0.03 and (m.get("icir") or 0) > 0
        )
        _ = passes_ic_gate  # keep import meaningful

    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
