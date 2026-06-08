"""Unit tests for the PURE low-volatility portfolio backtest core.

Network-free. Builds tiny synthetic ``FactorPanel`` + adjusted-close maps with
KNOWN structure so every claim is mechanically checkable:

  * the low-vol basket is selected by ascending realized vol;
  * net return is strictly below gross (frictions only ever cost);
  * turnover math (one-way, drift-aware) is bounded as constructed;
  * a constructed low-vol basket beats a high-vol basket on Sharpe;
  * periods with an insufficient eligible universe are skipped.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest.low_vol_portfolio import (
    BUY_RATE,
    SELL_RATE,
    run_low_vol_portfolio_backtest,
)
from src.data.factor_panel import FactorPanel


def _trading_index(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2020-01-01", periods=n)


def _price_frame(closes: list[float], index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1_000_000] * len(closes),
        },
        index=index,
    )


def _const_vol_series(seed: int, n: int, daily_vol: float, start: float = 100.0):
    """A geometric random walk with a fixed per-step lognormal vol."""
    rng = np.random.RandomState(seed)
    steps = rng.randn(n) * daily_vol
    prices = start * np.exp(np.cumsum(steps))
    return prices.tolist()


def _build_panel(symbol_closes: dict[str, list[float]], index: pd.DatetimeIndex) -> FactorPanel:
    prices = {sym: _price_frame(closes, index) for sym, closes in symbol_closes.items()}
    return FactorPanel(prices=prices)


def _adj_from_panel(panel: FactorPanel) -> dict[str, pd.Series]:
    # Identity adjustment (no dividends) for the simple cases: adj close == close.
    return {sym: df["close"].astype(float).rename(sym) for sym, df in panel.prices.items()}


def _monthly_rebal(panel: FactorPanel, idx: pd.DatetimeIndex, ref: str, min_hist: int = 61):
    s = pd.Series(1, index=idx)
    rebal = [pd.Timestamp(g.index[0]) for _, g in s.groupby([s.index.year, s.index.month])]
    return [d for d in rebal if len(panel.history(ref, d)) >= min_hist]


def _ascending_vol_universe(n: int, count: int, base: float = 0.002, step: float = 0.0015):
    """``count`` symbols with strictly increasing daily vol (S00 calmest)."""
    return {
        f"S{i:02d}.SH": _const_vol_series(100 + i, n, base + step * i)
        for i in range(count)
    }


def test_basket_picks_lowest_vol_names_and_metrics_present():
    n = 400
    idx = _trading_index(n)
    # 12 symbols with monotonically increasing vol; with basket_n=2 the basket
    # must always be the two calmest (S00, S01). The core needs basket_n+5
    # rankable names, so the universe is comfortably above that.
    closes = _ascending_vol_universe(n, 12)
    panel = _build_panel(closes, idx)
    adj = _adj_from_panel(panel)
    all_syms = set(closes)
    rebal = _monthly_rebal(panel, idx, "S00.SH")
    eligible = dict.fromkeys(rebal, all_syms)

    result = run_low_vol_portfolio_backtest(
        panel, adj, rebal, eligible, window=60, basket_n=2
    )

    assert "equity_curve" in result
    assert "metrics" in result
    metrics = result["metrics"]
    for leg in ("gross", "net", "benchmark"):
        assert leg in metrics
        m = metrics[leg]
        for key in ("cagr", "sharpe", "ann_vol", "max_drawdown"):
            assert key in m
    assert result["n_periods"] >= 1
    assert result["avg_annual_turnover"] is not None

    curve = result["equity_curve"]
    assert len(curve) == result["n_periods"]
    for point in curve:
        assert set(point) >= {"date", "basket_gross", "basket_net", "benchmark"}

    # The two calmest names -> basket vol below the equal-weight benchmark.
    assert metrics["net"]["ann_vol"] < metrics["benchmark"]["ann_vol"]


def test_net_is_below_gross_because_of_costs():
    n = 300
    idx = _trading_index(n)
    closes = _ascending_vol_universe(n, 10)
    panel = _build_panel(closes, idx)
    adj = _adj_from_panel(panel)
    rebal = _monthly_rebal(panel, idx, "S00.SH")
    eligible = {d: set(closes) for d in rebal}

    result = run_low_vol_portfolio_backtest(panel, adj, rebal, eligible, window=60, basket_n=3)
    curve = result["equity_curve"]
    # final net cumulative <= gross cumulative (costs only subtract)
    assert curve[-1]["basket_net"] <= curve[-1]["basket_gross"] + 1e-12
    # and strictly below somewhere (there is real turnover -> real cost)
    assert any(p["basket_net"] < p["basket_gross"] - 1e-9 for p in curve)
    assert result["metrics"]["net"]["cagr"] <= result["metrics"]["gross"]["cagr"] + 1e-9


def test_turnover_is_bounded_one_way():
    n = 250
    idx = _trading_index(n)
    closes = _ascending_vol_universe(n, 10)
    panel = _build_panel(closes, idx)
    adj = _adj_from_panel(panel)
    rebal = _monthly_rebal(panel, idx, "S00.SH")
    eligible = {d: set(closes) for d in rebal}

    result = run_low_vol_portfolio_backtest(panel, adj, rebal, eligible, window=60, basket_n=3)
    # One-way turnover per period is in [0, 1]; annualized = mean*12 <= 12.
    assert 0.0 <= result["avg_annual_turnover"] <= 12 + 1e-9
    for p in result["equity_curve"]:
        assert p["basket_net"] <= p["basket_gross"] + 1e-12


def test_low_vol_basket_beats_high_vol_basket_sharpe():
    """Constructed: calm names drift up steadily; wild names are pure noise.

    The low-vol bottom-N basket posts a higher Sharpe than the high-vol top-N
    basket selected from the same panel (``select_high_vol=True``).
    """
    n = 500
    idx = _trading_index(n)
    rng = np.random.RandomState(7)
    closes = {}
    for i in range(6):
        steps = rng.randn(n) * 0.003 + 0.0006  # low vol, mild up drift
        closes[f"CALM{i}.SH"] = (100 * np.exp(np.cumsum(steps))).tolist()
    for i in range(6):
        steps = rng.randn(n) * 0.030  # high vol, no drift
        closes[f"WILD{i}.SH"] = (100 * np.exp(np.cumsum(steps))).tolist()

    panel = _build_panel(closes, idx)
    adj = _adj_from_panel(panel)
    rebal = _monthly_rebal(panel, idx, "CALM0.SH")
    eligible = {d: set(closes) for d in rebal}

    low = run_low_vol_portfolio_backtest(panel, adj, rebal, eligible, window=60, basket_n=3)
    high = run_low_vol_portfolio_backtest(
        panel, adj, rebal, eligible, window=60, basket_n=3, select_high_vol=True
    )
    assert low["metrics"]["net"]["sharpe"] > high["metrics"]["net"]["sharpe"]


def test_insufficient_universe_is_skipped():
    """When eligible names < basket_n + 5, the period contributes nothing."""
    n = 200
    idx = _trading_index(n)
    closes = {
        "AAA.SH": _const_vol_series(31, n, 0.002),
        "BBB.SH": _const_vol_series(32, n, 0.004),
        "CCC.SH": _const_vol_series(33, n, 0.006),
    }
    panel = _build_panel(closes, idx)
    adj = _adj_from_panel(panel)
    rebal = _monthly_rebal(panel, idx, "AAA.SH")
    # basket_n=30 -> needs >=35 names but only 3 eligible -> every period skipped.
    eligible = {d: set(closes) for d in rebal}
    result = run_low_vol_portfolio_backtest(panel, adj, rebal, eligible, window=60, basket_n=30)
    assert result["n_periods"] == 0
    assert result["equity_curve"] == []
    assert result["metrics"]["net"] == {}


def test_total_return_prices_lift_dividend_payers():
    """adj_close != close lifts P&L: a flat-price high-dividend name still earns.

    Build a name whose UNADJUSTED close is dead flat (lowest vol -> always in the
    basket) but whose adjusted close ramps up (dividends). The basket gross
    return must be positive even though price vol ranking saw zero movement.
    """
    n = 250
    idx = _trading_index(n)
    flat = [100.0] * n
    closes = {"DIV.SH": flat}  # flat price -> zero vol -> always picked
    # plus a noisy filler universe so the eligible count clears basket_n+5.
    closes.update(_ascending_vol_universe(n, 8, base=0.01, step=0.004))
    panel = _build_panel(closes, idx)
    adj = _adj_from_panel(panel)
    # Override DIV.SH adjusted close to ramp +20% over the window.
    adj["DIV.SH"] = pd.Series(np.linspace(100.0, 120.0, n), index=idx, name="DIV.SH")
    rebal = _monthly_rebal(panel, idx, "DIV.SH")
    eligible = {d: set(closes) for d in rebal}

    result = run_low_vol_portfolio_backtest(panel, adj, rebal, eligible, window=60, basket_n=1)
    # Only DIV.SH in the basket; its adjusted P&L is strictly positive.
    assert result["metrics"]["gross"]["cagr"] > 0


def test_cost_rates_are_realistic_a_share_profile():
    # Sanity-lock the friction constants the research script defined.
    assert abs(BUY_RATE - (0.00025 + 0.0005 + 0.00001)) < 1e-12
    assert abs(SELL_RATE - (0.00025 + 0.0005 + 0.00001 + 0.0005)) < 1e-12
    assert SELL_RATE > BUY_RATE  # stamp duty on sells
