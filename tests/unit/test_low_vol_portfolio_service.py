"""Service-level honesty tests for ``run_low_vol_portfolio_from_cache``.

The pure backtester's first documented honesty invariant is total-return P&L
(close × adj_factor). The service must therefore COUNT symbols that fall back
to the raw unadjusted close (missing/unreadable ``{sym}_adj.pkl`` and no
provider fetch), surface that count in the result, and REFUSE the run when the
fallback ratio is material — instead of silently shipping a dividend-free
backtest under a "总收益复权价" disclaimer (2026-06-10 audit finding).
"""

import pandas as pd
import pytest

from backend.app.services.low_vol_portfolio_service import (
    AdjFallbackMaterialError,
    run_low_vol_portfolio_from_cache,
)

_N_BARS = 320  # > MIN_HISTORY_BARS so at least a few monthly rebalances exist


def _write_px(cache_dir, sym, seed=0):
    dates = pd.bdate_range("2018-01-02", periods=_N_BARS)
    base = 10.0 + seed
    closes = [base + 0.01 * i for i in range(_N_BARS)]
    px = pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes,
         "volume": [1e6] * _N_BARS},
        index=dates,
    )
    px.to_pickle(cache_dir / f"{sym}_px.pkl")
    return dates


def _write_adj(cache_dir, sym, dates):
    pd.Series([1.0] * len(dates), index=dates, name="adj_factor").to_pickle(
        cache_dir / f"{sym}_adj.pkl"
    )


class _CacheOnlyProvider:
    """Constituents/suspensions only — NO get_adj_factor, NO price fetch needed
    (px pickles are pre-written), so a missing adj pickle stays missing."""

    def __init__(self, symbols):
        self._symbols = list(symbols)

    def get_index_constituents(self, code, trade_date=None):
        return list(self._symbols)

    def get_suspended_symbols(self, trade_date):
        return set()

    def get_financial_indicators(self, symbol, start, end):
        return pd.DataFrame()

    def get_moneyflow(self, symbol, start, end):
        return pd.DataFrame()


def test_material_adj_fallback_refuses_by_default(tmp_path):
    # 1 of 2 symbols lacks {sym}_adj.pkl -> 50% fallback >> threshold -> refuse
    # loudly with an actionable message, never silently run dividend-free.
    dates = _write_px(tmp_path, "AAA")
    _write_px(tmp_path, "BBB", seed=5)
    _write_adj(tmp_path, "AAA", dates)
    prov = _CacheOnlyProvider(["AAA", "BBB"])
    with pytest.raises(AdjFallbackMaterialError) as ei:
        run_low_vol_portfolio_from_cache(prov, "000300.SH", cache_dir=tmp_path)
    assert "adj_factor" in str(ei.value)


def test_adj_fallback_reported_when_explicitly_allowed(tmp_path):
    # With the threshold lifted, the run proceeds but the payload must carry
    # the fallback accounting so the endpoint can flag it.
    dates = _write_px(tmp_path, "AAA")
    _write_px(tmp_path, "BBB", seed=5)
    _write_adj(tmp_path, "AAA", dates)
    prov = _CacheOnlyProvider(["AAA", "BBB"])
    result = run_low_vol_portfolio_from_cache(
        prov, "000300.SH", cache_dir=tmp_path, max_adj_fallback_ratio=1.0
    )
    af = result["adj_fallback"]
    assert af["count"] == 1
    assert af["symbols"] == ["BBB"]
    assert abs(af["ratio"] - 0.5) < 1e-12


def test_no_adj_fallback_when_cache_complete(tmp_path):
    dates = _write_px(tmp_path, "AAA")
    d2 = _write_px(tmp_path, "BBB", seed=5)
    _write_adj(tmp_path, "AAA", dates)
    _write_adj(tmp_path, "BBB", d2)
    prov = _CacheOnlyProvider(["AAA", "BBB"])
    result = run_low_vol_portfolio_from_cache(prov, "000300.SH", cache_dir=tmp_path)
    assert result["adj_fallback"] == {"count": 0, "ratio": 0.0, "symbols": []}
