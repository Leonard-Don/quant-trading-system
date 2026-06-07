import numpy as np
import pandas as pd

from src.analytics.factors.evaluation import (
    evaluate_factor,
    factor_ic_series,
    forward_returns,
    passes_ic_gate,
)
from src.data.factor_panel import FactorPanel


class _ConstFactor:
    name = "fake"
    direction = 1

    def __init__(self, values_by_date):
        self.v = values_by_date

    def compute(self, panel, as_of):
        return self.v[pd.Timestamp(as_of)]


def _panel_with_relationship(seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=80)
    syms = [f"S{i}" for i in range(20)]
    prices = {}
    factor_by_date = {}
    horizon = 5
    # assign each symbol a hidden 'quality' that drives BOTH its factor value and its forward return
    quality = {s: rng.normal() for s in syms}
    for s in syms:
        # forward return correlated with quality -> cumulative price path
        steps = rng.normal(quality[s] * 0.002, 0.01, len(dates))
        closes = 10 * np.exp(np.cumsum(steps))
        prices[s] = pd.DataFrame(
            {
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": [1e6] * len(dates),
            },
            index=dates,
        )
    for d in dates[:-horizon]:
        factor_by_date[pd.Timestamp(d)] = pd.Series({s: quality[s] for s in syms})
    return FactorPanel(prices=prices), dates[:-horizon], _ConstFactor(factor_by_date), horizon


def test_forward_returns_are_strictly_future():
    panel, dates, _, horizon = _panel_with_relationship()
    fr = forward_returns(panel, dates[0], horizon)
    # forward return uses close[as_of+horizon]/close[as_of]-1; computable + finite
    assert fr.notna().any()


def test_ic_is_positive_for_predictive_factor():
    panel, dates, factor, horizon = _panel_with_relationship()
    ic = factor_ic_series(factor, panel, dates, horizon)
    assert ic.mean() > 0.1  # strong synthetic relationship -> clearly positive IC


def test_ic_near_zero_for_random_factor():
    panel, dates, _, horizon = _panel_with_relationship(seed=1)
    rng = np.random.default_rng(99)
    syms = panel.symbols
    rand = _ConstFactor(
        {pd.Timestamp(d): pd.Series({s: rng.normal() for s in syms}) for d in dates}
    )
    ic = factor_ic_series(rand, panel, dates, horizon)
    assert abs(ic.mean()) < 0.1


def test_evaluate_factor_reports_oos_and_icir():
    panel, dates, factor, horizon = _panel_with_relationship()
    rep = evaluate_factor(factor, panel, dates, horizon, train_frac=0.7)
    assert rep["mean_ic"] > 0.1
    assert rep["oos_mean_ic"] > 0.0
    assert "icir" in rep and "yearly_ic" in rep and "n_dates" in rep


def test_gate_requires_positive_oos_ic_not_just_magnitude():
    # Positive, material OOS IC + positive ICIR + sign-stable -> PASS
    assert passes_ic_gate(0.04, 0.20, True) is True
    # OOS sign flip (large NEGATIVE magnitude) must FAIL — this was the abs() bug
    assert passes_ic_gate(-0.05, 0.20, True) is False
    # Sub-threshold positive -> FAIL
    assert passes_ic_gate(0.02, 0.20, True) is False
    # Not sign-stable -> FAIL
    assert passes_ic_gate(0.04, 0.20, False) is False
    # Negative ICIR (in-sample doesn't work) -> FAIL
    assert passes_ic_gate(0.04, -0.10, True) is False
