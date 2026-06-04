import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.data.providers.circuit_breaker import CircuitOpenError, CircuitState
from src.data.providers.sina_provider import SinaFinanceProvider
from src.data.providers.sina_ths_adapter import SinaIndustryAdapter


@pytest.fixture(autouse=True)
def _disable_live_tushare_provider(monkeypatch):
    monkeypatch.setattr(
        SinaIndustryAdapter,
        "_create_tushare_provider",
        staticmethod(lambda: None),
    )


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
            {
                "行业": "半导体及元件",
                "industry_name": "半导体及元件",
                "净额": 1,
                "流入": 10,
                "流出": 5,
            },
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
    adapter.sina.get_industry_stocks.return_value = [
        {"code": f"{i:06d}", "mktcap": 1} for i in range(1, 51)
    ] + [{"code": "000003", "mktcap": 30}]

    df = pd.DataFrame([{"industry_name": "半导体及元件", "industry_code": "new_test"}])

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


def test_resolve_sina_industry_code_prefers_persistent_snapshot_before_live():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.side_effect = AssertionError(
        "live Sina industry list should not run"
    )
    original_cache = SinaIndustryAdapter._sina_industry_list_shared_cache
    original_cache_time = SinaIndustryAdapter._sina_industry_list_shared_cache_time
    SinaIndustryAdapter._sina_industry_list_shared_cache = None
    SinaIndustryAdapter._sina_industry_list_shared_cache_time = 0

    persistent_df = pd.DataFrame(
        [
            {"industry_name": "白酒", "industry_code": "new_bj"},
        ]
    )

    try:
        with patch.object(
            SinaFinanceProvider,
            "_get_persistent_industry_list_lookup",
            return_value={"白酒": persistent_df.to_dict(orient="records")},
        ):
            assert adapter._resolve_sina_industry_code("白酒", "881125") == "new_bj"
    finally:
        SinaIndustryAdapter._sina_industry_list_shared_cache = original_cache
        SinaIndustryAdapter._sina_industry_list_shared_cache_time = original_cache_time


def test_resolve_sina_industry_code_prefers_cached_new_node_over_hangye_fallback():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.return_value = pd.DataFrame(
        [
            {"industry_name": "电力行业", "industry_code": "hangye_ZD44"},
        ]
    )

    with patch.object(
        SinaIndustryAdapter, "_get_cached_sina_stock_nodes", return_value={"new_dlhy"}
    ):
        assert adapter._resolve_sina_industry_code("电力", "881145") == "new_dlhy"


def test_resolve_sina_industry_code_avoids_overbroad_cached_alias():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.return_value = pd.DataFrame()

    with patch.object(
        SinaIndustryAdapter, "_get_cached_sina_stock_nodes", return_value={"new_ylqx"}
    ):
        assert adapter._resolve_sina_industry_code("医疗服务", "881160") is None


def test_resolve_sina_industry_code_avoids_overbroad_live_new_node_match():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.return_value = pd.DataFrame(
        [
            {"industry_name": "生物制药", "industry_code": "new_swzz"},
        ]
    )

    with patch.object(
        SinaIndustryAdapter, "_get_cached_sina_stock_nodes", return_value={"new_swzz"}
    ):
        assert adapter._resolve_sina_industry_code("医疗服务", "881160") is None


def test_resolve_sina_industry_code_uses_cached_new_node_for_logistics_family():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.return_value = pd.DataFrame(
        [
            {"industry_name": "物流", "industry_code": "hangye_ZG59"},
        ]
    )

    with patch.object(
        SinaIndustryAdapter, "_get_cached_sina_stock_nodes", return_value={"new_wzwm"}
    ):
        assert adapter._resolve_sina_industry_code("物流", "881159") == "new_wzwm"


def test_resolve_sina_industry_node_marks_proxy_source():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.return_value = pd.DataFrame()

    with patch.object(
        SinaIndustryAdapter, "_get_cached_sina_stock_nodes", return_value={"new_dzqj"}
    ):
        assert adapter._resolve_sina_industry_node("半导体", "881121") == (
            "new_dzqj",
            "sina_proxy_stock_sum",
        )


def test_resolve_sina_industry_node_uses_persistent_lookup_before_dataframe_scan():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()

    with (
        patch.object(
            SinaFinanceProvider,
            "_get_persistent_industry_list_lookup",
            return_value={"白酒": [{"industry_name": "白酒", "industry_code": "new_bj"}]},
        ),
        patch.object(
            SinaIndustryAdapter,
            "_get_sina_industry_list",
            side_effect=AssertionError("persistent lookup should resolve before DataFrame scan"),
        ),
    ):
        assert adapter._resolve_sina_industry_node("白酒", allow_live=False) == (
            "new_bj",
            "sina_stock_sum",
        )


