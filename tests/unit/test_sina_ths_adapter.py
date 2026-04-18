import json
import time
from unittest.mock import MagicMock, patch

import pandas as pd

from src.data.providers.sina_provider import SinaFinanceProvider
from src.data.providers.sina_ths_adapter import SinaIndustryAdapter


def test_attach_industry_codes_before_market_cap_fallback():
    adapter = SinaIndustryAdapter()
    SinaIndustryAdapter._ths_catalog_shared_cache = pd.DataFrame(
        [
            {"industry_name": "半导体及元件", "industry_code": "881121"},
            {"industry_name": "软件开发", "industry_code": "881122"},
        ]
    )
    SinaIndustryAdapter._ths_catalog_shared_cache_time = 10**12

    ths_df = pd.DataFrame(
        [
            {"行业": "半导体及元件", "industry_name": "半导体及元件", "净额": 1, "流入": 10, "流出": 5},
            {"行业": "软件开发", "industry_name": "软件开发", "净额": 2, "流入": 8, "流出": 4},
        ]
    )

    result = adapter._process_ths_raw_data(ths_df)

    assert "industry_code" in result.columns
    assert result["industry_code"].tolist() == ["881121", "881122"]


def test_compute_industry_market_caps_fetches_all_pages():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter._resolve_sina_industry_code = MagicMock(return_value="new_test")
    adapter.sina.get_industry_stocks.return_value = (
        [{"code": f"{i:06d}", "mktcap": 1} for i in range(1, 51)]
        + [{"code": "000003", "mktcap": 30}]
    )

    df = pd.DataFrame(
        [{"industry_name": "半导体及元件", "industry_code": "new_test"}]
    )

    adapter._compute_industry_market_caps(df)

    assert df["total_market_cap"].iloc[0] == (50 + 30) * 10000
    adapter.sina.get_industry_stocks.assert_called_once_with(
        "new_test", page=1, count=50, fetch_all=True
    )


def test_resolve_sina_industry_code_uses_sina_node_code():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.return_value = pd.DataFrame(
        [
            {"industry_name": "医疗器械", "industry_code": "new_ylqx"},
            {"industry_name": "白酒", "industry_code": "new_bj"},
        ]
    )

    assert adapter._resolve_sina_industry_code("白酒", "881125") == "new_bj"


def test_resolve_sina_industry_code_prefers_cached_new_node_over_hangye_fallback():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.return_value = pd.DataFrame(
        [
            {"industry_name": "电力行业", "industry_code": "hangye_ZD44"},
        ]
    )

    with patch.object(SinaIndustryAdapter, "_get_cached_sina_stock_nodes", return_value={"new_dlhy"}):
        assert adapter._resolve_sina_industry_code("电力", "881145") == "new_dlhy"


def test_resolve_sina_industry_code_avoids_overbroad_cached_alias():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.return_value = pd.DataFrame()

    with patch.object(SinaIndustryAdapter, "_get_cached_sina_stock_nodes", return_value={"new_ylqx"}):
        assert adapter._resolve_sina_industry_code("医疗服务", "881160") is None


def test_resolve_sina_industry_code_avoids_overbroad_live_new_node_match():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.return_value = pd.DataFrame(
        [
            {"industry_name": "生物制药", "industry_code": "new_swzz"},
        ]
    )

    with patch.object(SinaIndustryAdapter, "_get_cached_sina_stock_nodes", return_value={"new_swzz"}):
        assert adapter._resolve_sina_industry_code("医疗服务", "881160") is None


def test_resolve_sina_industry_code_uses_cached_new_node_for_logistics_family():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.return_value = pd.DataFrame(
        [
            {"industry_name": "物流", "industry_code": "hangye_ZG59"},
        ]
    )

    with patch.object(SinaIndustryAdapter, "_get_cached_sina_stock_nodes", return_value={"new_wzwm"}):
        assert adapter._resolve_sina_industry_code("物流", "881159") == "new_wzwm"


def test_resolve_sina_industry_node_marks_proxy_source():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.return_value = pd.DataFrame()

    with patch.object(SinaIndustryAdapter, "_get_cached_sina_stock_nodes", return_value={"new_dzqj"}):
        assert adapter._resolve_sina_industry_node("半导体", "881121") == ("new_dzqj", "sina_proxy_stock_sum")


def test_get_cached_stock_list_by_industry_uses_persistent_proxy_snapshot():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina._load_persistent_industry_stocks.side_effect = lambda code: [
        {
            "code": "688981",
            "name": "中芯国际",
            "change_pct": 1.8,
            "mktcap": 42000000,
            "volume": 100,
            "amount": 200,
            "pe_ratio": 52.7,
            "pb_ratio": 3.1,
        }
    ] if code == "new_dzqj" else []

    with patch.object(SinaIndustryAdapter, "_get_cached_sina_stock_nodes", return_value={"new_dzqj"}):
        with patch.object(SinaFinanceProvider, "_load_persistent_industry_list", return_value=pd.DataFrame()):
            stocks = adapter.get_cached_stock_list_by_industry("半导体")

    assert len(stocks) == 1
    assert stocks[0]["symbol"] == "688981"
    assert stocks[0]["market_cap"] == 42000000 * 10000
    assert stocks[0]["pe_ratio"] == 52.7


