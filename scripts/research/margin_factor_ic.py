"""Point-in-time IC probe for a margin-financing (融资) factor.

RESEARCH probe — does the trailing change in margin financing balance (``rzye``,
融资余额) predict forward returns? This measures *test* IC only; it is NOT wired
into the scorer. The sign of the relationship is genuinely unknown a priori:

* a *financing surge* could be **bullish** (leveraged demand front-running a move), or
* it could be **bearish** (overheating / crowded longs that mean-revert).

We start with ``direction = +1`` and report the IC sign honestly. A consistently
*negative* IC means financing surges precede *under*-performance.

Factor definition
-----------------
``margin_buildup`` = trailing ~20-trading-day relative change in financing balance
at each rebalance date ``D``::

    margin_buildup(sym, D) = (rzye[sym, D] - rzye[sym, D-20]) / rzye[sym, D-20]

Point-in-time: only margin snapshots with ``trade_date <= D`` are ever read, so the
factor at ``D`` cannot see the future. ``D`` and ``D-20`` are the panel's own trading
days at/at-or-before the rebalance date and ~20 trading days earlier.

Data
----
Tushare ``pro.margin_detail(trade_date=YYYYMMDD)`` returns per-stock margin for that
date (cols incl ``ts_code``, ``rzye``). One call per trade_date covers ALL stocks —
we fetch by date (NOT per symbol) and cache each snapshot to a SEPARATE pickle dir
``data/_factor_cache/margin/`` so we never touch the shared price cache.

It reuses the existing IC machinery (``evaluate_factor``) and panel/universe plumbing;
it does NOT reimplement IC.

Run::

    .venv/bin/python scripts/research/margin_factor_ic.py
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Price cache (shared, already warm) and a SEPARATE margin snapshot cache so this
# probe never mutates the price pickles.
PRICE_CACHE_DIR = pathlib.Path("/Users/leonardodon/quant-trading-system/data/_factor_cache")
MARGIN_CACHE_DIR = PRICE_CACHE_DIR / "margin"

# Trailing window for the relative change, in *trading* days. ~20 ≈ one month.
DEFAULT_LOOKBACK = 20


def _yyyymmdd(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y%m%d")


def fetch_margin_snapshot(provider, trade_date, cache_dir=MARGIN_CACHE_DIR) -> pd.Series:
    """Per-date financing balance (``rzye``) indexed by ``ts_code``.

    Fetched with ONE ``margin_detail(trade_date=...)`` call covering all stocks and
    cached to ``cache_dir/{YYYYMMDD}.pkl``. A trade_date that has no margin data
    (e.g. a non-trading day) is cached as an empty Series so we don't re-hit the API.
    """
    cache_dir = pathlib.Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _yyyymmdd(trade_date)
    path = cache_dir / f"{key}.pkl"
    if path.exists():
        return pd.read_pickle(path)

    pro = provider._get_pro_client()
    df = pro.margin_detail(trade_date=key)
    if df is None or df.empty or "ts_code" not in df.columns or "rzye" not in df.columns:
        s = pd.Series(dtype=float)
    else:
        s = (
            df.dropna(subset=["ts_code"])
            .assign(rzye=lambda d: pd.to_numeric(d["rzye"], errors="coerce"))
            .set_index("ts_code")["rzye"]
            .astype(float)
        )
        s = s[~s.index.duplicated(keep="last")]
    s.to_pickle(path)
    return s


class MarginBuildupFactor:
    """Trailing relative change in margin financing balance (融资余额, ``rzye``).

    ``compute(panel, as_of)`` returns one value per symbol: the relative change in
    ``rzye`` over the last ``lookback`` *trading* days, using only margin snapshots
    with ``trade_date <= as_of`` (point-in-time).
    """

    name = "margin_buildup"
    direction = 1  # start at +1; report the realized sign honestly.

    def __init__(self, provider=None, lookback: int = DEFAULT_LOOKBACK, cache_dir=MARGIN_CACHE_DIR):
        self.provider = provider
        self.lookback = int(lookback)
        self.cache_dir = pathlib.Path(cache_dir)

    def _snapshot(self, trade_date) -> pd.Series:
        return fetch_margin_snapshot(self.provider, trade_date, self.cache_dir)

    def compute(self, panel, as_of) -> pd.Series:
        as_of = pd.Timestamp(as_of)

        # Use the panel's union trading calendar to pick D (last trading day <= as_of)
        # and the trading day ~lookback bars earlier. Both are <= as_of, so this is
        # strictly point-in-time.
        cal = panel.trading_dates
        cal = cal[cal <= as_of]
        if len(cal) <= self.lookback:
            return pd.Series(dtype=float)
        d_now = cal[-1]
        d_prev = cal[-1 - self.lookback]

        cur = self._snapshot(d_now)
        prev = self._snapshot(d_prev)
        if cur.empty or prev.empty:
            return pd.Series(dtype=float)

        out: dict[str, float] = {}
        for sym in panel.symbols:
            c = cur.get(sym, np.nan)
            p = prev.get(sym, np.nan)
            if np.isfinite(c) and np.isfinite(p) and p > 0:
                out[sym] = float(c / p - 1.0)
        return pd.Series(out, dtype=float)


def _fmt(x) -> str:
    return f"{x:.4f}" if isinstance(x, (int, float)) and x == x else "-"


def main() -> None:
    from dotenv import load_dotenv

    # The Tushare token lives in the repo-root .env. Prefer this checkout's .env;
    # fall back to the canonical repo root (e.g. when run from a git worktree).
    if not load_dotenv(PROJECT_ROOT / ".env"):
        load_dotenv("/Users/leonardodon/quant-trading-system/.env")

    from scripts.run_factor_scorecard import monthly_rebalance_dates
    from src.analytics.factors.evaluation import evaluate_factor
    from src.data.factor_panel import build_panel
    from src.data.providers.tushare_provider import TushareProvider

    provider = TushareProvider()
    csi300 = provider.get_index_constituents("000300.SH")
    print(f"CSI300 constituents: {len(csi300)} symbols; building price panel (cached)...")

    panel = build_panel(
        csi300,
        "20190101",
        "20240101",
        provider,
        cache_dir=PRICE_CACHE_DIR,
    )
    usable = len(panel.symbols)
    print(f"panel built: {usable} symbols usable (of {len(csi300)} requested)")

    factor = MarginBuildupFactor(provider=provider)

    # Rebalance dates need >=252 bars of history; drop the final date so a forward
    # bar exists for the longest horizon.
    base_dates = monthly_rebalance_dates(panel.trading_dates)
    ref_sym = panel.symbols[0]
    base_dates = [d for d in base_dates if len(panel.history(ref_sym, d)) >= 252]
    dates = base_dates[:-1] if base_dates else []
    print(f"rebalance dates: {len(dates)} (first {dates[0].date()} … last {dates[-1].date()})")

    # Warm the margin cache once over every D and D-lookback used by these dates.
    print("warming margin snapshot cache (one margin_detail call per trade_date)...")
    cal = panel.trading_dates
    needed: set = set()
    for d in dates:
        sub = cal[cal <= d]
        if len(sub) > factor.lookback:
            needed.add(sub[-1])
            needed.add(sub[-1 - factor.lookback])
    for i, td in enumerate(sorted(needed), 1):
        fetch_margin_snapshot(provider, td)
        if i % 10 == 0 or i == len(needed):
            print(f"  margin snapshots cached: {i}/{len(needed)}")

    horizons = [5, 20, 60]
    print(f"\nfactor: {factor.name} (direction={factor.direction:+d}, lookback={factor.lookback}d)")
    print(
        f"{'horizon':>8} | {'n':>4} | {'mean IC':>9} | {'OOS IC':>9} | "
        f"{'ICIR':>7} | {'stable':>6} | verdict"
    )
    print("-" * 70)
    results = {}
    for h in horizons:
        rep = evaluate_factor(factor, panel, dates, h)
        results[h] = rep
        print(
            f"{h:>8} | {rep['n_dates']:>4} | {_fmt(rep['mean_ic']):>9} | "
            f"{_fmt(rep['oos_mean_ic']):>9} | {_fmt(rep['icir']):>7} | "
            f"{'✓' if rep.get('sign_stable') else '✗':>6} | "
            f"{'PASS' if rep.get('passes') else 'FAIL'}"
        )

    # Honest verdict on sign/predictiveness.
    print("\n--- verdict ---")
    for h in horizons:
        ic = results[h]["mean_ic"]
        if isinstance(ic, (int, float)) and ic == ic:
            sign = "bullish (+)" if ic > 0 else "bearish (-)"
            print(f"h={h:>3}: mean IC {ic:+.4f} -> financing buildup is {sign} for fwd returns")
    any_pass = any(results[h].get("passes") for h in horizons)
    print(f"\noverall: {'PASS at >=1 horizon' if any_pass else 'FAIL at all horizons'}")


if __name__ == "__main__":
    main()
