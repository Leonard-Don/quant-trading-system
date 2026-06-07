"""Offline unit tests for the northbound-flow factor's pure logic.

These exercise the trailing-Delta-ratio cross-section builder with synthetic
northbound data -- no network. The headline guarantee is POINT-IN-TIME safety:
injecting data dated AFTER ``as_of`` must not change the computed factor.
"""

from __future__ import annotations

import pandas as pd

from scripts.research.northbound_factor_ic import (
    NorthboundAccumulationFactor,
    trailing_ratio_delta,
)


def _synthetic_cross_sections(n_dates: int = 25, ratio_step: float = 0.1) -> dict:
    """Daily cross-sections where each symbol's ratio rises linearly.

    AAA rises by ``ratio_step`` per day, BBB by ``2*ratio_step``, CCC falls by
    ``ratio_step``. Dates are consecutive business days starting 2023-01-02.
    """
    dates = pd.bdate_range("2023-01-02", periods=n_dates)
    cs = {}
    for i, d in enumerate(dates):
        cs[pd.Timestamp(d)] = pd.Series(
            {
                "AAA.SH": 5.0 + i * ratio_step,
                "BBB.SZ": 3.0 + i * 2 * ratio_step,
                "CCC.SH": 8.0 - i * ratio_step,
            },
            dtype=float,
        )
    return cs, list(dates)


def test_delta_is_ratio_change_over_lookback():
    cs, dates = _synthetic_cross_sections(n_dates=25, ratio_step=0.1)
    as_of = dates[24]  # index 24 -> baseline index 4 with lookback=20
    delta = trailing_ratio_delta(cs, as_of, lookback=20)
    # 20 steps of +0.1 / +0.2 / -0.1.
    assert delta["AAA.SH"] == pytest_approx(2.0)
    assert delta["BBB.SZ"] == pytest_approx(4.0)
    assert delta["CCC.SH"] == pytest_approx(-2.0)


def test_point_in_time_future_data_ignored():
    """Injecting cross-sections AFTER as_of must not change the factor."""
    cs, dates = _synthetic_cross_sections(n_dates=25, ratio_step=0.1)
    as_of = dates[24]
    before = trailing_ratio_delta(cs, as_of, lookback=20)

    # Append wildly different FUTURE cross-sections (dates > as_of).
    future_dates = pd.bdate_range(dates[24] + pd.Timedelta(days=1), periods=10)
    for d in future_dates:
        cs[pd.Timestamp(d)] = pd.Series(
            {"AAA.SH": 999.0, "BBB.SZ": -999.0, "CCC.SH": 0.0}, dtype=float
        )
    after = trailing_ratio_delta(cs, as_of, lookback=20)
    pd.testing.assert_series_equal(before.sort_index(), after.sort_index())


def test_insufficient_history_returns_empty():
    cs, dates = _synthetic_cross_sections(n_dates=10, ratio_step=0.1)
    # Only 10 visible dates but lookback=20 needs 21 -> empty.
    assert trailing_ratio_delta(cs, dates[9], lookback=20).empty


def test_only_symbols_in_both_snapshots_survive():
    dates = pd.bdate_range("2023-01-02", periods=22)
    cs = {}
    for i, d in enumerate(dates):
        data = {"AAA.SH": 5.0 + i * 0.1, "BBB.SZ": 3.0 + i * 0.1}
        if i >= 5:  # CCC only appears partway through -> present in current, absent in baseline
            data["CCC.SH"] = 1.0 + i * 0.1
        cs[pd.Timestamp(d)] = pd.Series(data, dtype=float)
    delta = trailing_ratio_delta(cs, dates[21], lookback=20)  # baseline = index 1 (no CCC)
    assert set(delta.index) == {"AAA.SH", "BBB.SZ"}


def test_uses_latest_visible_snapshot_not_exact_as_of():
    """as_of falling on a non-snapshot day still uses the last visible date."""
    cs, dates = _synthetic_cross_sections(n_dates=25, ratio_step=0.1)
    # as_of is a weekend after dates[24]; should still resolve to dates[24] vs [4].
    as_of = dates[24] + pd.Timedelta(days=2)
    delta = trailing_ratio_delta(cs, as_of, lookback=20)
    assert delta["AAA.SH"] == pytest_approx(2.0)


def test_factor_adapter_matches_interface():
    cs, dates = _synthetic_cross_sections(n_dates=25, ratio_step=0.1)
    factor = NorthboundAccumulationFactor(cs, lookback=20)
    assert factor.name == "northbound_accumulation"
    assert factor.direction == 1
    out = factor.compute(panel=None, as_of=dates[24])  # panel unused
    assert out["BBB.SZ"] == pytest_approx(4.0)


def pytest_approx(value, tol: float = 1e-9):
    """Tiny local float-comparison helper (avoids importing pytest.approx by name
    so the test stays readable). Returns an object comparing equal within tol."""

    class _Approx:
        def __eq__(self, other):
            return abs(float(other) - float(value)) <= tol

        def __repr__(self):
            return f"~{value}"

    return _Approx()