def test_compute_industry_market_caps_marks_standard_sina_source():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter._resolve_sina_industry_node = MagicMock(return_value=("new_test", "sina_stock_sum"))
    adapter.sina.get_industry_stocks.return_value = [
        {"code": "000001", "mktcap": 100},
        {"code": "000002", "mktcap": 200},
    ]

    df = pd.DataFrame([{"industry_name": "白酒", "industry_code": "881125"}])

    adapter._compute_industry_market_caps(df)

    assert df["total_market_cap"].iloc[0] == 300 * 10000
    assert df["market_cap_source"].iloc[0] == "sina_stock_sum"


def test_compute_industry_market_caps_marks_proxy_source():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.akshare = MagicMock()
    adapter._resolve_sina_industry_node = MagicMock(return_value=("new_dzqj", "sina_proxy_stock_sum"))
    adapter.sina.get_industry_stocks.return_value = [
        {"code": "688981", "mktcap": 100},
        {"code": "603986", "mktcap": 200},
    ]
    adapter.akshare.get_stock_list_by_industry.return_value = []

    df = pd.DataFrame([{"industry_name": "半导体", "industry_code": "881121"}])

    adapter._compute_industry_market_caps(df)

    assert df["total_market_cap"].iloc[0] == 300 * 10000
    assert df["market_cap_source"].iloc[0] == "sina_proxy_stock_sum"


def test_persist_market_cap_snapshot_merges_real_entries(tmp_path):
    adapter = SinaIndustryAdapter()
    original_path = SinaIndustryAdapter._industry_market_cap_snapshot_path
    SinaIndustryAdapter._industry_market_cap_snapshot_path = tmp_path / "industry_market_cap_snapshot.json"
    try:
        adapter._persist_market_cap_snapshot(
            pd.DataFrame(
                [
                    {"industry_name": "电力", "industry_code": "881145", "total_market_cap": 2e12, "market_cap_source": "akshare_metadata"},
                    {"industry_name": "食品加工制造", "industry_code": "881127", "total_market_cap": 5e11, "market_cap_source": "sina_stock_sum"},
                    {"industry_name": "未知行业", "industry_code": "999999", "total_market_cap": 1.0, "market_cap_source": "estimated_from_flow"},
                ]
            )
        )
        payload = json.loads(SinaIndustryAdapter._industry_market_cap_snapshot_path.read_text(encoding="utf-8"))
    finally:
        SinaIndustryAdapter._industry_market_cap_snapshot_path = original_path

    assert sorted(payload["data"].keys()) == ["881127", "881145"]


