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


def test_eligible_by_date_restricts_cross_section():
    # On each date, an ineligible symbol must be excluded from that date's IC.
    # Build a panel; compute IC with NO filter, then with a filter that drops one
    # symbol per date. The filtered IC must equal the IC recomputed on the
    # restricted (symbol-dropped) cross-section — proving the symbol was excluded.
    panel, dates, factor, horizon = _panel_with_relationship(seed=3)
    syms = panel.symbols
    dropped = syms[0]
    eligible = {pd.Timestamp(d): set(syms) - {dropped} for d in dates}

    ic_full = factor_ic_series(factor, panel, dates, horizon)
    ic_filtered = factor_ic_series(
        factor, panel, dates, horizon, eligible_by_date=eligible
    )

    # Filtering changed the series (the dropped symbol mattered to at least one date).
    assert not ic_full.equals(ic_filtered)

    # And the filtered IC matches a panel that simply never had the dropped symbol.
    restricted_panel = FactorPanel(
        prices={s: df for s, df in panel.prices.items() if s != dropped}
    )

    class _Restricted:
        name = factor.name
        direction = factor.direction

        def compute(self, p, as_of):
            full = factor.compute(panel, as_of)
            return full.drop(index=[dropped], errors="ignore")

    ic_restricted = factor_ic_series(
        _Restricted(), restricted_panel, dates, horizon
    )
    pd.testing.assert_series_equal(ic_filtered, ic_restricted)


def test_eligible_by_date_default_none_unchanged():
    # Back-compat: eligible_by_date=None == no filter == current behavior.
    panel, dates, factor, horizon = _panel_with_relationship(seed=4)
    a = factor_ic_series(factor, panel, dates, horizon)
    b = factor_ic_series(factor, panel, dates, horizon, eligible_by_date=None)
    pd.testing.assert_series_equal(a, b)


def test_evaluate_factor_threads_eligible_by_date():
    # evaluate_factor must accept + thread eligible_by_date down to the IC series.
    panel, dates, factor, horizon = _panel_with_relationship(seed=5)
    syms = panel.symbols
    eligible = {pd.Timestamp(d): set(syms) - {syms[0]} for d in dates}
    rep = evaluate_factor(
        factor, panel, dates, horizon, eligible_by_date=eligible
    )
    rep_full = evaluate_factor(factor, panel, dates, horizon)
    assert rep["mean_ic"] != rep_full["mean_ic"]


def test_forward_returns_use_total_return_prices_across_a_split():
    # A 2:1 split halves the raw close (phantom -50% "return"); the adj_factor
    # doubles on the same day. Total-return prices (close * adj) must see ~0%.
    dates = pd.bdate_range("2024-01-01", periods=6)
    closes = [10.0, 10.0, 10.0, 5.0, 5.0, 5.0]  # split effective on day 4
    adj = pd.Series([1.0, 1.0, 1.0, 2.0, 2.0, 2.0], index=dates)
    px = pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes,
         "volume": [1e6] * 6},
        index=dates,
    )
    panel = FactorPanel(prices={"SPLIT": px}, adj={"SPLIT": adj})
    fr = forward_returns(panel, dates[1], horizon=3)
    assert abs(fr["SPLIT"]) < 1e-12  # not -0.5


def test_forward_returns_include_dividends_via_adj_factor():
    # An ex-dividend day drops the raw close; adj_factor steps up so the
    # total-return path credits the payout instead of booking a fake loss.
    dates = pd.bdate_range("2024-01-01", periods=4)
    closes = [100.0, 100.0, 95.0, 95.0]  # 5 paid out on day 3
    adj = pd.Series([1.0, 1.0, 100.0 / 95.0, 100.0 / 95.0], index=dates)
    px = pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes,
         "volume": [1e6] * 4},
        index=dates,
    )
    panel = FactorPanel(prices={"DIV": px}, adj={"DIV": adj})
    fr = forward_returns(panel, dates[0], horizon=2)
    assert abs(fr["DIV"]) < 1e-12  # raw close would say -5%


def test_forward_returns_fall_back_to_raw_close_without_adj():
    # Panels without adj data (legacy callers, tests) keep the old behavior.
    panel, dates, _, horizon = _panel_with_relationship(seed=7)
    sym = panel.symbols[0]
    df = panel.prices[sym]
    fr = forward_returns(panel, dates[0], horizon)
    pos = df.index.searchsorted(pd.Timestamp(dates[0]))
    expected = float(df["close"].iloc[pos + horizon] / df["close"].iloc[pos] - 1.0)
    assert abs(fr[sym] - expected) < 1e-12


def test_evaluate_factor_reports_oos_only_diagnostics():
    # The gate's headline evidence must be measurable OOS-only: report the OOS
    # segment's ICIR and a one-sided t-test (H1: mean OOS IC > 0) so the
    # scorecard can apply multiple-testing control. Full-sample icir stays as a
    # diagnostic but must no longer be the only dispersion statistic.
    panel, dates, factor, horizon = _panel_with_relationship()
    rep = evaluate_factor(factor, panel, dates, horizon, train_frac=0.7)
    assert rep["oos_n"] > 0
    assert rep["oos_icir"] > 0  # strong synthetic factor works OOS too
    assert np.isfinite(rep["oos_t_stat"])
    assert 0.0 <= rep["oos_p_value"] < 0.05  # clearly significant


def test_oos_p_value_is_one_sided():
    # A factor that predicts the WRONG way must get p ~ 1, not ~ 0: the test is
    # one-sided (H1: mean OOS IC > 0), so negative IC is evidence AGAINST.
    panel, dates, factor, horizon = _panel_with_relationship(seed=2)

    class _Inverted:
        name = "inverted"
        direction = -1  # flips the sign of every cross-sectional IC

        def compute(self, p, as_of):
            return factor.compute(p, as_of)

    rep = evaluate_factor(_Inverted(), panel, dates, horizon, train_frac=0.7)
    assert rep["oos_mean_ic"] < 0
    assert rep["oos_p_value"] > 0.5


def test_evaluate_factor_empty_ic_reports_nan_oos_diagnostics():
    # Empty IC series (no evaluable dates) -> the new keys exist and are NaN,
    # so downstream consumers can rely on the schema unconditionally.
    panel, _, factor, horizon = _panel_with_relationship(seed=6)
    rep = evaluate_factor(factor, panel, [], horizon)
    assert rep["passes"] is False
    assert rep["oos_n"] == 0
    for key in ("oos_icir", "oos_t_stat", "oos_p_value"):
        assert key in rep and not np.isfinite(rep[key])


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
