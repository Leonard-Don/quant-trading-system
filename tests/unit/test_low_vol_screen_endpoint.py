"""Endpoint tests for ``GET /analysis/low-volatility-screen``.

Fully mocked — no network. A fake Tushare provider supplies constituents +
names; a fake DataManager supplies per-symbol price frames. Asserts ranking
order, the honest disclaimer, daily caching, and query-param validation.
"""

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import analysis
from backend.app.core.error_handler import register_exception_handlers
from src.utils.cache import cache_manager


def _frame(closes):
    dates = pd.bdate_range("2023-06-01", periods=len(closes))
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


# Three names with clearly different realized vol. CALM < MID < WILD.
_PRICES = {
    "111111.SH": _frame(list(np.linspace(10.0, 10.5, 80))),  # CALM
    "222222.SH": _frame(list(10 + np.cumsum(np.random.RandomState(1).randn(80) * 0.05))),  # MID
    "333333.SZ": _frame(list(10 + np.sin(np.arange(80)) * 3)),  # WILD
}
_NAMES = pd.DataFrame(
    {
        "ts_code": ["111111.SH", "222222.SH", "333333.SZ"],
        "name": ["平静股", "中波股", "狂野股"],
    }
)


class _FakeProvider:
    def __init__(self):
        self.constituent_calls = 0

    def get_index_constituents(self, code, trade_date=None):
        self.constituent_calls += 1
        assert code in ("000300.SH", "000905.SH")
        return list(_PRICES.keys())

    def get_stock_basic(self, *, list_status="L"):
        return _NAMES


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
        self.fetch_calls = 0

    def get_historical_data(self, *, symbol, start_date=None, end_date=None, interval="1d"):
        self.fetch_calls += 1
        return _PRICES[symbol]


@pytest.fixture
def client(monkeypatch):
    fake = _FakeDataManager()
    monkeypatch.setattr(analysis, "data_manager", fake)
    cache_manager.clear()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(analysis.router, prefix="/analysis")
    test_client = TestClient(app)
    test_client.fake_dm = fake  # type: ignore[attr-defined]
    return test_client


def test_ranks_ascending_by_vol_with_names_and_disclaimer(client):
    resp = client.get("/analysis/low-volatility-screen?universe=csi300&top=30&window=60")
    assert resp.status_code == 200
    body = resp.json()

    assert body["universe"] == "csi300"
    assert body["window"] == 60
    assert body["count"] == 3
    assert "as_of" in body

    items = body["items"]
    # ascending realized_vol, ranks 1..3
    assert [i["symbol"] for i in items] == ["111111.SH", "222222.SH", "333333.SZ"]
    assert [i["rank"] for i in items] == [1, 2, 3]
    vols = [i["realized_vol"] for i in items]
    assert vols == sorted(vols)
    # names resolved + annualized vol + recent_return present
    assert items[0]["name"] == "平静股"
    assert items[0]["annualized_vol"] > items[0]["realized_vol"]
    assert "recent_return" in items[0]

    # honest disclaimer present with the OOS evidence
    assert "样本外验证" in body["disclaimer"]
    assert "lowvol-confirmation.md" in body["disclaimer"]
    assert "非投资建议" in body["disclaimer"]


def test_result_is_cached_daily(client):
    fake = client.fake_dm
    first = client.get("/analysis/low-volatility-screen?universe=csi500&top=10&window=60")
    assert first.status_code == 200
    calls_after_first = fake.fetch_calls
    assert calls_after_first > 0
    constituents_after_first = fake.provider.constituent_calls

    # second identical request must hit cache — no extra fetches
    second = client.get("/analysis/low-volatility-screen?universe=csi500&top=10&window=60")
    assert second.status_code == 200
    assert fake.fetch_calls == calls_after_first
    assert fake.provider.constituent_calls == constituents_after_first
    assert second.json() == first.json()


def test_csi500_maps_to_000905(client):
    resp = client.get("/analysis/low-volatility-screen?universe=csi500")
    assert resp.status_code == 200
    assert resp.json()["universe"] == "csi500"


def test_bad_universe_returns_422(client):
    resp = client.get("/analysis/low-volatility-screen?universe=sp500")
    assert resp.status_code == 422


def test_top_cap_enforced_returns_422(client):
    resp = client.get("/analysis/low-volatility-screen?top=101")
    assert resp.status_code == 422


def test_top_below_one_returns_422(client):
    resp = client.get("/analysis/low-volatility-screen?top=0")
    assert resp.status_code == 422


def test_partial_fetch_still_ranks_available(client, monkeypatch):
    # One symbol's fetch fails — the screen ranks the remaining two.
    fake = client.fake_dm

    def flaky(*, symbol, start_date=None, end_date=None, interval="1d"):
        if symbol == "333333.SZ":
            raise RuntimeError("provider hiccup")
        return _PRICES[symbol]

    monkeypatch.setattr(fake, "get_historical_data", flaky)
    resp = client.get("/analysis/low-volatility-screen?universe=csi300&window=60")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert [i["symbol"] for i in body["items"]] == ["111111.SH", "222222.SH"]


def test_window_validated_flag_is_honest(client):
    # Only window=60 (lookback) at the 20d horizon was validated. Any other
    # window must be flagged so the output can't borrow the validated framing.
    ok = client.get("/analysis/low-volatility-screen?universe=csi300&window=60").json()
    assert ok["window_validated"] is True
    assert "⚠️" not in ok["disclaimer"]

    other = client.get("/analysis/low-volatility-screen?universe=csi300&window=120").json()
    assert other["window_validated"] is False
    assert "未经验证" in other["disclaimer"]
