"""Endpoint tests for ``GET /analysis/low-volatility-portfolio``.

Fully mocked — NO network and NO disk cache reads. The heavy service
(``run_low_vol_portfolio_from_cache``) is monkeypatched to return a deterministic
synthetic backtest, so these tests pin the endpoint contract: response shape,
``net < gross``, the honest disclaimer, daily caching, and param validation.
"""

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import analysis
from backend.app.core.error_handler import register_exception_handlers
from backend.app.services import low_vol_portfolio_service
from src.utils.cache import cache_manager


def _fake_backtest(provider, index_code, *, basket_n=30, **kwargs):
    # Deterministic synthetic result with net < gross and a benchmark leg.
    return {
        "index": index_code,
        "span": "20180101..20241231",
        "basket_n": basket_n,
        "window": 60,
        "cost_rates": {"buy": 0.00076, "sell": 0.00126},
        "equity_curve": [
            {"date": "2019-01-02", "basket_gross": 1.0, "basket_net": 1.0, "benchmark": 1.0},
            {"date": "2019-02-01", "basket_gross": 1.05, "basket_net": 1.04, "benchmark": 1.03},
            {"date": "2019-03-01", "basket_gross": 1.10, "basket_net": 1.08, "benchmark": 1.05},
        ],
        "metrics": {
            "gross": {"cagr": 0.06, "ann_vol": 0.13, "sharpe": 0.46, "max_drawdown": -0.13, "n_periods": 60},
            "net": {"cagr": 0.05, "ann_vol": 0.12, "sharpe": 0.44, "max_drawdown": -0.13, "n_periods": 60},
            "benchmark": {"cagr": 0.03, "ann_vol": 0.18, "sharpe": 0.22, "max_drawdown": -0.23, "n_periods": 60},
        },
        "avg_annual_turnover": 2.7,
        "n_periods": 60,
    }


class _FakeProvider:
    def get_index_constituents(self, code, trade_date=None):
        return ["111111.SH"]


class _FakeFactory:
    def __init__(self, provider):
        self._provider = provider

    def get_provider(self, name=None):
        assert name == "tushare"
        return self._provider


class _FakeDataManager:
    def __init__(self):
        self.provider = _FakeProvider()
        self.provider_factory = _FakeFactory(self.provider)


@pytest.fixture
def client(monkeypatch):
    fake_dm = _FakeDataManager()
    monkeypatch.setattr(analysis, "data_manager", fake_dm)

    calls = {"n": 0}

    def counting_backtest(provider, index_code, *, basket_n=30, **kwargs):
        calls["n"] += 1
        return _fake_backtest(provider, index_code, basket_n=basket_n, **kwargs)

    monkeypatch.setattr(
        low_vol_portfolio_service,
        "run_low_vol_portfolio_from_cache",
        counting_backtest,
    )
    cache_manager.clear()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(analysis.router, prefix="/analysis")
    test_client = TestClient(app)
    test_client.backtest_calls = calls  # type: ignore[attr-defined]
    return test_client


def test_returns_metrics_curve_and_disclaimer(client):
    resp = client.get("/analysis/low-volatility-portfolio?universe=csi300&basket_n=30")
    assert resp.status_code == 200
    body = resp.json()

    assert body["universe"] == "csi300"
    assert body["index_code"] == "000300.SH"
    assert body["basket_n"] == 30
    assert body["window"] == 60
    assert body["span"] == "20180101..20241231"
    assert body["avg_annual_turnover"] == 2.7
    assert body["cost_rates"]["sell"] > body["cost_rates"]["buy"]
    assert "as_of" in body

    # metrics: all three legs present with the key risk/return fields
    metrics = body["metrics"]
    for leg in ("gross", "net", "benchmark"):
        assert leg in metrics
        for key in ("cagr", "ann_vol", "sharpe", "max_drawdown"):
            assert metrics[leg][key] is not None

    # honest invariants: net <= gross, basket Sharpe > benchmark Sharpe (CSI300)
    assert metrics["net"]["cagr"] <= metrics["gross"]["cagr"]
    assert metrics["net"]["sharpe"] > metrics["benchmark"]["sharpe"]

    # equity curve has the three growth-of-1 series
    curve = body["equity_curve"]
    assert len(curve) == 3
    for point in curve:
        assert set(point) == {"date", "basket_gross", "basket_net", "benchmark"}
    assert curve[-1]["basket_net"] <= curve[-1]["basket_gross"]

    # disclaimer present, honest about CSI500 marginality + research-only
    assert "样本外验证" in body["disclaimer"]
    assert "CSI500" in body["disclaimer"]
    assert "非投资建议" in body["disclaimer"]


