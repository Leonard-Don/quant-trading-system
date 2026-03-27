from datetime import datetime

from src.data.realtime_manager import RealTimeDataManager


def test_build_quote_preserves_missing_numeric_fields():
    manager = RealTimeDataManager()
    try:
        quote = manager._build_quote(
            "TEST",
            {
                "symbol": "TEST",
                "price": None,
                "change": None,
                "change_percent": None,
                "volume": None,
                "timestamp": datetime.now().isoformat(),
            },
            default_source="test",
        )
    finally:
        manager.cleanup()

    assert quote is not None
    assert quote.price is None
    assert quote.change is None
    assert quote.change_percent is None
    assert quote.volume is None
    assert quote.source == "test"


def test_build_quote_derives_previous_close_and_percent_when_possible():
    manager = RealTimeDataManager()
    try:
        quote = manager._build_quote(
            "TEST",
            {
                "symbol": "TEST",
                "price": 105.0,
                "change": 5.0,
                "timestamp": datetime.now().isoformat(),
            },
            default_source="test",
        )
    finally:
        manager.cleanup()

    assert quote is not None
    assert quote.previous_close == 100.0
    assert round(quote.change_percent, 2) == 5.0


def test_get_quotes_dict_reuses_recent_bundle_cache():
    manager = RealTimeDataManager()
    calls = []

    def fake_fetch(symbols, use_cache=True):
        calls.append((tuple(symbols), use_cache))
        return {
            "AAPL": manager._build_quote(
                "AAPL",
                {
                    "symbol": "AAPL",
                    "price": 100.0,
                    "timestamp": datetime.now().isoformat(),
                },
                default_source="test",
            ),
            "MSFT": manager._build_quote(
                "MSFT",
                {
                    "symbol": "MSFT",
                    "price": 200.0,
                    "timestamp": datetime.now().isoformat(),
                },
                default_source="test",
            ),
        }, {"requested": 2}

    manager._fetch_real_time_data = fake_fetch
    try:
        first = manager.get_quotes_dict(["AAPL", "MSFT"], use_cache=True)
        second = manager.get_quotes_dict(["AAPL", "MSFT"], use_cache=True)
    finally:
        manager.cleanup()

    assert first == second
    assert calls == [(("AAPL", "MSFT"), True)]
    assert manager.runtime_stats["bundle_cache_hits"] == 1
    assert manager.runtime_stats["bundle_cache_writes"] >= 1


def test_store_quote_invalidates_recent_bundle_cache():
    manager = RealTimeDataManager()
    try:
        manager._store_cached_quote_bundle(
            ["AAPL"],
            {
                "AAPL": {
                    "symbol": "AAPL",
                    "price": 100.0,
                    "timestamp": datetime.now().isoformat(),
                },
            },
        )
        assert manager._get_cached_quote_bundle(["AAPL"]) is not None

        manager._store_quote(
            manager._build_quote(
                "AAPL",
                {
                    "symbol": "AAPL",
                    "price": 101.0,
                    "timestamp": datetime.now().isoformat(),
                },
                default_source="test",
            )
        )
    finally:
        manager.cleanup()

    assert manager._get_cached_quote_bundle(["AAPL"]) is None


def test_prewarm_quote_bundle_uses_cached_quotes_without_refetching():
    manager = RealTimeDataManager()
    try:
        manager._store_quote(
            manager._build_quote(
                "AAPL",
                {
                    "symbol": "AAPL",
                    "price": 101.0,
                    "timestamp": datetime.now().isoformat(),
                },
                default_source="test",
            )
        )
        manager._store_quote(
            manager._build_quote(
                "MSFT",
                {
                    "symbol": "MSFT",
                    "price": 202.0,
                    "timestamp": datetime.now().isoformat(),
                },
                default_source="test",
            )
        )

        payload = manager.prewarm_quote_bundle(["AAPL", "MSFT"])
    finally:
        manager.cleanup()

    assert payload["AAPL"]["price"] == 101.0
    assert payload["MSFT"]["price"] == 202.0


