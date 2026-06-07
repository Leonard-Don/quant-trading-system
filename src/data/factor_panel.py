from __future__ import annotations

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