def test_persist_market_cap_snapshot_preserves_existing_entries(tmp_path):
    adapter = SinaIndustryAdapter()
    snapshot_path = tmp_path / "industry_market_cap_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "updated_at": 123.0,
                "data": {
                    "881145": {
                        "industry_name": "电力",
                        "total_market_cap": 2450000000000.0,
                        "market_cap_source": "akshare_metadata",
                        "updated_at": 123.0,
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    original_path = SinaIndustryAdapter._industry_market_cap_snapshot_path
    SinaIndustryAdapter._industry_market_cap_snapshot_path = snapshot_path
    try:
        adapter._persist_market_cap_snapshot(
            pd.DataFrame(
                [
                    {"industry_name": "食品加工制造", "industry_code": "881127", "total_market_cap": 5e11, "market_cap_source": "sina_stock_sum"},
                ]
            )
        )
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    finally:
        SinaIndustryAdapter._industry_market_cap_snapshot_path = original_path

    assert sorted(payload["data"].keys()) == ["881127", "881145"]


def test_apply_persistent_market_cap_snapshot_fills_missing_caps(tmp_path):
    adapter = SinaIndustryAdapter()
    snapshot_path = tmp_path / "industry_market_cap_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "updated_at": 123.0,
                "data": {
                    "881145": {
                        "industry_name": "电力",
                        "total_market_cap": 2450000000000.0,
                        "market_cap_source": "akshare_metadata",
                        "updated_at": 123.0,
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    original_path = SinaIndustryAdapter._industry_market_cap_snapshot_path
    SinaIndustryAdapter._industry_market_cap_snapshot_path = snapshot_path
    try:
        df = pd.DataFrame(
            [
                {"industry_name": "电力", "industry_code": "881145", "total_market_cap": 0.0, "market_cap_source": "unknown", "data_sources": ["ths"]},
            ]
        )
        assert adapter._apply_persistent_market_cap_snapshot(df) is True
    finally:
        SinaIndustryAdapter._industry_market_cap_snapshot_path = original_path

    assert df["total_market_cap"].iloc[0] == 2450000000000.0
    assert df["market_cap_source"].iloc[0] == "snapshot_akshare_metadata"
    assert "snapshot" in df["data_sources"].iloc[0]


def test_apply_persistent_market_cap_snapshot_marks_stale_age(tmp_path):
    adapter = SinaIndustryAdapter()
    snapshot_path = tmp_path / "industry_market_cap_snapshot.json"
    stale_hours = SinaIndustryAdapter._market_cap_snapshot_stale_after_hours + 2
    snapshot_path.write_text(
        json.dumps(
            {
                "updated_at": 123.0,
                "data": {
                    "881145": {
                        "industry_name": "电力",
                        "total_market_cap": 2450000000000.0,
                        "market_cap_source": "akshare_metadata",
                        "updated_at": __import__("time").time() - stale_hours * 3600,
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    original_path = SinaIndustryAdapter._industry_market_cap_snapshot_path
    SinaIndustryAdapter._industry_market_cap_snapshot_path = snapshot_path
    try:
        df = pd.DataFrame(
            [
                {"industry_name": "电力", "industry_code": "881145", "total_market_cap": 0.0, "market_cap_source": "unknown", "data_sources": ["ths"]},
            ]
        )
        adapter._apply_persistent_market_cap_snapshot(df)
    finally:
        SinaIndustryAdapter._industry_market_cap_snapshot_path = original_path

    assert df["market_cap_snapshot_age_hours"].iloc[0] >= stale_hours - 0.1
    assert bool(df["market_cap_snapshot_is_stale"].iloc[0]) is True


def test_get_persistent_market_cap_snapshot_status_counts_stale_entries(tmp_path):
    snapshot_path = tmp_path / "industry_market_cap_snapshot.json"
    now = time.time()
    snapshot_path.write_text(
        json.dumps(
            {
                "updated_at": now,
                "data": {
                    "881145": {
                        "industry_name": "电力",
                        "total_market_cap": 2450000000000.0,
                        "market_cap_source": "akshare_metadata",
                        "updated_at": now - 2 * 3600,
                    },
                    "881127": {
                        "industry_name": "食品加工制造",
                        "total_market_cap": 5e11,
                        "market_cap_source": "sina_stock_sum",
                        "updated_at": now - (SinaIndustryAdapter._market_cap_snapshot_stale_after_hours + 3) * 3600,
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    original_path = SinaIndustryAdapter._industry_market_cap_snapshot_path
    SinaIndustryAdapter._industry_market_cap_snapshot_path = snapshot_path
    try:
        status = SinaIndustryAdapter.get_persistent_market_cap_snapshot_status()
    finally:
        SinaIndustryAdapter._industry_market_cap_snapshot_path = original_path

    assert status["entries"] == 2
    assert status["fresh_entries"] == 1
    assert status["stale_entries"] == 1
    assert status["max_age_hours"] >= SinaIndustryAdapter._market_cap_snapshot_stale_after_hours + 2.9
    assert status["source_counts"] == {"akshare_metadata": 1, "sina_stock_sum": 1}


def test_enrich_with_akshare_uses_precise_join_keys():
    adapter = SinaIndustryAdapter()
    adapter.get_symbol_by_name = MagicMock(return_value="")
    SinaIndustryAdapter._akshare_valuation_snapshot_cache = None
    SinaIndustryAdapter._akshare_valuation_snapshot_cache_time = 0
    SinaIndustryAdapter._akshare_valuation_snapshot_failure_at = 0

    source_df = pd.DataFrame(
        [{"industry_name": "房地产开发", "leading_stock": "万科A"}]
    )
    meta_df = pd.DataFrame(
        [
            {"industry_name": "房地产服务", "total_market_cap": 999, "turnover_rate": 8.8, "market_cap_source": "akshare_metadata"},
        ]
    )
    valuation_df = pd.DataFrame(
        [{"行业名称": "房地产服务", "TTM(滚动)市盈率": 22.2, "市净率": 1.5, "静态股息率": 0.8}]
    )

    with patch("src.data.providers.akshare_provider.AKShareProvider._get_industry_metadata", return_value=meta_df), patch(
        "src.data.providers.sina_ths_adapter.ak.sw_index_first_info",
        return_value=valuation_df,
    ):
        enriched = adapter._enrich_with_akshare(source_df.copy())

    assert pd.isna(enriched["total_market_cap"].iloc[0])
    assert pd.isna(enriched["pe_ttm"].iloc[0])


def test_enrich_with_akshare_marks_sources_when_matched():
    adapter = SinaIndustryAdapter()
    adapter.get_symbol_by_name = MagicMock(return_value="")
    SinaIndustryAdapter._akshare_valuation_snapshot_cache = None
    SinaIndustryAdapter._akshare_valuation_snapshot_cache_time = 0
    SinaIndustryAdapter._akshare_valuation_snapshot_failure_at = 0
    source_df = pd.DataFrame([{"industry_name": "白酒", "leading_stock": "贵州茅台"}])
    meta_df = pd.DataFrame([{"industry_name": "白酒", "total_market_cap": 123.0, "turnover_rate": 2.5, "market_cap_source": "akshare_metadata"}])
    valuation_df = pd.DataFrame([{"行业名称": "白酒", "TTM(滚动)市盈率": 18.8, "市净率": 3.2, "静态股息率": 1.1}])

    with patch("src.data.providers.akshare_provider.AKShareProvider._get_industry_metadata", return_value=meta_df), patch(
        "src.data.providers.sina_ths_adapter.ak.sw_index_first_info",
        return_value=valuation_df,
    ):
        enriched = adapter._enrich_with_akshare(source_df.copy())

    assert enriched["market_cap_source"].iloc[0] == "akshare_metadata"
    assert enriched["valuation_source"].iloc[0] == "akshare_sw"
    assert enriched["valuation_quality"].iloc[0] == "industry_level"
    assert "akshare" in enriched["data_sources"].iloc[0]


def test_ensure_flow_strength_rebuilds_from_main_net_ratio():
    adapter = SinaIndustryAdapter()
    df = pd.DataFrame(
        [
            {"industry_name": "电子", "main_net_inflow": 5_000_000_000, "main_net_ratio": 5.0, "flow_strength": 0.0},
            {"industry_name": "医药生物", "main_net_inflow": 3_000_000_000, "main_net_ratio": 3.0, "flow_strength": 0.0},
            {"industry_name": "计算机", "main_net_inflow": -1_000_000_000, "main_net_ratio": -1.0, "flow_strength": 0.0},
        ]
    )

    adapter._ensure_flow_strength(df)

    assert df["flow_strength"].tolist() == [0.05, 0.03, -0.01]


def test_sina_provider_fetch_all_pages_merges_results(tmp_path):
    provider = SinaFinanceProvider()
    responses = [
        '[{"code":"000001","symbol":"sz000001","name":"平安银行","mktcap":"10","volume":"1","amount":"2"}]',
        '[{"code":"000002","symbol":"sz000002","name":"万科A","mktcap":"20","volume":"3","amount":"4"}]',
        "[]",
    ]

    class DummyResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    provider.session.get = MagicMock(side_effect=[DummyResponse(text) for text in responses])
    original_path = SinaFinanceProvider._industry_stocks_cache_path
    SinaFinanceProvider._industry_stocks_cache_path = tmp_path / "sina_industry_stocks_cache.json"
    try:
        result = provider.get_industry_stocks("new_test", count=1, fetch_all=True)
    finally:
        SinaFinanceProvider._industry_stocks_cache_path = original_path

    assert [item["code"] for item in result] == ["000001", "000002"]
    assert provider.session.get.call_count == 3


def test_normalize_to_ths_industry_name_prefers_unique_safe_match():
    adapter = SinaIndustryAdapter()
    SinaIndustryAdapter._ths_catalog_shared_cache = pd.DataFrame(
        [
            {"industry_name": "白色家电", "industry_code": "881001"},
            {"industry_name": "小家电", "industry_code": "881002"},
        ]
    )
    SinaIndustryAdapter._ths_catalog_shared_cache_time = 10**12

    assert adapter._normalize_to_ths_industry_name("电器行业") == "白色家电"


def test_normalize_to_ths_industry_name_avoids_ambiguous_fuzzy_match():
    adapter = SinaIndustryAdapter()
    SinaIndustryAdapter._ths_catalog_shared_cache = pd.DataFrame(
        [
            {"industry_name": "房地产开发", "industry_code": "881101"},
            {"industry_name": "房地产服务", "industry_code": "881102"},
        ]
    )
    SinaIndustryAdapter._ths_catalog_shared_cache_time = 10**12

    assert adapter._normalize_to_ths_industry_name("房地产") == "房地产"


def test_normalize_to_ths_industry_name_does_not_collapse_broad_industry_to_subsector():
    adapter = SinaIndustryAdapter()
    SinaIndustryAdapter._ths_catalog_shared_cache = pd.DataFrame(
        [
            {"industry_name": "医疗器械", "industry_code": "881201"},
            {"industry_name": "化学制药", "industry_code": "881202"},
            {"industry_name": "中药", "industry_code": "881203"},
        ]
    )
    SinaIndustryAdapter._ths_catalog_shared_cache_time = 10**12

    assert adapter._normalize_to_ths_industry_name("医药生物") == "医药生物"
