import numpy as np
import pandas as pd

from src.analytics.factors.price import (
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
