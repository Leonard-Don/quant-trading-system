"""Unit tests for the pure low-volatility ranking core.

The realized-vol definition under test MUST match the validated factor exactly
(``src/analytics/factors/price.py::LowVolatilityFactor``):
``vol = close.pct_change().dropna().iloc[-window:].std(ddof=0)`` — lower vol ranks
higher. These tests pin ordering, insufficient-history skipping, NaN handling,
deterministic tie-breaking and top-N truncation. Network-free / pure.
"""

import math

import numpy as np
import pandas as pd

from src.analytics.low_vol_screen import rank_low_volatility


def _frame(closes, *, start="2023-01-01"):
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1_000_000] * len(closes),
        },
        index=dates,
    )


def test_orders_ascending_by_realized_vol():
    # calm = tiny moves; wild = big swings
    calm = _frame(list(np.linspace(10.0, 11.0, 80)))
    wild = _frame(list(10 + np.sin(np.arange(80)) * 3))
    out = rank_low_volatility({"CALM": calm, "WILD": wild})
    assert [r["symbol"] for r in out] == ["CALM", "WILD"]
    assert out[0]["rank"] == 1
    assert out[1]["rank"] == 2
    assert out[0]["realized_vol"] < out[1]["realized_vol"]


def test_matches_validated_factor_vol_definition():
    closes = list(10 + np.cumsum(np.random.RandomState(0).randn(90) * 0.1))
    out = rank_low_volatility({"AAA": _frame(closes)}, window=60)
    expected = pd.Series(closes).pct_change().dropna().iloc[-60:].std(ddof=0)
    assert math.isclose(out[0]["realized_vol"], float(expected), rel_tol=1e-12)
    # annualized = vol * sqrt(252)
    assert math.isclose(
        out[0]["annualized_vol"], float(expected) * math.sqrt(252), rel_tol=1e-12
    )


def test_skips_symbols_with_insufficient_history():
    # window=60 needs >= 61 bars; 40 bars must be skipped
    short = _frame(list(np.linspace(10.0, 11.0, 40)))
    ok = _frame(list(np.linspace(10.0, 11.0, 80)))
    out = rank_low_volatility({"SHORT": short, "OK": ok}, window=60)
    assert [r["symbol"] for r in out] == ["OK"]


def test_skips_non_finite_vol():
    # A zero price inside the window makes the adjacent pct_change ``inf``
    # (x/0), so the std is non-finite -> the symbol is skipped. (This mirrors
    # the validated factor's ``pct_change().dropna().std(ddof=0)`` exactly.)
    good = _frame(list(np.linspace(10.0, 11.0, 80)))
    bad = _frame(list(np.linspace(10.0, 11.0, 80)))
    bad.iloc[-5, bad.columns.get_loc("close")] = 0.0
    out = rank_low_volatility({"GOOD": good, "BAD": bad}, window=60)
    symbols = [r["symbol"] for r in out]
    assert "GOOD" in symbols
    assert "BAD" not in symbols


def test_skips_all_nan_closes():
    good = _frame(list(np.linspace(10.0, 11.0, 80)))
    bad = _frame([np.nan] * 80)
    out = rank_low_volatility({"GOOD": good, "BAD": bad}, window=60)
    assert [r["symbol"] for r in out] == ["GOOD"]


def test_deterministic_tie_breaking_by_symbol():
    # identical price paths -> identical vol -> tie broken alphabetically
    path = list(np.linspace(10.0, 11.0, 80))
    out = rank_low_volatility(
        {"ZZZ": _frame(path), "AAA": _frame(path), "MMM": _frame(path)},
        window=60,
    )
    assert [r["symbol"] for r in out] == ["AAA", "MMM", "ZZZ"]
    assert [r["rank"] for r in out] == [1, 2, 3]


def test_top_n_truncation():
    frames = {}
    for i in range(10):
        amp = 0.01 * (i + 1)  # increasing noise -> increasing vol
        rs = np.random.RandomState(i)
        closes = list(10 + np.cumsum(rs.randn(80) * amp))
        frames[f"S{i:02d}"] = _frame(closes)
    out = rank_low_volatility(frames, window=60, top=3)
    assert len(out) == 3
    assert [r["rank"] for r in out] == [1, 2, 3]
    vols = [r["realized_vol"] for r in out]
    assert vols == sorted(vols)


def test_recent_return_uses_close_to_close_window():
    # +10% over the last 20 close-to-close bars
    closes = [10.0] * 60 + list(np.linspace(10.0, 11.0, 21))[1:]  # 80 bars total
    out = rank_low_volatility({"AAA": _frame(closes)}, window=60, recent_return_days=20)
    rec = out[0]["recent_return"]
    # last close 11.0 vs close 20 bars earlier (10.0) -> +10%
    assert math.isclose(rec, 10.0, rel_tol=1e-6)


def test_payload_shape_and_n_bars():
    out = rank_low_volatility({"AAA": _frame(list(np.linspace(10.0, 11.0, 80)))})
    row = out[0]
    assert set(row.keys()) == {
        "symbol",
        "realized_vol",
        "annualized_vol",
        "recent_return",
        "n_bars",
        "rank",
    }
    assert row["n_bars"] == 80
    assert row["symbol"] == "AAA"


def test_empty_input_returns_empty_list():
    assert rank_low_volatility({}) == []