def test_update_quotes_prewarms_bundle_for_current_subscription_set():
    manager = RealTimeDataManager()
    manager.subscribed_symbols = {"AAPL", "MSFT"}

    def fake_fetch(symbols, use_cache=True):
        return {
            "AAPL": manager._build_quote(
                "AAPL",
                {
                    "symbol": "AAPL",
                    "price": 100.0,
                    "timestamp": datetime.now().isoformat(),
                },
                default_source="test",
            ),
            "MSFT": manager._build_quote(
                "MSFT",
                {
                    "symbol": "MSFT",
                    "price": 200.0,
                    "timestamp": datetime.now().isoformat(),
                },
                default_source="test",
            ),
        }, {"requested": 2, "cache_hits": 0, "fetched": 2, "misses": 0}

    manager._fetch_real_time_data = fake_fetch
    try:
        manager._update_quotes()
        bundle = manager._get_cached_quote_bundle(["AAPL", "MSFT"])
    finally:
        manager.cleanup()

    assert bundle is not None
    assert bundle["AAPL"]["price"] == 100.0
    assert bundle["MSFT"]["price"] == 200.0
    assert manager.runtime_stats["bundle_prewarm_calls"] >= 1


def test_market_summary_exposes_cache_runtime_stats():
    manager = RealTimeDataManager()
    try:
        manager.runtime_stats["bundle_cache_hits"] = 3
        manager.runtime_stats["bundle_cache_misses"] = 1
        manager.runtime_stats["bundle_cache_writes"] = 2
        manager.runtime_stats["bundle_prewarm_calls"] = 4
        manager.runtime_stats["last_fetch_stats"] = {"requested": 2, "cache_hits": 2}
        manager.runtime_stats["last_bundle_cache_key"] = ["AAPL", "MSFT"]
        manager.quote_history["AAPL"] = [
            manager._build_quote(
                "AAPL",
                {
                    "symbol": "AAPL",
                    "price": 100.0,
                    "change": 1.2,
                    "change_percent": 1.1,
                    "volume": 123,
                    "high": 101.0,
                    "low": 99.5,
                    "open": 99.8,
                    "previous_close": 98.9,
                    "bid": 99.9,
                    "ask": 100.1,
                    "timestamp": datetime.now().isoformat(),
                },
                default_source="test",
            )
        ]
        manager.quote_history["MSFT"] = [
            manager._build_quote(
                "MSFT",
                {
                    "symbol": "MSFT",
                    "price": 200.0,
                    "change": None,
                    "change_percent": None,
                    "volume": 456,
                    "high": None,
                    "low": None,
                    "open": 198.5,
                    "previous_close": 197.9,
                    "bid": None,
                    "ask": None,
                    "timestamp": datetime.now().isoformat(),
                },
                default_source="test",
            )
        ]
        summary = manager.get_market_summary()
    finally:
        manager.cleanup()

    assert summary["cache"]["bundle_cache_hits"] == 3
    assert summary["cache"]["bundle_cache_misses"] == 1
    assert summary["cache"]["bundle_cache_writes"] == 2
    assert summary["cache"]["bundle_prewarm_calls"] == 4
    assert summary["cache"]["last_fetch_stats"] == {"requested": 2, "cache_hits": 2}
    assert summary["cache"]["last_bundle_cache_key"] == ["AAPL", "MSFT"]
    assert summary["quality"]["active_quote_count"] == 2
    assert any(item["field"] == "price" and item["coverage_ratio"] == 1.0 for item in summary["quality"]["field_coverage"])
    assert any(item["field"] == "bid" and item["missing"] == 1 for item in summary["quality"]["field_coverage"])
    assert summary["quality"]["most_incomplete_symbols"][0]["symbol"] == "MSFT"
