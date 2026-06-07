"""Point-in-time IC probe for a NORTHBOUND-FLOW factor (Stock Connect).

Research question
-----------------
Does foreign "smart money" (北向资金 / Stock Connect) ACCUMULATION predict
forward returns on A-shares?

Factor
------
``northbound_accumulation`` = change in northbound holding ``ratio`` (北向持股
占比, %) over the trailing ~20 trading days at each rebalance date::

    value(symbol, D) = ratio[symbol, D] - ratio[symbol, D-20]

``direction = +1`` (more accumulation -> bullish). Strictly point-in-time: at
rebalance date ``D`` only ``hk_hold`` cross-sections with ``trade_date <= D``
are used.

This is a RESEARCH probe (measure IC), NOT an integration into the scorer. It
reuses the existing factor-evaluation machinery (rank IC / ICIR / OOS /
yearly-stability / pass gate) verbatim; only the cross-section builder is new.

Northbound cross-sections are fetched EFFICIENTLY by ``trade_date`` (one
``hk_hold`` call per needed date -- the rebalance dates and their -20d points --
NOT per symbol) and cached to ``data/_factor_cache/northbound/<YYYYMMDD>.pkl``
so reruns resume and they don't collide with other probes' caches.
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

LOOKBACK = 20  # trailing trading days for the ratio delta
HORIZONS = (5, 20, 60)
# Prices are cached in the primary checkout's data dir from a prior run; the
# northbound cross-sections live alongside in a separate subdir so probes don't
# collide. Both are gitignored under data/.
FACTOR_CACHE_DIR = PROJECT_ROOT / "data/_factor_cache"
NB_CACHE_DIR = FACTOR_CACHE_DIR / "northbound"


# ---------------------------------------------------------------------------
# Pure, offline-testable logic: the trailing-Delta-ratio cross-section builder.
# ---------------------------------------------------------------------------
def trailing_ratio_delta(
    cross_sections: dict[pd.Timestamp, pd.Series],
    as_of: pd.Timestamp,
    lookback: int = LOOKBACK,
) -> pd.Series:
    """Compute ``ratio[D] - ratio[D-lookback]`` per symbol, point-in-time.

    Parameters
    ----------
    cross_sections
        Mapping ``trade_date -> Series[symbol -> northbound ratio (%)]``. May
        contain dates AFTER ``as_of``; those MUST be ignored (point-in-time).
    as_of
        Rebalance date ``D``. The most recent available cross-section with
        ``trade_date <= as_of`` is used as the "current" snapshot, and the
        ``lookback``-th visible cross-section before it as the baseline.
    lookback
        Number of trailing northbound observations between the current snapshot
        and the baseline snapshot (default 20).

    Returns
    -------
    pd.Series
        ``symbol -> ratio change``. Empty if there is insufficient point-in-time
        history. Only symbols present in BOTH snapshots are returned.
    """
    as_of = pd.Timestamp(as_of)
    visible = sorted(d for d in cross_sections if pd.Timestamp(d) <= as_of)
    if len(visible) < lookback + 1:
        return pd.Series(dtype=float)
    cur_date = visible[-1]
    base_date = visible[-(lookback + 1)]
    cur = cross_sections[cur_date].astype(float)
    base = cross_sections[base_date].astype(float)
    common = cur.index.intersection(base.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    delta = cur.loc[common] - base.loc[common]
    return delta.dropna().astype(float)


class NorthboundAccumulationFactor:
    """Factor adapter: reads cached northbound cross-sections and emits the
    trailing-Delta-ratio cross-section at ``as_of``. Matches the duck-typed
    factor interface (``name``, ``direction``, ``compute(panel, as_of)``)."""

    name = "northbound_accumulation"
    direction = 1

    def __init__(self, cross_sections: dict[pd.Timestamp, pd.Series], lookback: int = LOOKBACK):
        # date -> Series[symbol -> ratio]; pre-fetched once for the whole run.
        self.cross_sections = {pd.Timestamp(d): s for d, s in cross_sections.items()}
        self.lookback = lookback

    def compute(self, panel, as_of) -> pd.Series:  # panel kept for interface parity
        return trailing_ratio_delta(self.cross_sections, pd.Timestamp(as_of), self.lookback)


# ---------------------------------------------------------------------------
# Northbound fetching + caching (one hk_hold call per trade_date, pickled).
# ---------------------------------------------------------------------------
def _nb_cache_path(trade_date: str) -> pathlib.Path:
    return NB_CACHE_DIR / f"{trade_date}.pkl"


def fetch_northbound_cross_section(provider, trade_date: str) -> pd.Series:
    """Northbound holding ``ratio`` for ``trade_date`` as ``Series[ts_code->%]``.

    Resumable pickle cache under ``data/_factor_cache/northbound/``. One
    ``hk_hold`` API call per date. Returns an empty Series when the endpoint has
    no data for that date (e.g. a non-trading day passed by mistake).
    """
    NB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _nb_cache_path(trade_date)
    if path.exists():
        return pd.read_pickle(path)
    pro = provider._get_pro_client()
    df = pro.hk_hold(trade_date=trade_date)
    if df is None or getattr(df, "empty", True) or "ratio" not in df.columns:
        ser = pd.Series(dtype=float)
    else:
        df = df[df["exchange"].isin(["SH", "SZ"])] if "exchange" in df.columns else df
        ser = (
            df.dropna(subset=["ts_code", "ratio"])
            .groupby("ts_code")["ratio"]
            .last()
            .astype(float)
        )
    ser.to_pickle(path)
    return ser


def northbound_dates_for_rebalances(
    rebalance_dates, trading_dates, lookback: int = LOOKBACK
) -> list[str]:
    """The set of ``YYYYMMDD`` dates whose northbound cross-section is needed.

    For each rebalance date ``D`` we need the trading day at ``D`` and the one
    ``lookback`` trading days earlier (the delta endpoints). Trading days come
    from the price panel so northbound snapshots align to actual market dates.
    Returns a sorted, de-duplicated list of compact date strings.
    """
    td = pd.DatetimeIndex(trading_dates).sort_values()
    needed: set[str] = set()
    for d in rebalance_dates:
        d = pd.Timestamp(d)
        pos = td.searchsorted(d, side="right") - 1  # last trading day <= D
        if pos < lookback:
            continue
        for p in (pos, pos - lookback):
            needed.add(td[p].strftime("%Y%m%d"))
    return sorted(needed)


def _load_token_env() -> None:
    """Load the Tushare token from the nearest ``.env``.

    When running from an isolated git worktree the local PROJECT_ROOT has no
    ``.env`` (it lives in the primary checkout), so walk up the directory tree
    until one is found. No-op if none exists (token may already be exported).
    """
    from dotenv import load_dotenv

    for parent in [PROJECT_ROOT, *PROJECT_ROOT.parents]:
        env = parent / ".env"
        if env.exists():
            load_dotenv(env)
            return


def main() -> None:
    _load_token_env()

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
        cache_dir=str(FACTOR_CACHE_DIR),
    )
    usable = len(panel.symbols)
    print(f"panel built: {usable} symbols usable (of {len(csi300)} requested)")
    if usable < 100:
        print(f"WARNING: only {usable} symbols usable (<100); IC estimates will be noisy")

    trading_dates = panel.trading_dates
    base_dates = monthly_rebalance_dates(trading_dates)
    # Need >= LOOKBACK+1 trading days of history before the first usable date.
    ref_sym = panel.symbols[0]
    base_dates = [d for d in base_dates if len(panel.history(ref_sym, d)) >= LOOKBACK + 1]
    # Drop the last date so a forward bar exists for the longest horizon.
    dates = base_dates[:-1] if base_dates else []
    print(f"rebalance dates: {len(dates)} (monthly, point-in-time)")

    # Fetch every northbound cross-section we need: one hk_hold call per date.
    nb_dates = northbound_dates_for_rebalances(dates, trading_dates, LOOKBACK)
    print(f"northbound cross-sections needed: {len(nb_dates)} dates (one hk_hold call each)")
    cross_sections: dict[pd.Timestamp, pd.Series] = {}
    for i, td in enumerate(nb_dates, 1):
        ser = fetch_northbound_cross_section(provider, td)
        cross_sections[pd.Timestamp(td)] = ser
        if i % 10 == 0 or i == len(nb_dates):
            print(f"  fetched {i}/{len(nb_dates)} ({td}: {len(ser)} stocks)")

    factor = NorthboundAccumulationFactor(cross_sections, LOOKBACK)

    print("\nFactor: northbound_accumulation = ratio[D] - ratio[D-20], direction=+1")
    print(f"Universe: CSI300 ({usable} usable) | 2019-01-01 .. 2024-01-01 | OOS = last 30%")
    print(f"{'horizon':>8} | {'mean IC':>9} | {'OOS IC':>9} | {'ICIR':>7} | {'stable':>6} | verdict")
    print("-" * 64)
    results = []
    for h in HORIZONS:
        rep = evaluate_factor(factor, panel, dates, h)
        results.append((h, rep))
        print(
            f"{h:>8} | {rep['mean_ic']:>9.4f} | {rep['oos_mean_ic']:>9.4f} | "
            f"{rep['icir']:>7.3f} | {('YES' if rep.get('sign_stable') else 'no'):>6} | "
            f"{'PASS' if rep.get('passes') else 'FAIL'}"
        )

    any_pass = any(rep.get("passes") for _, rep in results)
    print("-" * 64)
    print(
        "VERDICT: northbound accumulation "
        + ("PREDICTS at >=1 horizon (PASS)" if any_pass else "does NOT predict (FAIL at all horizons)")
    )


if __name__ == "__main__":
    main()