def test_get_cached_stock_list_by_industry_uses_persistent_proxy_snapshot():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.akshare = MagicMock()
    adapter.sina._get_persistent_industry_stock_rows.side_effect = lambda code: (
        [
            {
                "code": "688981",
                "name": "中芯国际",
                "change_pct": 1.8,
                "mktcap": 42000000,
                "volume": 100,
                "amount": 200,
                "turnover_ratio": 4.6,
                "pe_ratio": 52.7,
                "pb_ratio": 3.1,
            }
        ]
        if code == "new_dzqj"
        else []
    )

    with patch.object(
        SinaIndustryAdapter, "_get_cached_sina_stock_nodes", return_value={"new_dzqj"}
    ), patch.object(
        SinaFinanceProvider, "_load_persistent_industry_list", return_value=pd.DataFrame()
    ):
        stocks = adapter.get_cached_stock_list_by_industry("半导体")

    assert len(stocks) == 1
    assert stocks[0]["symbol"] == "688981"
    assert stocks[0]["market_cap"] == 42000000 * 10000
    assert stocks[0]["turnover_rate"] == 4.6
    assert stocks[0]["pe_ratio"] == 52.7
    adapter.akshare.persist_stock_list_snapshot.assert_called_once_with(
        "半导体",
        stocks,
        include_market_cap_lookup=False,
    )


