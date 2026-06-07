from __future__ import annotations

import pandas as pd

from src.data.factor_panel import FactorPanel


def _fundamental_factor(panel: FactorPanel, as_of, col: str) -> pd.Series:
    out = {}
    for sym in panel.symbols:
        row = panel.latest_fundamental(sym, as_of)
        if row is None or col not in row or pd.isna(row[col]):
            continue
        out[sym] = float(row[col])
    return pd.Series(out, dtype=float)


class ROEFactor:
    name = "roe"
    direction = 1

    def compute(self, panel, as_of):
        return _fundamental_factor(panel, as_of, "roe")


class ProfitGrowthFactor:
    name = "profit_growth"
    direction = 1

    def compute(self, panel, as_of):
        return _fundamental_factor(panel, as_of, "netprofit_yoy")


class RevenueGrowthFactor:
    name = "revenue_growth"
    direction = 1

    def compute(self, panel, as_of):
        return _fundamental_factor(panel, as_of, "or_yoy")


ALL_FUNDAMENTAL_FACTORS = [ROEFactor(), ProfitGrowthFactor(), RevenueGrowthFactor()]
