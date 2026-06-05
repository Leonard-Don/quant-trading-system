"""Cache + per-minute backoff behavior for :class:`TushareProvider`.

Rapid repeated reads (行业详情) used to hammer Tushare's per-minute limit and
silently degrade to the slow AKShare scrape. These tests pin the new
client-side TTL cache and the sliding-window throttle that protect the hot read
paths. No live network — the Tushare pro client is mocked, and pytest-socket
blocks sockets via the repo's pytest addopts.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest

from src.data.providers.tushare_provider import TushareProvider


class _FakeClock:
    """Deterministic, injectable monotonic clock for cache/throttle tests."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _CountingPro:
    """Fake Tushare pro client that records how often each endpoint is hit."""

    def __init__(self):
        self.daily_basic_calls = 0
        self.fina_indicator_calls = 0
        self.daily_calls = 0

    def daily_basic(self, **kwargs):
        self.daily_basic_calls += 1
        ts_code = kwargs.get("ts_code", "600519.SH")
        return pd.DataFrame(
            [
                {
                    "ts_code": ts_code,
                    "trade_date": "20240103",
                    "pe_ttm": 28.5,
                    "pb": 9.2,
                    "turnover_rate": 0.45,
                    "total_mv": 211000000.0,
                }
            ]
        )

    def fina_indicator(self, **kwargs):
        self.fina_indicator_calls += 1
        ts_code = kwargs.get("ts_code", "600519.SH")
        return pd.DataFrame(
            [{"ts_code": ts_code, "end_date": "20231231", "roe": 31.2, "or_yoy": 18.0, "netprofit_yoy": 19.5}]
        )

    def daily(self, **kwargs):
        self.daily_calls += 1
        ts_code = kwargs.get("ts_code", "000001.SZ")
        return pd.DataFrame(
            [
                {
                    "ts_code": ts_code,
                    "trade_date": "20240103",
                    "open": 10.0,
                    "high": 10.8,
                    "low": 9.9,
                    "close": 10.5,
                    "pct_chg": 2.0,
                    "vol": 1234.0,
                    "amount": 56789.0,
                }
            ]
        )


@pytest.fixture(autouse=True)
def _isolate_tushare(monkeypatch):
    """Token isolation: blank the env token and reset class-level state.

    Without this, the real (valid) token leaks in and the rate-limited /
    fallback tests go flaky. There is no class-level circuit breaker on
    TushareProvider today, but we defensively clear any cache/throttle class
    attributes if a future refactor introduces them.
    """
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TS_TOKEN", raising=False)
    for attr in ("_class_cache", "_class_rate_limiter"):
        if hasattr(TushareProvider, attr):
            obj = getattr(TushareProvider, attr)
            if hasattr(obj, "clear"):
                obj.clear()
    yield


def _make_provider(pro, clock, *, cache_ttl=None, rate_limit=None):
    config = {"pro_client": pro, "clock": clock}
    if cache_ttl is not None:
        config["cache_ttl"] = cache_ttl
    if rate_limit is not None:
        config["rate_limit"] = rate_limit
    return TushareProvider(api_key="token", config=config)


# ---------------------------------------------------------------------------
# (a) second identical call within TTL does NOT hit the underlying API
# ---------------------------------------------------------------------------
def test_valuation_second_call_within_ttl_is_served_from_cache():
    pro = _CountingPro()
    clock = _FakeClock()
    provider = _make_provider(pro, clock)

    first = provider.get_stock_valuation("600519")
    second = provider.get_stock_valuation("600519")

    assert pro.daily_basic_calls == 1  # 2nd call served from cache
    assert first == second
    assert "error" not in first


def test_financial_second_call_within_ttl_is_served_from_cache():
    pro = _CountingPro()
    clock = _FakeClock()
    provider = _make_provider(pro, clock)

    first = provider.get_stock_financial_data("600519")
    second = provider.get_stock_financial_data("600519")

    assert pro.fina_indicator_calls == 1
    assert first == second


def test_quote_second_call_within_ttl_is_served_from_cache():
    pro = _CountingPro()
    clock = _FakeClock()
    provider = _make_provider(pro, clock)

    provider.get_latest_quote("000001")
    provider.get_latest_quote("000001")

    # get_latest_quote funnels through get_historical_data -> pro.daily once.
    assert pro.daily_calls == 1


def test_historical_second_call_within_ttl_is_served_from_cache():
    pro = _CountingPro()
    clock = _FakeClock()
    provider = _make_provider(pro, clock)

    provider.get_historical_data("000001", interval="1d")
    provider.get_historical_data("000001", interval="1d")

    assert pro.daily_calls == 1


def test_cache_key_separates_distinct_symbols():
    pro = _CountingPro()
    clock = _FakeClock()
    provider = _make_provider(pro, clock)

    provider.get_stock_valuation("600519")
    provider.get_stock_valuation("000001")

    assert pro.daily_basic_calls == 2  # different symbols are distinct keys


