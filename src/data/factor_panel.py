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
            fa["ann_date"] = pd.to_datetime(fa["ann_date"].astype(str))
            fundamentals[sym] = fa

        mf_path = cache_dir / f"{sym}_mf.pkl"
        mf = _cache_load(mf_path)
        if mf is None:
            mf = provider.get_moneyflow(sym, start, end)
            if mf is not None and not mf.empty:
                mf.to_pickle(mf_path)
        if mf is not None and not mf.empty:
            mf = mf.copy()
            mf.index = pd.DatetimeIndex(pd.to_datetime(mf["trade_date"].astype(str)))
            moneyflow[sym] = mf.sort_index()
    return FactorPanel(prices=prices, fundamentals=fundamentals, moneyflow=moneyflow)
