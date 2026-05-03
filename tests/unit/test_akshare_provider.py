import json
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import patch

import pandas as pd
import pytest

from src.data.providers.akshare_provider import AKShareProvider
from src.data.providers.circuit_breaker import CircuitOpenError, CircuitState


def test_get_industry_metadata_persists_snapshot(tmp_path):
    provider = AKShareProvider()
    provider._industry_meta_cache = None
    provider._industry_meta_cache_time = None

    cache_path = tmp_path / "industry_metadata_cache.json"
    raw_df = pd.DataFrame(
        [
            {"板块名称": "白酒Ⅱ", "总市值": 123.0, "换手率": 2.5, "涨跌幅": 1.2},
            {"板块名称": "证券Ⅱ", "总市值": 456.0, "换手率": 3.1, "涨跌幅": -0.3},
        ]
    )

    with (
        patch.object(AKShareProvider, "_industry_meta_cache_path", cache_path),
        patch(
            "src.data.providers.akshare_provider.ak.stock_board_industry_name_em",
            return_value=raw_df,
        ),
    ):
        df = provider._get_industry_metadata()

    assert not df.empty
    assert cache_path.exists()
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["data"]
    assert "updated_at" in payload


def test_get_industry_metadata_uses_persistent_snapshot_on_failure(tmp_path):
    cache_path = tmp_path / "industry_metadata_cache.json"
    snapshot_df = pd.DataFrame(
        [
            {
                "industry_name": "白酒",
                "original_name": "白酒Ⅱ",
                "total_market_cap": 123.0,
                "turnover_rate": 2.5,
                "change_pct_meta": 1.2,
            }
        ]
    )
    cache_path.write_text(
        json.dumps(
            {
                "updated_at": datetime.now().isoformat(),
                "data": snapshot_df.to_dict(orient="records"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    provider = AKShareProvider()
    provider._industry_meta_cache = None
    provider._industry_meta_cache_time = None

    with (
        patch.object(AKShareProvider, "_industry_meta_cache_path", cache_path),
        patch(
            "src.data.providers.akshare_provider.ak.stock_board_industry_name_em",
            side_effect=RuntimeError("upstream unavailable"),
        ),
    ):
        df = provider._get_industry_metadata()

    assert not df.empty
    assert df.iloc[0]["industry_name"] == "白酒"


def test_get_stock_list_by_industry_reuses_cached_snapshot():
    provider = AKShareProvider()
    provider._industry_stock_cache = {}
    AKShareProvider._shared_industry_stock_snapshot = {}
    AKShareProvider._shared_industry_stock_snapshot_time = None

    industry_meta = pd.DataFrame(
        [
            {
                "industry_name": "白酒",
                "original_name": "白酒Ⅱ",
            }
        ]
    )
    stocks_df = pd.DataFrame(
        [
            {
                "代码": "600519",
                "名称": "贵州茅台",
                "最新价": 1666.6,
                "涨跌幅": 1.2,
                "换手率": 3.4,
                "成交量": 12345,
                "成交额": 67890,
                "总市值": 2.1e12,
                "流通市值": 2.0e12,
                "市盈率-动态": 28.5,
            }
        ]
    )

    with (
        patch.object(provider, "_get_industry_metadata", return_value=industry_meta),
        patch.object(
            provider,
            "_get_all_stocks_market_cap",
            return_value={},
        ),
        patch(
            "src.data.providers.akshare_provider.ak.stock_board_industry_cons_em",
            return_value=stocks_df,
        ) as stock_cons,
    ):
        first = provider.get_stock_list_by_industry("白酒", include_market_cap_lookup=False)
        second = provider.get_stock_list_by_industry("白酒", include_market_cap_lookup=False)

    assert stock_cons.call_count == 1
    assert first == second
    assert first[0]["symbol"] == "600519"
    assert first[0]["turnover_rate"] == 3.4


def test_get_stock_list_by_industry_prefers_persistent_snapshot_for_fast_lookup(tmp_path):
    snapshot_path = tmp_path / "industry_stock_cache.json"
    cache_key = "白酒|market_cap:0"
    snapshot_payload = {
        "updated_at": datetime.now().isoformat(),
        "data": {
            cache_key: {
                "updated_at": datetime.now().isoformat(),
                "stocks": [
                    {
                        "symbol": "600519",
                        "name": "贵州茅台",
                        "price": 1666.6,
                        "change_pct": 1.2,
                        "volume": 12345,
                        "amount": 67890,
                        "market_cap": 2.1e12,
                        "pe_ratio": 28.5,
                    }
                ],
            }
        },
    }
    snapshot_path.write_text(
        json.dumps(snapshot_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    provider = AKShareProvider()
    provider._industry_stock_cache = {}
    AKShareProvider._shared_industry_stock_snapshot = None
    AKShareProvider._shared_industry_stock_snapshot_time = None

    with (
        patch.object(AKShareProvider, "_industry_stock_snapshot_path", snapshot_path),
        patch(
            "src.data.providers.akshare_provider.ak.stock_board_industry_cons_em",
            side_effect=AssertionError("live industry stock fetch should not run"),
        ),
    ):
        stocks = provider.get_stock_list_by_industry("白酒", include_market_cap_lookup=False)

    assert len(stocks) == 1
    assert stocks[0]["symbol"] == "600519"


def test_get_stock_list_by_industry_dedupes_concurrent_live_fetches():
    provider = AKShareProvider()
    provider._industry_stock_cache = {}
    AKShareProvider._shared_industry_stock_snapshot = {}
    AKShareProvider._shared_industry_stock_snapshot_time = None

    industry_meta = pd.DataFrame(
        [
            {
                "industry_name": "白酒",
                "original_name": "白酒Ⅱ",
            }
        ]
    )
    stocks_df = pd.DataFrame(
        [
            {
                "代码": "600519",
                "名称": "贵州茅台",
                "最新价": 1666.6,
                "涨跌幅": 1.2,
                "换手率": 3.4,
                "成交量": 12345,
                "成交额": 67890,
                "总市值": 2.1e12,
                "流通市值": 2.0e12,
                "市盈率-动态": 28.5,
            }
        ]
    )
    gate = threading.Event()
    started = threading.Event()
    call_count = 0
    call_count_lock = threading.Lock()

    def _slow_stock_fetch(symbol):
        nonlocal call_count
        with call_count_lock:
            call_count += 1
        started.set()
        gate.wait(timeout=1)
        return stocks_df

    with (
        patch.object(provider, "_get_industry_metadata", return_value=industry_meta),
        patch.object(
            provider,
            "_get_all_stocks_market_cap",
            return_value={},
        ),
        patch(
            "src.data.providers.akshare_provider.ak.stock_board_industry_cons_em",
            side_effect=_slow_stock_fetch,
        ),
    ):
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_one = executor.submit(provider.get_stock_list_by_industry, "白酒", False)
            assert started.wait(timeout=1)
            future_two = executor.submit(provider.get_stock_list_by_industry, "白酒", False)
            gate.set()
            first = future_one.result(timeout=1)
            second = future_two.result(timeout=1)

    assert call_count == 1
    assert first == second
    assert first[0]["symbol"] == "600519"
    assert first[0]["turnover_rate"] == 3.4


def test_persist_stock_list_snapshot_skips_disk_write_when_snapshot_unchanged(tmp_path):
    snapshot_path = tmp_path / "industry_stock_cache.json"
    cache_key = "白酒|market_cap:0"
    stocks = [
        {
            "symbol": "600519",
            "name": "贵州茅台",
            "price": 1666.6,
            "change_pct": 1.2,
            "volume": 12345,
            "amount": 67890,
            "market_cap": 2.1e12,
            "pe_ratio": 28.5,
        }
    ]
    snapshot_path.write_text(
        json.dumps(
            {
                "updated_at": datetime.now().isoformat(),
                "data": {
                    cache_key: {
                        "updated_at": datetime.now().isoformat(),
                        "stocks": stocks,
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    provider = AKShareProvider()
    provider._industry_stock_cache = {}
    AKShareProvider._shared_industry_stock_snapshot = None
    AKShareProvider._shared_industry_stock_snapshot_time = None

    with (
        patch.object(AKShareProvider, "_industry_stock_snapshot_path", snapshot_path),
        patch.object(
            Path,
            "write_text",
            side_effect=AssertionError("unchanged stock snapshot should not be rewritten"),
        ),
    ):
        provider.persist_stock_list_snapshot("白酒", stocks, include_market_cap_lookup=False)


def test_akshare_provider_circuit_short_circuits_after_repeated_failures():
    provider = AKShareProvider()
    calls = 0

    def unstable_fetch():
        nonlocal calls
        calls += 1
        raise RuntimeError("upstream unavailable")

    for _ in range(5):
        with pytest.raises(RuntimeError):
            provider._call_akshare("unit_test_fetch", unstable_fetch)

    breaker = provider._akshare_breakers["unit_test_fetch"]
    assert breaker.state is CircuitState.OPEN

    with pytest.raises(CircuitOpenError):
        provider._call_akshare("unit_test_fetch", unstable_fetch)

    assert calls == 5
    assert provider.get_circuit_status()["unit_test_fetch"]["state"] == "open"