# ---------------------------------------------------------------------------
# (b) cache expires after TTL
# ---------------------------------------------------------------------------
def test_valuation_cache_expires_after_ttl():
    pro = _CountingPro()
    clock = _FakeClock()
    provider = _make_provider(pro, clock, cache_ttl=30)

    provider.get_stock_valuation("600519")
    clock.advance(31)  # past the 30s TTL
    provider.get_stock_valuation("600519")

    assert pro.daily_basic_calls == 2


def test_cache_ttl_zero_disables_caching():
    pro = _CountingPro()
    clock = _FakeClock()
    provider = _make_provider(pro, clock, cache_ttl=0)

    provider.get_stock_valuation("600519")
    provider.get_stock_valuation("600519")

    assert pro.daily_basic_calls == 2  # TTL=0 -> never cached, fully deterministic


def test_clear_cache_forces_refetch():
    pro = _CountingPro()
    clock = _FakeClock()
    provider = _make_provider(pro, clock)

    provider.get_stock_valuation("600519")
    provider.clear_cache()
    provider.get_stock_valuation("600519")

    assert pro.daily_basic_calls == 2


def test_miss_behavior_matches_uncached_shape():
    """Cache MISS must return exactly what the un-cached path returned."""
    pro = _CountingPro()
    clock = _FakeClock()
    provider = _make_provider(pro, clock, cache_ttl=0)

    val = provider.get_stock_valuation("600519")
    assert val["pe_ttm"] == 28.5
    assert val["pb"] == 9.2
    assert val["turnover"] == 0.45
    assert val["market_cap"] == 211000000.0 * 10000
    assert val["source"] == "tushare"


# ---------------------------------------------------------------------------
# (c) throttle prevents exceeding the per-minute rate
# ---------------------------------------------------------------------------
def test_throttle_short_circuits_when_per_minute_rate_exceeded():
    pro = _CountingPro()
    clock = _FakeClock()
    # rate_limit=3 within a 60s window; caching off so every call is a request.
    provider = _make_provider(pro, clock, cache_ttl=0, rate_limit=3)

    symbols = ["600519", "600520", "600521", "600522", "600523"]
    results = [provider.get_stock_valuation(s) for s in symbols]

    # Only the first 3 reach the underlying client; the rest are short-circuited.
    assert pro.daily_basic_calls == 3
    assert all("error" not in r for r in results[:3])
    # Short-circuited calls degrade gracefully (error dict), they do NOT raise.
    assert all("error" in r for r in results[3:])
    assert all(r["source"] == "tushare" for r in results)


def test_throttle_window_resets_after_a_minute():
    pro = _CountingPro()
    clock = _FakeClock()
    provider = _make_provider(pro, clock, cache_ttl=0, rate_limit=2)

    provider.get_stock_valuation("600519")
    provider.get_stock_valuation("600520")
    blocked = provider.get_stock_valuation("600521")
    assert "error" in blocked
    assert pro.daily_basic_calls == 2

    clock.advance(61)  # slide past the 60s window
    provider.get_stock_valuation("600522")
    assert pro.daily_basic_calls == 3


def test_throttle_does_not_raise_into_historical_callers():
    pro = _CountingPro()
    clock = _FakeClock()
    provider = _make_provider(pro, clock, cache_ttl=0, rate_limit=1)

    provider.get_historical_data("000001", interval="1d")
    # Second call is throttled; must degrade to empty frame, not raise.
    frame = provider.get_historical_data("000002", interval="1d")

    assert isinstance(frame, pd.DataFrame)
    assert frame.empty
    assert pro.daily_calls == 1


def test_cache_hit_does_not_consume_a_rate_token():
    pro = _CountingPro()
    clock = _FakeClock()
    # Cache ON, tight rate limit. A cached read must not burn a token.
    provider = _make_provider(pro, clock, cache_ttl=60, rate_limit=1)

    first = provider.get_stock_valuation("600519")
    second = provider.get_stock_valuation("600519")  # cache hit, no token used

    assert pro.daily_basic_calls == 1
    assert first == second
    assert "error" not in second


def test_rate_limit_defaults_to_class_attribute():
    """When no override is given, the throttle honors the class rate_limit."""
    pro = _CountingPro()
    clock = _FakeClock()
    provider = _make_provider(pro, clock, cache_ttl=0)

    # Default class rate_limit is 200; a handful of calls must all pass.
    for s in ("600519", "600520", "600521", "600522"):
        assert "error" not in provider.get_stock_valuation(s)
    assert pro.daily_basic_calls == 4


def test_token_isolation_no_env_token_leaks():
    """Sanity: the isolation fixture really blanked the token."""
    assert not os.getenv("TUSHARE_TOKEN")
    assert not os.getenv("TS_TOKEN")
