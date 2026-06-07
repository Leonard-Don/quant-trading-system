from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.factor_panel import FactorPanel


class LowVolatilityFactor:
    name = "low_volatility"
    direction = 1

    def __init__(self, window: int = 60):
        self.window = window

    def compute(self, panel: FactorPanel, as_of) -> pd.Series:
        out = {}
        for sym in panel.symbols:
            h = panel.history(sym, as_of)
            if len(h) < self.window + 1:
                continue
            rets = h["close"].pct_change().dropna().iloc[-self.window:]
            vol = rets.std(ddof=0)
            if np.isfinite(vol):
                out[sym] = -float(vol)  # higher = calmer
        return pd.Series(out, dtype=float)


class MomentumFactor:
    name = "momentum_12_1"
    direction = 1

    def __init__(self, lookback: int = 252, gap: int = 21):
        self.lookback, self.gap = lookback, gap

    def compute(self, panel: FactorPanel, as_of) -> pd.Series:
        out = {}
        for sym in panel.symbols:
            h = panel.history(sym, as_of)
            if len(h) < self.lookback + 1:
                continue
            c = h["close"]
            out[sym] = float(c.iloc[-self.gap] / c.iloc[-self.lookback] - 1.0)
        return pd.Series(out, dtype=float)


class ShortReversalFactor:
    name = "short_reversal"
    direction = 1

    def __init__(self, window: int = 5):
        self.window = window

    def compute(self, panel: FactorPanel, as_of) -> pd.Series:
        out = {}
        for sym in panel.symbols:
            h = panel.history(sym, as_of)
            if len(h) < self.window + 1:
                continue
            c = h["close"]
            out[sym] = -float(c.iloc[-1] / c.iloc[-self.window - 1] - 1.0)  # higher = more oversold
        return pd.Series(out, dtype=float)


class TurnoverReversalFactor:
    name = "turnover_reversal"
    direction = 1

    def __init__(self, window: int = 20):
        self.window = window

    def compute(self, panel: FactorPanel, as_of) -> pd.Series:
        out = {}
        for sym in panel.symbols:
            h = panel.history(sym, as_of)
            if len(h) < self.window:
                continue
            out[sym] = -float(h["volume"].iloc[-self.window:].mean())  # higher = less crowded
        return pd.Series(out, dtype=float)


ALL_PRICE_FACTORS = [
    LowVolatilityFactor(),
    MomentumFactor(),
    ShortReversalFactor(),
    TurnoverReversalFactor(),
]
