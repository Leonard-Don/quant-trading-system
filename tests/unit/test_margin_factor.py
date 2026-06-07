"""Unit tests for the margin-financing IC probe factor.

Covers (1) the trailing-Δ math on a known series, and (2) the point-in-time
guarantee: margin rows with ``trade_date`` AFTER the as_of date must not change
the computed factor (the factor must only read snapshots <= as_of).

No network: a fake ``pro`` client returns margin frames from an in-memory dict.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pandas as pd
import pytest

# Load the script module directly (scripts/research is not an installed package).
_SPEC = importlib.util.spec_from_file_location(
    "margin_factor_ic",
    pathlib.Path(__file__).resolve().parents[2] / "scripts/research/margin_factor_ic.py",
)
mfi = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mfi)


class _FakePro:
    """Stand-in for the tushare ``pro`` client.

    ``margin_detail(trade_date=...)`` returns a frame with ``ts_code``/``rzye`` from
    ``self.data[trade_date]``; records every requested trade_date in ``self.calls``.
    """

    def __init__(self, data: dict[str, dict[str, float]]):
        self.data = data
        self.calls: list[str] = []

    def margin_detail(self, trade_date: str) -> pd.DataFrame:
        self.calls.append(trade_date)
        rows = self.data.get(trade_date, {})
        return pd.DataFrame(
            {"trade_date": trade_date, "ts_code": list(rows), "rzye": list(rows.values())}
        )


class _FakeProvider:
    def __init__(self, pro: _FakePro):
        self._pro = pro

    def _get_pro_client(self):
        return self._pro


class _Panel:
    """Minimal FactorPanel-shaped stub: just symbols + a union trading calendar."""

    def __init__(self, symbols: list[str], dates: pd.DatetimeIndex):
        self._symbols = symbols
        self._dates = pd.DatetimeIndex(dates).sort_values()

    @property
    def symbols(self) -> list[str]:
        return self._symbols

    @property
    def trading_dates(self) -> pd.DatetimeIndex:
        return self._dates


def _make(tmp_path, data, *, lookback=2, symbols=("A.SH", "B.SH"), n_days=10):
    pro = _FakePro(data)
    provider = _FakeProvider(pro)
    factor = mfi.MarginBuildupFactor(provider=provider, lookback=lookback, cache_dir=tmp_path)
    cal = pd.bdate_range("2023-01-02", periods=n_days)
    panel = _Panel(list(symbols), cal)
    return factor, panel, pro, cal


def test_trailing_delta_math(tmp_path):
    """(rzye[D] - rzye[D-lookback]) / rzye[D-lookback] on a known series."""
    cal = pd.bdate_range("2023-01-02", periods=10)
    d_now = mfi._yyyymmdd(cal[-1])
    d_prev = mfi._yyyymmdd(cal[-1 - 2])  # lookback=2
    data = {
        d_prev: {"A.SH": 100.0, "B.SH": 200.0},
        d_now: {"A.SH": 150.0, "B.SH": 180.0},  # +50% and -10%
    }
    factor, panel, _pro, _cal = _make(tmp_path, data, lookback=2)
    vals = factor.compute(panel, cal[-1])
    assert vals["A.SH"] == pytest.approx(0.5)
    assert vals["B.SH"] == pytest.approx(-0.1)


def test_zero_or_missing_prev_dropped(tmp_path):
    """A non-positive or missing baseline rzye yields no factor value (no div-by-0)."""
    cal = pd.bdate_range("2023-01-02", periods=10)
    d_now = mfi._yyyymmdd(cal[-1])
    d_prev = mfi._yyyymmdd(cal[-1 - 2])
    data = {
        d_prev: {"A.SH": 0.0, "B.SH": 200.0},  # A baseline is 0 -> dropped
        d_now: {"A.SH": 150.0, "B.SH": 180.0},
    }
    factor, panel, _pro, _cal = _make(tmp_path, data, lookback=2)
    vals = factor.compute(panel, cal[-1])
    assert "A.SH" not in vals
    assert vals["B.SH"] == pytest.approx(-0.1)


def test_point_in_time_future_rows_ignored(tmp_path):
    """Injecting margin rows DATED AFTER as_of must not change the factor.

    The factor at as_of must read only the snapshots for D (<= as_of) and
    D-lookback, never a future trade_date.
    """
    cal = pd.bdate_range("2023-01-02", periods=10)
    as_of = cal[5]  # D is cal[5]; D-2 is cal[3]
    d_now = mfi._yyyymmdd(cal[5])
    d_prev = mfi._yyyymmdd(cal[3])
    d_future = mfi._yyyymmdd(cal[8])  # strictly after as_of

    base = {
        d_prev: {"A.SH": 100.0, "B.SH": 200.0},
        d_now: {"A.SH": 150.0, "B.SH": 180.0},
    }
    factor, panel, _pro, _cal = _make(tmp_path, dict(base), lookback=2)
    before = factor.compute(panel, as_of)

    # Now inject a wildly different FUTURE snapshot and recompute on a fresh cache.
    poisoned = dict(base)
    poisoned[d_future] = {"A.SH": 9_999.0, "B.SH": 1.0}
    factor2, panel2, pro2, _ = _make(tmp_path / "c2", poisoned, lookback=2)
    after = factor2.compute(panel2, as_of)

    assert before.to_dict() == pytest.approx(after.to_dict())
    # And the factor must never have requested the future trade_date.
    assert d_future not in pro2.calls
    assert set(pro2.calls) <= {d_now, d_prev}


def test_uses_only_dates_at_or_before_as_of(tmp_path):
    """D is the last trading day <= as_of (not the panel's final day)."""
    cal = pd.bdate_range("2023-01-02", periods=10)
    as_of = cal[4]
    expected_now = mfi._yyyymmdd(cal[4])
    expected_prev = mfi._yyyymmdd(cal[2])  # lookback=2
    data = {
        expected_prev: {"A.SH": 100.0},
        expected_now: {"A.SH": 120.0},
    }
    factor, panel, pro, _ = _make(tmp_path, data, lookback=2, symbols=("A.SH",))
    vals = factor.compute(panel, as_of)
    assert vals["A.SH"] == pytest.approx(0.2)
    assert set(pro.calls) == {expected_now, expected_prev}


def test_empty_snapshot_returns_empty(tmp_path):
    """Missing margin data for D yields an empty factor series, not an error."""
    cal = pd.bdate_range("2023-01-02", periods=10)
    factor, panel, _pro, _ = _make(tmp_path, {}, lookback=2)
    vals = factor.compute(panel, cal[-1])
    assert vals.empty
