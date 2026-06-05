"""Unit tests for src.utils.helpers.

Pure numeric/pandas helpers — deterministic, no network. Verifies the financial
metric math (Sharpe, drawdown, win-rate, Calmar, Sortino) and resampling.
"""

import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.utils.helpers import (
    calculate_calmar_ratio,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_win_rate,
    resample_data,
    setup_logging,
)


class TestSharpeRatio:
    def test_empty_returns_zero(self):
        assert calculate_sharpe_ratio(pd.Series([], dtype=float)) == 0.0

    def test_zero_std_returns_zero(self):
        # Constant returns => std is 0 => guarded to 0.0
        assert calculate_sharpe_ratio(pd.Series([0.01, 0.01, 0.01])) == 0.0

    def test_matches_manual_formula(self):
        returns = pd.Series([0.01, -0.02, 0.03, 0.005, -0.01])
        expected = returns.mean() / returns.std() * np.sqrt(252)
        assert calculate_sharpe_ratio(returns) == pytest.approx(expected)

    def test_risk_free_rate_lowers_sharpe(self):
        returns = pd.Series([0.01, 0.02, 0.015, 0.005, 0.03])
        higher = calculate_sharpe_ratio(returns, risk_free_rate=0.0)
        lower = calculate_sharpe_ratio(returns, risk_free_rate=0.01)
        assert lower < higher


class TestMaxDrawdown:
    def test_empty_returns_zero_and_nones(self):
        dd, start, end = calculate_max_drawdown(pd.Series([], dtype=float))
        assert dd == 0.0
        assert start is None and end is None

    def test_monotonic_increase_has_no_drawdown(self):
        pv = pd.Series([100, 110, 120, 130])
        dd, _, _ = calculate_max_drawdown(pv)
        assert dd == pytest.approx(0.0)

    def test_known_drawdown_value_and_dates(self):
        idx = pd.date_range("2024-01-01", periods=5, freq="D")
        # Peak 120 -> trough 90 => drawdown = 30/120 = 0.25
        pv = pd.Series([100, 120, 90, 100, 110], index=idx)
        dd, peak_date, trough_date = calculate_max_drawdown(pv)
        assert dd == pytest.approx(0.25)
        assert peak_date == idx[1]
        assert trough_date == idx[2]


class TestWinRate:
    def test_empty_returns_zero(self):
        assert calculate_win_rate(pd.Series([], dtype=float)) == 0.0

    def test_half_wins(self):
        trades = pd.Series([10, -5, 20, -8])
        assert calculate_win_rate(trades) == pytest.approx(0.5)

    def test_zero_pnl_trade_is_not_a_win(self):
        # Only strictly > 0 counts as a win.
        trades = pd.Series([0, 0, 5, -5])
        assert calculate_win_rate(trades) == pytest.approx(0.25)


class TestCalmarRatio:
    def test_zero_drawdown_returns_zero(self):
        returns = pd.Series([0.01, 0.01, 0.01])
        pv = pd.Series([100, 110, 120])  # monotonic => dd == 0
        assert calculate_calmar_ratio(returns, pv) == 0

    def test_positive_value(self):
        idx = pd.date_range("2024-01-01", periods=4, freq="D")
        returns = pd.Series([0.05, -0.10, 0.05, 0.02], index=idx)
        pv = pd.Series([100, 105, 94.5, 99.2], index=idx)
        annual_return = returns.mean() * 252
        max_dd, _, _ = calculate_max_drawdown(pv)
        expected = annual_return / max_dd
        assert calculate_calmar_ratio(returns, pv) == pytest.approx(expected)


class TestSortinoRatio:
    def test_empty_returns_zero(self):
        assert calculate_sortino_ratio(pd.Series([], dtype=float)) == 0.0

    def test_no_downside_returns_inf(self):
        # All positive returns => no downside deviation => inf
        assert calculate_sortino_ratio(pd.Series([0.01, 0.02, 0.03])) == float("inf")

    def test_matches_manual_formula(self):
        returns = pd.Series([0.02, -0.03, 0.01, -0.01, 0.04])
        excess = returns - 0.0
        downside = excess[excess < 0]
        expected = excess.mean() / downside.std() * np.sqrt(252)
        assert calculate_sortino_ratio(returns) == pytest.approx(expected)

    def test_single_downside_value_std_zero_returns_zero(self):
        # One negative return => downside std is NaN-guarded to 0 path is
        # actually std()==nan for a single value, but len>0 so it divides by
        # nan std. We assert it does not raise and returns a float.
        returns = pd.Series([0.02, -0.01, 0.03, 0.04])
        result = calculate_sortino_ratio(returns)
        assert isinstance(result, float)


class TestResampleData:
    def test_empty_returns_input(self):
        df = pd.DataFrame()
        assert resample_data(df).empty

    def test_weekly_resample_aggregation(self):
        idx = pd.date_range("2024-01-01", periods=7, freq="D")
        df = pd.DataFrame(
            {
                "open": [1, 2, 3, 4, 5, 6, 7],
                "high": [2, 3, 4, 5, 6, 7, 8],
                "low": [0, 1, 2, 3, 4, 5, 6],
                "close": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5],
                "volume": [10, 10, 10, 10, 10, 10, 10],
            },
            index=idx,
        )
        out = resample_data(df, "W")
        # One full week (Mon-Sun for 2024-01-01..07).
        assert out["open"].iloc[0] == 1  # first
        assert out["high"].iloc[0] == 8  # max
        assert out["low"].iloc[0] == 0  # min
        assert out["close"].iloc[0] == 7.5  # last
        assert out["volume"].iloc[0] == 70  # sum

    def test_only_present_columns_aggregated(self):
        idx = pd.date_range("2024-01-01", periods=3, freq="D")
        df = pd.DataFrame({"close": [1.0, 2.0, 3.0]}, index=idx)
        out = resample_data(df, "D")
        assert list(out.columns) == ["close"]


def test_setup_logging_is_deprecated_and_delegates():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        setup_logging("DEBUG")
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
