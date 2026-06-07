import numpy as np
import pandas as pd

from src.analytics.factors.price import (
    LowVolatilityFactor,
    MomentumFactor,
    ShortReversalFactor,
)
from src.data.factor_panel import FactorPanel


def _series(dates, closes, vol=1_000_000):
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [vol] * len(closes),
        },
        index=pd.DatetimeIndex(dates),
    )


def test_low_vol_factor_ranks_calmer_symbol_higher():
    dates = pd.bdate_range("2023-01-01", periods=120)
    calm = _series(dates, list(np.linspace(10, 11, 120)))  # tiny moves
    wild = _series(dates, list(10 + np.sin(np.arange(120)) * 3))  # big swings
    panel = FactorPanel(prices={"CALM": calm, "WILD": wild})
    f = LowVolatilityFactor()
    vals = f.compute(panel, as_of=dates[-1])
    assert vals["CALM"] > vals["WILD"]  # low-vol factor (higher = calmer)


def test_factor_is_point_in_time():
    dates = pd.bdate_range("2023-01-01", periods=120)
    closes = list(np.linspace(10, 11, 120))
    panel = FactorPanel(prices={"AAA": _series(dates, closes)})
    f = LowVolatilityFactor()
    base = f.compute(panel, as_of=dates[80])
    # inject an extreme spike AFTER as_of; factor at as_of must not change
    closes2 = closes[:]
    closes2[100] = 999.0
    panel2 = FactorPanel(prices={"AAA": _series(dates, closes2)})
    after = f.compute(panel2, as_of=dates[80])
    assert abs(base["AAA"] - after["AAA"]) < 1e-9


def test_momentum_positive_for_uptrend():
    dates = pd.bdate_range("2022-01-01", periods=300)
    panel = FactorPanel(prices={"UP": _series(dates, list(np.linspace(10, 30, 300)))})
    f = MomentumFactor()
    assert f.compute(panel, as_of=dates[-1])["UP"] > 0


def test_short_reversal_higher_for_recent_loser():
    dates = pd.bdate_range("2023-01-01", periods=30)
    loser = _series(dates, list(np.linspace(20, 10, 30)))  # falling
    winner = _series(dates, list(np.linspace(10, 20, 30)))  # rising
    panel = FactorPanel(prices={"LOSER": loser, "WINNER": winner})
    f = ShortReversalFactor()
    vals = f.compute(panel, as_of=dates[-1])
    assert vals["LOSER"] > vals["WINNER"]  # oversold ranks higher
