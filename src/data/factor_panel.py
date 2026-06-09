from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class FactorPanel:
    prices: dict[str, pd.DataFrame]  # symbol -> OHLCV indexed by DatetimeIndex
    fundamentals: dict[str, pd.DataFrame] = field(default_factory=dict)  # cols incl ann_date,end_date
    moneyflow: dict[str, pd.DataFrame] = field(default_factory=dict)  # indexed by date

    @property
    def symbols(self) -> list[str]:
        return sorted(self.prices.keys())

    @property
    def trading_dates(self) -> pd.DatetimeIndex:
        idx = None
        for df in self.prices.values():
            idx = df.index if idx is None else idx.union(df.index)
        return pd.DatetimeIndex([]) if idx is None else idx.sort_values()

    def history(self, symbol: str, as_of: pd.Timestamp) -> pd.DataFrame:
        df = self.prices.get(symbol)
        if df is None:
            return pd.DataFrame()
        return df.loc[df.index <= pd.Timestamp(as_of)]

    def latest_fundamental(self, symbol: str, as_of: pd.Timestamp) -> pd.Series | None:
        df = self.fundamentals.get(symbol)
        if df is None or df.empty:
            return None
        visible = df.loc[pd.to_datetime(df["ann_date"]) <= pd.Timestamp(as_of)]
        if visible.empty:
            return None
        return visible.sort_values("ann_date").iloc[-1]

    def moneyflow_history(self, symbol: str, as_of: pd.Timestamp) -> pd.DataFrame:
        df = self.moneyflow.get(symbol)
        if df is None:
            return pd.DataFrame()
        return df.loc[df.index <= pd.Timestamp(as_of)]


def _cache_load(path: pathlib.Path):
    # Pickle (not parquet) so the cache is dependency-free: neither pyarrow nor
    # fastparquet is a project dependency, and pickle round-trips OHLCV frames
    # (incl. their DatetimeIndex) losslessly.
    return pd.read_pickle(path) if path.exists() else None


def build_panel(symbols, start, end, provider, cache_dir) -> FactorPanel:
    cache_dir = pathlib.Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    prices, fundamentals, moneyflow = {}, {}, {}
    for sym in symbols:
        px_path = cache_dir / f"{sym}_px.pkl"
        px = _cache_load(px_path)
        if px is None:
            px = provider.get_historical_data(sym, start, end)
            if px is not None and not px.empty:
                px.to_pickle(px_path)
        if px is None or px.empty:
            continue
        px.index = pd.DatetimeIndex(px.index)
        prices[sym] = px

        fa_path = cache_dir / f"{sym}_fa.pkl"
        fa = _cache_load(fa_path)
        if fa is None:
            fa = provider.get_financial_indicators(sym, start, end)
            if fa is not None and not fa.empty:
                fa.to_pickle(fa_path)
        if fa is not None and not fa.empty:
            fa = fa.copy()
            # ``errors="coerce"`` so one malformed/None ann_date (seen in fresh
            # fetches) becomes NaT and is dropped, instead of crashing the whole
            # panel build with a strptime ValueError.
            fa["ann_date"] = pd.to_datetime(fa["ann_date"].astype(str), errors="coerce")
            fa = fa.dropna(subset=["ann_date"])
            if not fa.empty:
                fundamentals[sym] = fa

        mf_path = cache_dir / f"{sym}_mf.pkl"
        mf = _cache_load(mf_path)
        if mf is None:
            mf = provider.get_moneyflow(sym, start, end)
            if mf is not None and not mf.empty:
                mf.to_pickle(mf_path)
        if mf is not None and not mf.empty:
            mf = mf.copy()
            mf.index = pd.DatetimeIndex(
                pd.to_datetime(mf["trade_date"].astype(str), errors="coerce")
            )
            mf = mf[mf.index.notna()].sort_index()
            if not mf.empty:
                moneyflow[sym] = mf
    return FactorPanel(prices=prices, fundamentals=fundamentals, moneyflow=moneyflow)


def _to_yyyymmdd(value) -> str:
    """Coerce a date-like value to a Tushare ``YYYYMMDD`` string."""
    ts = pd.Timestamp(value)
    return ts.strftime("%Y%m%d")


def build_survivorship_free_universe(
    provider,
    index_code: str,
    start,
    end,
    *,
    sample_freq_days: int = 90,
    extra_dates=None,
) -> list[str]:
    """Survivorship-bias-free universe = UNION of historical index constituents.

    Calls ``provider.get_index_constituents(index_code, trade_date=d)`` (the
    point-in-time form) at a series of sample dates spanning ``[start, end]`` (one
    per ``sample_freq_days``, ~quarterly by default) plus any ``extra_dates`` (e.g.
    the actual rebalance dates), and unions the ``con_code`` sets. Any stock that
    was EVER in the index during the window therefore lands in the panel.

    Returns the de-duplicated symbol list in first-seen order so the panel/cache
    ordering is deterministic.
    """
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    sample_dates = list(
        pd.date_range(start=start_ts, end=end_ts, freq=f"{int(sample_freq_days)}D")
    )
    # Always include the endpoints so short ranges still sample at least twice.
    if not sample_dates or sample_dates[0] != start_ts:
        sample_dates.insert(0, start_ts)
    if sample_dates[-1] != end_ts:
        sample_dates.append(end_ts)
    for d in extra_dates or []:
        sample_dates.append(pd.Timestamp(d))
    # De-dup the sample grid (string-level) preserving order.
    seen_dates = list(dict.fromkeys(_to_yyyymmdd(d) for d in sample_dates))

    universe: list[str] = []
    seen: set[str] = set()
    for day in seen_dates:
        cons = provider.get_index_constituents(index_code, trade_date=day) or []
        for c in cons:
            c = str(c)
            if c and c not in seen:
                seen.add(c)
                universe.append(c)
    return universe


def build_eligible_by_date(
    provider,
    index_code: str,
    rebalance_dates,
) -> dict[pd.Timestamp, set[str]]:
    """Per-rebalance-date eligible set: as-of constituents MINUS suspended names.

    For each date ``D`` in ``rebalance_dates``:
        ``eligible(D) = {constituents as-of D} - {suspended on D}``

    One ``get_index_constituents(.., trade_date=D)`` and one
    ``get_suspended_symbols(D)`` call per date. Keyed by ``pd.Timestamp`` so it
    drops straight into ``factor_ic_series(.., eligible_by_date=...)``.
    """
    out: dict[pd.Timestamp, set[str]] = {}
    for d in rebalance_dates:
        ts = pd.Timestamp(d)
        day = _to_yyyymmdd(ts)
        cons = set(provider.get_index_constituents(index_code, trade_date=day) or [])
        suspended = provider.get_suspended_symbols(day) or set()
        out[ts] = cons - set(suspended)
    return out