def test_get_ths_industry_catalog_uses_persistent_snapshot_before_live(tmp_path):
    adapter = SinaIndustryAdapter()
    original_path = SinaIndustryAdapter._ths_catalog_snapshot_path
    original_cache = SinaIndustryAdapter._ths_catalog_shared_cache
    original_cache_time = SinaIndustryAdapter._ths_catalog_shared_cache_time
    SinaIndustryAdapter._ths_catalog_snapshot_path = tmp_path / "ths_industry_catalog_snapshot.json"
    SinaIndustryAdapter._ths_catalog_shared_cache = None
    SinaIndustryAdapter._ths_catalog_shared_cache_time = 0
    SinaIndustryAdapter._ths_catalog_snapshot_path.write_text(
        json.dumps(
            {
                "updated_at": time.time(),
                "data": [{"industry_name": "养殖业", "industry_code": "881203"}],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    try:
        with patch(
            "src.data.providers.sina_ths_adapter.ak.stock_board_industry_name_ths",
            side_effect=AssertionError("live THS catalog should not run"),
        ):
            catalog = adapter._get_ths_industry_catalog()
    finally:
        SinaIndustryAdapter._ths_catalog_snapshot_path = original_path
        SinaIndustryAdapter._ths_catalog_shared_cache = original_cache
        SinaIndustryAdapter._ths_catalog_shared_cache_time = original_cache_time

    assert catalog["industry_name"].tolist() == ["养殖业"]
    assert catalog["industry_code"].tolist() == ["881203"]


def test_get_ths_flow_data_parses_html_without_pandas_read_html(monkeypatch):
    adapter = SinaIndustryAdapter()
    sample_html = """
    <span class="page_info">1/1</span>
    <table class="m-table J-ajax-table">
      <thead>
        <tr>
          <th>序号</th>
          <th>行业</th>
          <th>行业指数</th>
          <th>涨跌幅</th>
          <th>流入资金(亿)</th>
          <th>流出资金(亿)</th>
          <th>净额(亿)</th>
          <th>公司家数</th>
          <th>领涨股</th>
          <th>涨跌幅</th>
          <th>当前价(元)</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>1</td>
          <td>养殖业</td>
          <td>1234.56</td>
          <td>1.23%</td>
          <td>9.87</td>
          <td>8.76</td>
          <td>1.11</td>
          <td>42</td>
          <td>罗牛山</td>
          <td>3.18%</td>
          <td>6.66</td>
        </tr>
      </tbody>
    </table>
    """

    class _Response:
        status_code = 200
        text = sample_html

    monkeypatch.setattr(
        SinaIndustryAdapter, "_build_ths_request_headers", lambda *args, **kwargs: ({}, False)
    )
    monkeypatch.setattr(
        "src.data.providers.sina_ths_adapter.requests.get", lambda *args, **kwargs: _Response()
    )
    monkeypatch.setattr(
        "src.data.providers.sina_ths_adapter.pd.read_html",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("read_html should not run")),
    )

    flow_df = adapter._get_ths_flow_data(1)

    assert flow_df.loc[0, "行业"] == "养殖业"
    assert flow_df.loc[0, "涨跌幅"] == "1.23%"
    assert flow_df.loc[0, "涨跌幅.1"] == "3.18%"
    assert flow_df.loc[0, "领涨股"] == "罗牛山"
    assert flow_df.loc[0, "industry_name"] == "养殖业"


def test_get_cached_stock_list_by_industry_falls_back_to_akshare_snapshot():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.akshare = MagicMock()
    adapter.sina._get_persistent_industry_stock_rows.return_value = []
    adapter.akshare.get_cached_stock_list_by_industry.return_value = [
        {
            "symbol": "600519",
            "name": "贵州茅台",
            "market_cap": 2.1e12,
            "pe_ratio": 28.5,
            "change_pct": 1.2,
        }
    ]

    with patch.object(SinaIndustryAdapter, "_get_cached_sina_stock_nodes", return_value=set()):
        with patch.object(
            SinaFinanceProvider, "_load_persistent_industry_list", return_value=pd.DataFrame()
        ):
            stocks = adapter.get_cached_stock_list_by_industry("白酒")

    assert len(stocks) == 1
    assert stocks[0]["symbol"] == "600519"
    adapter.akshare.get_cached_stock_list_by_industry.assert_called_once_with(
        "白酒",
        include_market_cap_lookup=False,
        allow_stale=True,
    )


def test_get_cached_sina_industry_codes_reuses_name_level_cache():
    adapter = SinaIndustryAdapter()
    original_name_cache = dict(SinaIndustryAdapter._candidate_industry_names_cache)
    original_code_cache = dict(SinaIndustryAdapter._cached_sina_industry_codes_cache)
    original_stock_nodes = SinaIndustryAdapter._sina_cached_stock_nodes
    original_stock_nodes_time = SinaIndustryAdapter._sina_cached_stock_nodes_time
    SinaIndustryAdapter._candidate_industry_names_cache = {}
    SinaIndustryAdapter._cached_sina_industry_codes_cache = {}
    SinaIndustryAdapter._sina_cached_stock_nodes = None
    SinaIndustryAdapter._sina_cached_stock_nodes_time = 0

    try:
        with (
            patch.object(
                SinaIndustryAdapter,
                "_get_cached_sina_stock_nodes",
                side_effect=[frozenset({"new_dzqj"})],
            ) as stock_nodes_mock,
            patch.object(
                SinaFinanceProvider,
                "_get_persistent_industry_list_lookup",
                side_effect=[{"半导体": [{"industry_code": "new_dzqj"}]}],
            ) as lookup_mock,
        ):
            first = adapter._get_cached_sina_industry_codes("半导体")
            second = adapter._get_cached_sina_industry_codes("半导体")
    finally:
        SinaIndustryAdapter._candidate_industry_names_cache = original_name_cache
        SinaIndustryAdapter._cached_sina_industry_codes_cache = original_code_cache
        SinaIndustryAdapter._sina_cached_stock_nodes = original_stock_nodes
        SinaIndustryAdapter._sina_cached_stock_nodes_time = original_stock_nodes_time

    assert first == ["new_dzqj"]
    assert second == ["new_dzqj"]
    assert stock_nodes_mock.call_count == 1
    assert lookup_mock.call_count == 1


def test_get_stock_list_by_industry_fast_mode_uses_cached_summary_only_for_final_fallback():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.akshare = MagicMock()
    adapter.akshare.get_stock_list_by_industry.side_effect = AssertionError(
        "fast mode should not hit live akshare"
    )
    adapter._resolve_sina_industry_code = MagicMock(return_value=None)
    adapter._build_symbol_cache_industry_fallback = MagicMock(return_value=[])
    adapter.get_cached_stock_list_by_industry = MagicMock(return_value=[])
    adapter._get_ths_industry_summary = MagicMock(return_value=pd.DataFrame())
    adapter.sina.get_industry_list.return_value = pd.DataFrame()

    stocks = adapter.get_stock_list_by_industry("养殖业", fast_mode=True)

    assert stocks == []
    adapter._get_ths_industry_summary.assert_called_once_with(cached_only=True)
    adapter.akshare.get_stock_list_by_industry.assert_not_called()


def test_get_stock_list_by_industry_fast_mode_named_fallback_prefers_persistent_industry_list():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.side_effect = AssertionError(
        "fast mode named fallback should not run live Sina list"
    )
    adapter.sina.get_industry_stocks.return_value = [
        {
            "code": "600519",
            "name": "贵州茅台",
            "change_pct": 1.2,
            "mktcap": 123,
            "volume": 1,
            "amount": 2,
            "turnover_ratio": 2.3,
        }
    ]
    adapter.akshare = MagicMock()
    adapter._resolve_sina_industry_code = MagicMock(return_value=None)
    adapter._build_symbol_cache_industry_fallback = MagicMock(return_value=[])
    adapter.get_cached_stock_list_by_industry = MagicMock(return_value=[])
    adapter._get_ths_industry_summary = MagicMock(return_value=pd.DataFrame())
    original_cache = SinaIndustryAdapter._sina_industry_list_shared_cache
    original_cache_time = SinaIndustryAdapter._sina_industry_list_shared_cache_time
    SinaIndustryAdapter._sina_industry_list_shared_cache = None
    SinaIndustryAdapter._sina_industry_list_shared_cache_time = 0

    persistent_industries = pd.DataFrame(
        [
            {"industry_name": "白酒", "industry_code": "new_bj"},
        ]
    )

    try:
        with patch.object(
            SinaFinanceProvider,
            "_get_persistent_industry_list_lookup",
            return_value={"白酒": persistent_industries.to_dict(orient="records")},
        ):
            stocks = adapter.get_stock_list_by_industry("白酒", fast_mode=True)
    finally:
        SinaIndustryAdapter._sina_industry_list_shared_cache = original_cache
        SinaIndustryAdapter._sina_industry_list_shared_cache_time = original_cache_time

    assert len(stocks) == 1
    assert stocks[0]["symbol"] == "600519"
    assert stocks[0]["turnover_rate"] == 2.3
    adapter.sina.get_industry_stocks.assert_called_once_with("new_bj")
    adapter.sina.get_industry_list.assert_not_called()


def test_get_stock_list_by_industry_fast_mode_skips_live_sina_industry_list_for_node_resolution():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.side_effect = AssertionError(
        "fast mode node resolution should not run live Sina list"
    )
    adapter.sina.get_industry_stocks.return_value = []
    adapter.akshare = MagicMock()
    adapter.akshare.get_stock_list_by_industry.return_value = []
    adapter.akshare.get_cached_stock_list_by_industry.return_value = []
    adapter._build_symbol_cache_industry_fallback = MagicMock(return_value=[])
    adapter._get_ths_industry_summary = MagicMock(return_value=pd.DataFrame())

    original_cache = SinaIndustryAdapter._sina_industry_list_shared_cache
    original_cache_time = SinaIndustryAdapter._sina_industry_list_shared_cache_time
    SinaIndustryAdapter._sina_industry_list_shared_cache = None
    SinaIndustryAdapter._sina_industry_list_shared_cache_time = 0

    try:
        with (
            patch.object(
                SinaFinanceProvider, "_get_persistent_industry_list_lookup", return_value={}
            ),
            patch.object(
                SinaIndustryAdapter,
                "_get_cached_sina_stock_nodes",
                return_value=set(),
            ),
        ):
            stocks = adapter.get_stock_list_by_industry("养殖业", fast_mode=True)
    finally:
        SinaIndustryAdapter._sina_industry_list_shared_cache = original_cache
        SinaIndustryAdapter._sina_industry_list_shared_cache_time = original_cache_time

    assert stocks == []
    adapter.sina.get_industry_list.assert_not_called()


def test_get_stock_list_by_industry_fast_mode_uses_persistent_leader_before_akshare_live():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.return_value = pd.DataFrame()
    adapter.akshare = MagicMock()
    adapter.akshare.get_stock_list_by_industry.side_effect = AssertionError(
        "should not call live akshare"
    )
    adapter._resolve_sina_industry_code = MagicMock(return_value=None)
    adapter._build_symbol_cache_industry_fallback = MagicMock(return_value=[])
    adapter.get_cached_stock_list_by_industry = MagicMock(return_value=[])
    adapter._get_ths_industry_summary = MagicMock(return_value=pd.DataFrame())
    adapter.get_stock_valuation = MagicMock(
        return_value={"market_cap": 123456789.0, "pe_ttm": 18.2, "pb": 3.4, "amount": 567890.0}
    )

    persistent_industries = pd.DataFrame(
        [
            {
                "industry_name": "养殖业",
                "leading_stock_name": "牧原股份",
                "leading_stock_code": "sz002714",
                "leading_stock_change": 2.35,
            }
        ]
    )

    with patch.object(
        SinaFinanceProvider,
        "_get_persistent_industry_list_lookup",
        return_value={"养殖业": persistent_industries.to_dict(orient="records")},
    ):
        stocks = adapter.get_stock_list_by_industry("养殖业", fast_mode=True)

    assert len(stocks) == 1
    assert stocks[0]["symbol"] == "002714"
    assert stocks[0]["name"] == "牧原股份"
    assert stocks[0]["change_pct"] == 2.35
    assert stocks[0]["market_cap"] == 123456789.0
    assert stocks[0]["pe_ratio"] == 18.2
    adapter.get_stock_valuation.assert_called_once_with("002714", cached_only=True)
    adapter._get_ths_industry_summary.assert_not_called()
    adapter.akshare.get_stock_list_by_industry.assert_not_called()


def test_get_industry_money_flow_enriches_with_tushare_as_fifth_source():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_money_flow.side_effect = AssertionError(
        "Sina market-cap fallback should not run when Tushare fills board metadata"
    )
    adapter._attach_industry_codes = MagicMock(
        side_effect=lambda df: df.assign(industry_code="881001")
    )
    adapter._get_ths_flow_data = MagicMock(
        return_value=pd.DataFrame(
            [
                {
                    "行业": "电子",
                    "industry_name": "电子",
                    "涨跌幅": "0.00%",
                    "净额": 0,
                    "流入": 0,
                    "流出": 0,
                    "公司家数": 0,
                }
            ]
        )
    )
    adapter._enrich_with_akshare = MagicMock(side_effect=lambda df, **kwargs: df)
    adapter._candidate_tushare_trade_dates = MagicMock(return_value=["2024-01-03"])
    adapter._persist_market_cap_snapshot = MagicMock()

    class _FakeTushare:
        def get_industry_moneyflow(self, trade_date):
            assert trade_date == "2024-01-03"
            return pd.DataFrame(
                [
                    {
                        "industry": "电子",
                        "net_amount": 120000.0,
                        "net_amount_rate": 4.2,
                    }
                ]
            )

        def get_dc_board_status(self, trade_date, idx_type="行业板块"):
            assert trade_date == "2024-01-03"
            assert idx_type == "行业板块"
            return pd.DataFrame(
                [
                    {
                        "name": "电子",
                        "pct_change": 1.8,
                        "leading": "中芯国际",
                        "leading_code": "688981.SH",
                        "leading_pct": 6.6,
                        "total_mv": 32000000.0,
                        "turnover_rate": 2.7,
                        "up_num": 42,
                        "down_num": 8,
                    }
                ]
            )

    adapter.tushare = _FakeTushare()

    result = adapter.get_industry_money_flow(days=5)

    assert len(result) == 1
    row = result.iloc[0]
    assert row["industry_name"] == "电子"
    assert row["change_pct"] == 1.8
    assert row["main_net_inflow"] == 120000.0 * 10000
    assert row["main_net_ratio"] == 4.2
    assert row["flow_strength"] == pytest.approx(0.042)
    assert row["total_market_cap"] == 32000000.0 * 10000
    assert row["turnover_rate"] == 2.7
    assert row["stock_count"] == 50
    assert row["leading_stock"] == "中芯国际"
    assert row["leading_stock_code"] == "688981"
    assert row["leading_stock_change"] == 6.6
    assert row["market_cap_source"] == "tushare_dc_board"
    assert "ths" in row["data_sources"]
    assert "tushare_moneyflow_ind_ths" in row["data_sources"]
    assert "tushare_dc_index" in row["data_sources"]
    adapter.sina.get_industry_money_flow.assert_not_called()


def test_get_stock_list_by_industry_uses_tushare_leader_final_fallback():
    adapter = SinaIndustryAdapter()
    adapter.sina = MagicMock()
    adapter.sina.get_industry_list.return_value = pd.DataFrame()
    adapter.akshare = MagicMock()
    adapter.akshare.get_stock_list_by_industry.side_effect = AssertionError(
        "fast mode should not call live akshare"
    )
    adapter._normalize_to_ths_industry_name = MagicMock(return_value="养殖业")
    adapter._resolve_sina_industry_code = MagicMock(return_value=None)
    adapter._build_symbol_cache_industry_fallback = MagicMock(return_value=[])
    adapter.get_cached_stock_list_by_industry = MagicMock(return_value=[])
    adapter._get_ths_industry_summary = MagicMock(return_value=pd.DataFrame())
    adapter._candidate_tushare_trade_dates = MagicMock(return_value=["2024-01-03"])
    adapter.get_stock_valuation = MagicMock(
        return_value={"market_cap": 87654321.0, "pe_ttm": 16.8, "pb": 2.7, "amount": 12345.0}
    )

    class _FakeTushare:
        def get_dc_board_status(self, trade_date, idx_type="行业板块"):
            assert trade_date == "2024-01-03"
            assert idx_type == "行业板块"
            return pd.DataFrame(
                [
                    {
                        "name": "养殖业",
                        "leading": "牧原股份",
                        "leading_code": "002714.SZ",
                        "leading_pct": 3.2,
                    }
                ]
            )

    adapter.tushare = _FakeTushare()

    with patch.object(SinaFinanceProvider, "_get_persistent_industry_list_lookup", return_value={}):
        stocks = adapter.get_stock_list_by_industry("养殖业", fast_mode=True)

    assert len(stocks) == 1
    assert stocks[0]["symbol"] == "002714"
    assert stocks[0]["name"] == "牧原股份"
    assert stocks[0]["change_pct"] == 3.2
    assert stocks[0]["market_cap"] == 87654321.0
    assert stocks[0]["pe_ratio"] == 16.8
    assert stocks[0]["pb_ratio"] == 2.7
    assert stocks[0]["source"] == "tushare_dc_index"
    adapter.get_stock_valuation.assert_called_once_with("002714", cached_only=True)
    adapter.akshare.get_stock_list_by_industry.assert_not_called()


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
    adapter._resolve_sina_industry_node = MagicMock(
        return_value=("new_dzqj", "sina_proxy_stock_sum")
    )
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
    SinaIndustryAdapter._industry_market_cap_snapshot_path = (
        tmp_path / "industry_market_cap_snapshot.json"
    )
    try:
        adapter._persist_market_cap_snapshot(
            pd.DataFrame(
                [
                    {
                        "industry_name": "电力",
                        "industry_code": "881145",
                        "total_market_cap": 2e12,
                        "market_cap_source": "akshare_metadata",
                    },
                    {
                        "industry_name": "食品加工制造",
                        "industry_code": "881127",
                        "total_market_cap": 5e11,
                        "market_cap_source": "sina_stock_sum",
                    },
                    {
                        "industry_name": "未知行业",
                        "industry_code": "999999",
                        "total_market_cap": 1.0,
                        "market_cap_source": "estimated_from_flow",
                    },
                ]
            )
        )
        payload = json.loads(
            SinaIndustryAdapter._industry_market_cap_snapshot_path.read_text(encoding="utf-8")
        )
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
                    {
                        "industry_name": "食品加工制造",
                        "industry_code": "881127",
                        "total_market_cap": 5e11,
                        "market_cap_source": "sina_stock_sum",
                    },
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
                {
                    "industry_name": "电力",
                    "industry_code": "881145",
                    "total_market_cap": 0.0,
                    "market_cap_source": "unknown",
                    "data_sources": ["ths"],
                },
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
                {
                    "industry_name": "电力",
                    "industry_code": "881145",
                    "total_market_cap": 0.0,
                    "market_cap_source": "unknown",
                    "data_sources": ["ths"],
                },
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
                        "updated_at": now
                        - (SinaIndustryAdapter._market_cap_snapshot_stale_after_hours + 3) * 3600,
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
    assert (
        status["max_age_hours"] >= SinaIndustryAdapter._market_cap_snapshot_stale_after_hours + 2.9
    )
    assert status["source_counts"] == {"akshare_metadata": 1, "sina_stock_sum": 1}


def test_load_persistent_market_cap_snapshot_reuses_memory_when_file_unchanged(tmp_path):
    snapshot_path = tmp_path / "industry_market_cap_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "updated_at": time.time(),
                "data": {
                    "881145": {
                        "industry_name": "电力",
                        "total_market_cap": 2450000000000.0,
                        "market_cap_source": "akshare_metadata",
                        "updated_at": time.time(),
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    original_path = SinaIndustryAdapter._industry_market_cap_snapshot_path
    original_cache = SinaIndustryAdapter._market_cap_snapshot_payload_cache
    original_meta = SinaIndustryAdapter._market_cap_snapshot_payload_cache_meta
    SinaIndustryAdapter._industry_market_cap_snapshot_path = snapshot_path
    SinaIndustryAdapter._reset_market_cap_snapshot_payload_cache()

    try:
        first = SinaIndustryAdapter._load_persistent_market_cap_snapshot()
        with patch.object(
            Path,
            "read_text",
            side_effect=AssertionError("read_text should not run on warm snapshot load"),
        ):
            second = SinaIndustryAdapter._load_persistent_market_cap_snapshot()
    finally:
        SinaIndustryAdapter._industry_market_cap_snapshot_path = original_path
        SinaIndustryAdapter._market_cap_snapshot_payload_cache = original_cache
        SinaIndustryAdapter._market_cap_snapshot_payload_cache_meta = original_meta

    assert first == second
    assert first["881145"]["industry_name"] == "电力"


def test_persist_market_cap_snapshot_skips_disk_write_when_snapshot_unchanged(tmp_path):
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
                        "updated_at": now,
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    original_path = SinaIndustryAdapter._industry_market_cap_snapshot_path
    original_cache = SinaIndustryAdapter._market_cap_snapshot_payload_cache
    original_meta = SinaIndustryAdapter._market_cap_snapshot_payload_cache_meta
    SinaIndustryAdapter._industry_market_cap_snapshot_path = snapshot_path
    SinaIndustryAdapter._reset_market_cap_snapshot_payload_cache()

    df = pd.DataFrame(
        [
            {
                "industry_name": "电力",
                "industry_code": "881145",
                "total_market_cap": 2450000000000.0,
                "market_cap_source": "akshare_metadata",
            }
        ]
    )

    try:
        with patch.object(
            SinaIndustryAdapter,
            "_write_market_cap_snapshot_payload",
            side_effect=AssertionError("snapshot payload should not be rewritten when unchanged"),
        ):
            SinaIndustryAdapter._persist_market_cap_snapshot(df)
    finally:
        SinaIndustryAdapter._industry_market_cap_snapshot_path = original_path
        SinaIndustryAdapter._market_cap_snapshot_payload_cache = original_cache
        SinaIndustryAdapter._market_cap_snapshot_payload_cache_meta = original_meta


def test_enrich_with_akshare_uses_precise_join_keys():
    adapter = SinaIndustryAdapter()
    adapter.get_symbol_by_name = MagicMock(return_value="")
    SinaIndustryAdapter._akshare_valuation_snapshot_cache = None
    SinaIndustryAdapter._akshare_valuation_snapshot_cache_time = 0
    SinaIndustryAdapter._akshare_valuation_snapshot_failure_at = 0

    source_df = pd.DataFrame([{"industry_name": "房地产开发", "leading_stock": "万科A"}])
    meta_df = pd.DataFrame(
        [
            {
                "industry_name": "房地产服务",
                "total_market_cap": 999,
                "turnover_rate": 8.8,
                "market_cap_source": "akshare_metadata",
            },
        ]
    )
    valuation_df = pd.DataFrame(
        [{"行业名称": "房地产服务", "TTM(滚动)市盈率": 22.2, "市净率": 1.5, "静态股息率": 0.8}]
    )

    with (
        patch(
            "src.data.providers.akshare_provider.AKShareProvider._get_industry_metadata",
            return_value=meta_df,
        ),
        patch(
            "src.data.providers.sina_ths_adapter.ak.sw_index_first_info",
            return_value=valuation_df,
        ),
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
    meta_df = pd.DataFrame(
        [
            {
                "industry_name": "白酒",
                "total_market_cap": 123.0,
                "turnover_rate": 2.5,
                "market_cap_source": "akshare_metadata",
            }
        ]
    )
    valuation_df = pd.DataFrame(
        [{"行业名称": "白酒", "TTM(滚动)市盈率": 18.8, "市净率": 3.2, "静态股息率": 1.1}]
    )

    with (
        patch(
            "src.data.providers.akshare_provider.AKShareProvider._get_industry_metadata",
            return_value=meta_df,
        ),
        patch(
            "src.data.providers.sina_ths_adapter.ak.sw_index_first_info",
            return_value=valuation_df,
        ),
    ):
        enriched = adapter._enrich_with_akshare(source_df.copy())

    assert enriched["market_cap_source"].iloc[0] == "akshare_metadata"
    assert enriched["valuation_source"].iloc[0] == "akshare_sw"
    assert enriched["valuation_quality"].iloc[0] == "industry_level"
    assert "akshare" in enriched["data_sources"].iloc[0]


def test_get_akshare_valuation_snapshot_cached_only_schedules_background_refresh():
    SinaIndustryAdapter._akshare_valuation_snapshot_cache = None
    SinaIndustryAdapter._akshare_valuation_snapshot_cache_time = 0
    SinaIndustryAdapter._akshare_valuation_snapshot_failure_at = 0
    SinaIndustryAdapter._akshare_valuation_snapshot_refresh_future = None

    with patch.object(
        SinaIndustryAdapter, "_schedule_akshare_valuation_snapshot_refresh"
    ) as schedule_refresh:
        snapshot = SinaIndustryAdapter._get_akshare_valuation_snapshot(
            cached_only=True,
            schedule_refresh=True,
        )

    assert snapshot.empty
    schedule_refresh.assert_called_once()


def test_get_ths_hexin_v_reuses_cached_token_within_ttl():
    SinaIndustryAdapter._ths_js_content_cache = None
    SinaIndustryAdapter._ths_hexin_v_cache = None
    SinaIndustryAdapter._ths_hexin_v_cache_time = 0

    class _DummyRacer:
        instances = 0

        def __init__(self):
            type(self).instances += 1

        def eval(self, script):
            assert script == "fake-js"

        def call(self, name):
            assert name == "v"
            return f"token-{type(self).instances}"

    with (
        patch(
            "src.data.providers.sina_ths_adapter.ak.stock_feature.stock_fund_flow._get_file_content_ths",
            return_value="fake-js",
        ),
        patch(
            "src.data.providers.sina_ths_adapter.py_mini_racer.MiniRacer",
            side_effect=_DummyRacer,
        ),
    ):
        first_token, first_from_cache = SinaIndustryAdapter._get_ths_hexin_v()
        second_token, second_from_cache = SinaIndustryAdapter._get_ths_hexin_v()

    assert first_token == "token-1"
    assert second_token == "token-1"
    assert first_from_cache is False
    assert second_from_cache is True
    assert _DummyRacer.instances == 1


def test_ensure_flow_strength_rebuilds_from_main_net_ratio():
    adapter = SinaIndustryAdapter()
    df = pd.DataFrame(
        [
            {
                "industry_name": "电子",
                "main_net_inflow": 5_000_000_000,
                "main_net_ratio": 5.0,
                "flow_strength": 0.0,
            },
            {
                "industry_name": "医药生物",
                "main_net_inflow": 3_000_000_000,
                "main_net_ratio": 3.0,
                "flow_strength": 0.0,
            },
            {
                "industry_name": "计算机",
                "main_net_inflow": -1_000_000_000,
                "main_net_ratio": -1.0,
                "flow_strength": 0.0,
            },
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


def test_sina_ths_adapter_circuit_short_circuits_after_repeated_failures():
    original_breakers = SinaIndustryAdapter._circuit_breakers
    SinaIndustryAdapter._circuit_breakers = {}
    calls = 0

    def unstable_fetch():
        nonlocal calls
        calls += 1
        raise RuntimeError("upstream unavailable")

    try:
        for _ in range(5):
            with pytest.raises(RuntimeError):
                SinaIndustryAdapter._call_with_circuit("unit_test_fetch", unstable_fetch)

        breaker = SinaIndustryAdapter._circuit_breakers["unit_test_fetch"]
        assert breaker.state is CircuitState.OPEN

        with pytest.raises(CircuitOpenError):
            SinaIndustryAdapter._call_with_circuit("unit_test_fetch", unstable_fetch)

        assert calls == 5
        assert SinaIndustryAdapter.get_circuit_status()["unit_test_fetch"]["state"] == "open"
    finally:
        SinaIndustryAdapter._circuit_breakers = original_breakers


def test_valuation_prefers_tushare_for_live_detail():
    adapter = SinaIndustryAdapter()
    adapter.tushare = MagicMock()
    adapter.tushare.get_stock_valuation.return_value = {
        "symbol": "600519", "name": "", "market_cap": 2.11e12,
        "pe_ttm": 28.5, "pb": 9.2, "turnover": 0.45, "amount": 0.0,
        "change_pct": 0.0, "source": "tushare",
    }
    adapter.akshare = MagicMock()

    val = adapter.get_stock_valuation("600519")

    assert val["source"] == "tushare"
    assert val["pe_ttm"] == 28.5
    adapter.tushare.get_stock_valuation.assert_called_once_with("600519")
    adapter.akshare.get_stock_valuation.assert_not_called()


def test_valuation_skips_tushare_when_cached_only():
    adapter = SinaIndustryAdapter()
    adapter.tushare = MagicMock()
    adapter.akshare = MagicMock()
    adapter.akshare.get_stock_valuation.return_value = {"symbol": "600519", "pe_ttm": 1.0}

    adapter.get_stock_valuation("600519", cached_only=True)

    adapter.tushare.get_stock_valuation.assert_not_called()
    adapter.akshare.get_stock_valuation.assert_called()


def test_valuation_falls_back_to_akshare_when_tushare_errors():
    adapter = SinaIndustryAdapter()
    adapter.tushare = MagicMock()
    adapter.tushare.get_stock_valuation.return_value = {"symbol": "600519", "error": "empty_daily_basic"}
    adapter.akshare = MagicMock()
    adapter.akshare.get_stock_valuation.return_value = {"symbol": "600519", "pe_ttm": 12.3, "market_cap": 5e11}

    val = adapter.get_stock_valuation("600519")

    assert val["pe_ttm"] == 12.3
    adapter.akshare.get_stock_valuation.assert_called()


def test_financial_data_prefers_tushare():
    adapter = SinaIndustryAdapter()
    adapter.tushare = MagicMock()
    adapter.tushare.get_stock_financial_data.return_value = {
        "roe": 31.2, "revenue_yoy": 18.0, "profit_yoy": 19.5, "source": "tushare",
    }
    adapter.akshare = MagicMock()

    fin = adapter.get_stock_financial_data("600519")

    assert fin["roe"] == 31.2
    adapter.tushare.get_stock_financial_data.assert_called_once_with("600519")
    adapter.akshare.get_stock_financial_data.assert_not_called()


def test_historical_data_prefers_tushare_for_ashare():
    adapter = SinaIndustryAdapter()
    ts_df = pd.DataFrame(
        {"open": [10.0, 10.5], "high": [10.8, 11.0], "low": [9.9, 10.4],
         "close": [10.5, 10.9], "volume": [1000.0, 1200.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    ts_df.index.name = "date"
    adapter.tushare = MagicMock()
    adapter.tushare.get_historical_data.return_value = ts_df
    adapter.akshare = MagicMock()

    with patch.object(SinaIndustryAdapter, "_ensure_history_cache_loaded", lambda: None), \
         patch.object(SinaIndustryAdapter, "_persist_history_cache", lambda: None):
        SinaIndustryAdapter._history_cache = {}
        out = adapter.get_historical_data("600519")

    assert not out.empty
    assert list(out["close"]) == [10.5, 10.9]
    adapter.akshare.get_historical_data.assert_not_called()


def test_latest_quote_prefers_sina_realtime():
    adapter = SinaIndustryAdapter()
    SinaIndustryAdapter._circuit_breakers = {}
    adapter.sina = MagicMock()
    adapter.sina.get_stock_realtime.return_value = pd.DataFrame([{
        "name": "贵州茅台", "price": 1680.0, "pre_close": 1650.0,
        "high": 1690.0, "low": 1640.0, "open": 1655.0,
        "bid": 1679.0, "ask": 1681.0, "volume": 1000, "amount": 1.0e9,
        "date": "2024-01-03", "time": "15:00:00",
    }])
    adapter.akshare = MagicMock()

    q = adapter.get_latest_quote("600519")

    assert q["source"] == "sina_realtime"
    assert q["current_price"] == 1680.0
    adapter.akshare.get_latest_quote.assert_not_called()