def test_result_is_cached_daily(client):
    calls = client.backtest_calls
    first = client.get("/analysis/low-volatility-portfolio?universe=csi500&basket_n=50")
    assert first.status_code == 200
    assert calls["n"] == 1

    second = client.get("/analysis/low-volatility-portfolio?universe=csi500&basket_n=50")
    assert second.status_code == 200
    assert calls["n"] == 1  # served from cache, no recompute
    assert second.json() == first.json()

    # a different basket_n is a distinct cache key -> recompute
    third = client.get("/analysis/low-volatility-portfolio?universe=csi500&basket_n=30")
    assert third.status_code == 200
    assert calls["n"] == 2


def test_csi500_maps_to_000905(client):
    resp = client.get("/analysis/low-volatility-portfolio?universe=csi500")
    assert resp.status_code == 200
    assert resp.json()["index_code"] == "000905.SH"


def test_bad_universe_returns_422(client):
    resp = client.get("/analysis/low-volatility-portfolio?universe=sp500")
    assert resp.status_code == 422


def test_basket_n_below_min_returns_422(client):
    resp = client.get("/analysis/low-volatility-portfolio?basket_n=5")
    assert resp.status_code == 422


def test_basket_n_above_max_returns_422(client):
    resp = client.get("/analysis/low-volatility-portfolio?basket_n=200")
    assert resp.status_code == 422


def test_provider_unavailable_returns_502(client, monkeypatch):
    # No provider factory -> _low_vol_provider returns None -> 502 AppException.
    class _NoFactoryDM:
        provider_factory = None

    monkeypatch.setattr(analysis, "data_manager", _NoFactoryDM())
    resp = client.get("/analysis/low-volatility-portfolio?universe=csi300")
    assert resp.status_code == 502


def test_service_smoke_on_synthetic_cache(tmp_path, monkeypatch):
    """The REAL service runs end-to-end against a tiny synthetic on-disk cache.

    Proves the cache-only path (build_panel reading {sym}_px.pkl, adj from
    {sym}_adj.pkl) wires into the pure core without any network price fetch.
    """
    import numpy as np

    idx = pd.bdate_range("2018-01-01", periods=420)
    syms = [f"S{i:02d}.SH" for i in range(12)]
    for i, sym in enumerate(syms):
        rng = np.random.RandomState(100 + i)
        closes = 100 * np.exp(np.cumsum(rng.randn(len(idx)) * (0.002 + 0.0015 * i)))
        px = pd.DataFrame(
            {
                "ts_code": sym,
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": 1_000_000.0,
            },
            index=idx,
        )
        px.to_pickle(tmp_path / f"{sym}_px.pkl")
        # adj_factor flat at 1.0 -> adjusted close == close
        pd.Series(1.0, index=idx, name="adj_factor").to_pickle(tmp_path / f"{sym}_adj.pkl")

    class _Prov:
        def get_index_constituents(self, code, trade_date=None):
            return syms

        def get_suspended_symbols(self, day):
            return set()

        def get_historical_data(self, *a, **k):  # must NOT be called (price cache hit)
            raise AssertionError("network price fetch attempted despite cache")

        def get_financial_indicators(self, *a, **k):
            return pd.DataFrame()  # no fundamentals needed for the vol backtest

        def get_moneyflow(self, *a, **k):
            return pd.DataFrame()

        def reset_throttle(self):
            pass

    result = low_vol_portfolio_service.run_low_vol_portfolio_from_cache(
        _Prov(), "000300.SH", basket_n=3, cache_dir=tmp_path, sample_freq_days=200
    )
    assert result["n_periods"] > 0
    assert result["metrics"]["net"]["cagr"] is not None
    # net is never above gross
    assert result["metrics"]["net"]["cagr"] <= result["metrics"]["gross"]["cagr"] + 1e-9
