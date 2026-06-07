"""Offline tests for the earnings-forecast (业绩预告) IC probe.

No network: builds a synthetic forecast frame and a tiny price panel and asserts
the POINT-IN-TIME gate — a forecast announced AFTER ``as_of`` must NOT be
visible, and the latest forecast with ``ann_date <= as_of`` is the one used.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.research.earnings_forecast_factor_ic import (
    EarningsForecastGrowthFactor,
    _normalise_forecast_frame,
    latest_forecast_growth,
)
from src.data.factor_panel import FactorPanel


def _raw_forecast(rows: list[dict]) -> pd.DataFrame:
    """Build a raw ``pro.forecast``-shaped frame from row dicts."""
    return pd.DataFrame(
        rows,
        columns=["ts_code", "ann_date", "end_date", "p_change_min", "p_change_max"],
    )


@pytest.fixture
def forecast_df() -> pd.DataFrame:
    # Three announcements for one stock: Q4'21 (Jan'22), Q1'22 (Apr'22),
    # mid'22 (Jul'22). Midpoints: 18.0, 50.0, -40.0.
    return _normalise_forecast_frame(
        _raw_forecast(
            [
                {"ts_code": "000651.SZ", "ann_date": "20220117",
                 "end_date": "20211231", "p_change_min": 16.0, "p_change_max": 20.0},
                {"ts_code": "000651.SZ", "ann_date": "20220415",
                 "end_date": "20220331", "p_change_min": 40.0, "p_change_max": 60.0},
                {"ts_code": "000651.SZ", "ann_date": "20220715",
                 "end_date": "20220630", "p_change_min": -50.0, "p_change_max": -30.0},
            ]
        )
    )


def test_midpoint_computation(forecast_df: pd.DataFrame) -> None:
    assert list(forecast_df["forecast_growth"]) == [18.0, 50.0, -40.0]


def test_future_forecast_not_visible(forecast_df: pd.DataFrame) -> None:
    # As of the day BEFORE the first announcement: nothing is visible.
    assert latest_forecast_growth(forecast_df, "20220116") is None


def test_latest_visible_forecast_used(forecast_df: pd.DataFrame) -> None:
    # On the announcement day, that forecast becomes visible (inclusive gate).
    assert latest_forecast_growth(forecast_df, "20220117") == 18.0
    # Between the 1st and 2nd announcements, the 1st is still the latest visible.
    assert latest_forecast_growth(forecast_df, "20220301") == 18.0
    # After the 2nd, the newer one supersedes it...
    assert latest_forecast_growth(forecast_df, "20220601") == 50.0
    # ...and after the 3rd, the latest (negative) one wins.
    assert latest_forecast_growth(forecast_df, "20221001") == -40.0


def test_a_forecast_announced_after_as_of_is_excluded(forecast_df: pd.DataFrame) -> None:
    # The Apr (50.0) and Jul (-40.0) forecasts are announced AFTER 2022-03-01,
    # so the value as of that date must be the Jan forecast (18.0), not them.
    val = latest_forecast_growth(forecast_df, "20220301")
    assert val == 18.0
    assert val != 50.0
    assert val != -40.0


def _panel_with(symbols: list[str]) -> FactorPanel:
    idx = pd.date_range("2022-01-01", periods=400, freq="D")
    prices = {
        s: pd.DataFrame({"close": [10.0 + i * 0.01 for i in range(len(idx))]}, index=idx)
        for s in symbols
    }
    return FactorPanel(prices=prices)


def test_factor_compute_gates_by_ann_date(forecast_df: pd.DataFrame) -> None:
    panel = _panel_with(["000651.SZ"])
    factor = EarningsForecastGrowthFactor({"000651.SZ": forecast_df})

    # Before any announcement -> the stock is simply absent (no visible forecast).
    early = factor.compute(panel, pd.Timestamp("2022-01-16"))
    assert "000651.SZ" not in early.index
    assert factor.coverage(panel, pd.Timestamp("2022-01-16")) == 0

    # After the first announcement -> present with the Jan midpoint.
    later = factor.compute(panel, pd.Timestamp("2022-03-01"))
    assert later["000651.SZ"] == 18.0
    assert factor.coverage(panel, pd.Timestamp("2022-03-01")) == 1


def test_factor_skips_symbols_without_forecast() -> None:
    panel = _panel_with(["AAA.SZ", "BBB.SZ"])
    factor = EarningsForecastGrowthFactor(
        {"AAA.SZ": _normalise_forecast_frame(pd.DataFrame())}
    )
    vals = factor.compute(panel, pd.Timestamp("2023-01-01"))
    assert vals.empty


def test_normalise_empty_frame_is_safe() -> None:
    out = _normalise_forecast_frame(pd.DataFrame())
    assert out.empty
    assert "forecast_growth" in out.columns
    # An empty frame must still gate cleanly (no crash, returns None).
    assert latest_forecast_growth(out, "20230101") is None


def test_duplicate_revisions_deduplicated() -> None:
    # Tushare emits update revisions as duplicate rows; dedupe must collapse them.
    df = _normalise_forecast_frame(
        _raw_forecast(
            [
                {"ts_code": "X.SZ", "ann_date": "20210415", "end_date": "20210331",
                 "p_change_min": 106.0, "p_change_max": 144.0},
                {"ts_code": "X.SZ", "ann_date": "20210415", "end_date": "20210331",
                 "p_change_min": 106.0, "p_change_max": 144.0},
            ]
        )
    )
    assert len(df) == 1
    assert df.iloc[0]["forecast_growth"] == 125.0
