from __future__ import annotations

import numpy as np
import pandas as pd


class NetInflowFactor:
    name = "net_inflow"
    direction = 1

    def __init__(self, window: int = 5):
        self.window = window

    def compute(self, panel, as_of):
        out = {}
        for sym in panel.symbols:
            mf = panel.moneyflow_history(sym, as_of)
            if mf.empty or "net_mf_amount" not in mf.columns:
                continue
            v = mf["net_mf_amount"].iloc[-self.window:].mean()
            if np.isfinite(v):
                out[sym] = float(v)
        return pd.Series(out, dtype=float)


ALL_MONEYFLOW_FACTORS = [NetInflowFactor()]
