from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.data.providers.provider_factory import DataProviderFactory
from src.data.providers.tushare_provider import TushareProvider


class _FakeTusharePro:
    def __init__(self):
        self.daily_calls: list[dict] = []
        self.fund_daily_calls: list[dict] = []
        self.trade_cal_calls: list[dict] = []

    def daily(self, **kwargs):
        self.daily_calls.append(kwargs)
        return pd.DataFrame(
            [
                {
                    "ts_code": kwargs.get("ts_code", "000001.SZ"),
                    "trade_date": "20240103",
                    "open": 10.0,
                    "high": 10.8,
                    "low": 9.9,
                    "close": 10.5,
                    "pct_chg": 2.0,
                    "vol": 1234.0,
                    "amount": 56789.0,
                },
                {
                    "ts_code": kwargs.get("ts_code", "000001.SZ"),
                    "trade_date": "20240102",
                    "open": 9.5,
                    "high": 10.0,
                    "low": 9.4,
                    "close": 10.0,
                    "pct_chg": 1.0,
                    "vol": 1000.0,
                    "amount": 45678.0,
                },
            ]
        )

    def trade_cal(self, **kwargs):
        self.trade_cal_calls.append(kwargs)
        return pd.DataFrame(
            [
                {"exchange": "SSE", "cal_date": "20240102", "is_open": "1"},
                {"exchange": "SSE", "cal_date": "20240103", "is_open": "1"},
            ]
        )

    def fund_daily(self, **kwargs):
        self.fund_daily_calls.append(kwargs)
        return pd.DataFrame(
            [
                {
                    "ts_code": kwargs.get("ts_code", "510300.SH"),
                    "trade_date": "20240103",
                    "open": 4.0,
                    "high": 4.2,
                    "low": 3.9,
                    "close": 4.1,
                    "pct_chg": 1.5,
                    "vol": 2000.0,
                    "amount": 88888.0,
                }
            ]
        )


class _MarketMoodPro:
    def daily(self, **kwargs):
        return pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "pct_chg": 1.2, "vol": 100.0, "amount": 100000.0},
                {"ts_code": "600000.SH", "pct_chg": -0.8, "vol": 200.0, "amount": 200000.0},
                {"ts_code": "430001.BJ", "pct_chg": 0.0, "vol": 50.0, "amount": 50000.0},
            ]
        )

    def limit_list_d(self, **kwargs):
        if kwargs.get("limit_type") == "U":
            return pd.DataFrame([{"ts_code": "000001.SZ", "limit_times": 1}])
        if kwargs.get("limit_type") == "D":
            return pd.DataFrame([{"ts_code": "600000.SH"}])
        if kwargs.get("limit_type") == "Z":
            return pd.DataFrame([{"ts_code": "000002.SZ"}, {"ts_code": "000003.SZ"}])
        return pd.DataFrame()


class _MissingKeyProvider(TushareProvider):
    def __init__(self, *args, **kwargs):  # pragma: no cover - should be skipped before init
        raise AssertionError("provider should not initialize without a token")


def test_normalizes_common_a_share_symbols_to_tushare_codes():
    assert TushareProvider.normalize_symbol("000001") == "000001.SZ"
    assert TushareProvider.normalize_symbol("600000") == "600000.SH"
    assert TushareProvider.normalize_symbol("430001") == "430001.BJ"
    assert TushareProvider.normalize_symbol("sz000001") == "000001.SZ"
    assert TushareProvider.normalize_symbol("600000.SH") == "600000.SH"


def test_historical_daily_data_uses_tushare_pro_and_standardizes_frame():
    fake = _FakeTusharePro()
    provider = TushareProvider(api_key="token", config={"pro_client": fake})

    frame = provider.get_historical_data(
        "000001",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 4),
        interval="1d",
    )

    assert fake.daily_calls[0] == {
        "ts_code": "000001.SZ",
        "start_date": "20240101",
        "end_date": "20240104",
    }
    assert list(frame.index.strftime("%Y-%m-%d")) == ["2024-01-02", "2024-01-03"]
    assert frame.index.name == "date"
    assert frame["close"].tolist() == [10.0, 10.5]
    assert frame["volume"].tolist() == [1000.0, 1234.0]
    assert "returns" in frame.columns
    assert frame.attrs["source"] == "tushare"
    assert frame.attrs["source_mode"] == "eod"


def test_etf_history_uses_tushare_fund_daily_endpoint():
    fake = _FakeTusharePro()
    provider = TushareProvider(api_key="token", config={"pro_client": fake})

    frame = provider.get_historical_data("510300.SH", start_date=datetime(2024, 1, 1))

    assert fake.daily_calls == []
    assert fake.fund_daily_calls[0] == {"ts_code": "510300.SH", "start_date": "20240101"}
    assert frame["close"].tolist() == [4.1]
    assert frame.attrs["asset_type"] == "fund"


def test_latest_quote_is_explicitly_eod_snapshot_not_realtime():
    provider = TushareProvider(api_key="token", config={"pro_client": _FakeTusharePro()})

    quote = provider.get_latest_quote("000001")

    assert quote["symbol"] == "000001.SZ"
    assert quote["price"] == 10.5
    assert quote["change_percent"] == 2.0
    assert quote["source"] == "tushare"
    assert quote["mode"] == "eod_snapshot"
    assert quote["as_of"] == "2024-01-03"


def test_trade_calendar_returns_open_days_as_iso_dates():
    fake = _FakeTusharePro()
    provider = TushareProvider(api_key="token", config={"pro_client": fake})

    days = provider.get_trade_calendar(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 4),
        exchange="SSE",
    )

    assert days == ["2024-01-02", "2024-01-03"]
    assert fake.trade_cal_calls[0] == {
        "exchange": "SSE",
        "start_date": "20240101",
        "end_date": "20240104",
        "is_open": "1",
    }


def test_market_mood_can_include_or_exclude_beijing_exchange():
    provider = TushareProvider(api_key="token", config={"pro_client": _MarketMoodPro()})

    all_a = provider.get_market_mood("20240103", include_bj=True)
    sh_sz = provider.get_market_mood("20240103", include_bj=False)

    assert all_a["stock_count"] == 3
    assert all_a["rise_count"] == 1
    assert all_a["fall_count"] == 1
    assert all_a["flat_count"] == 1
    assert all_a["total_amount_yi"] == 3.5
    assert all_a["limit_up_count"] == 1
    assert all_a["limit_down_count"] == 1
    assert all_a["blowup_count"] == 2
    assert sh_sz["stock_count"] == 2
    assert sh_sz["total_amount_yi"] == 3.0


def test_provider_factory_knows_tushare_and_skips_missing_token(monkeypatch):
    monkeypatch.setattr(
        DataProviderFactory,
        "PROVIDER_CLASSES",
        {"tushare": _MissingKeyProvider},
    )

    factory = DataProviderFactory(
        {
            "default": "tushare",
            "providers": ["tushare"],
            "api_keys": {"tushare": None},
            "fallback_enabled": True,
        }
    )

    report = factory.get_source_health_report()
    source = report["sources"][0]
    assert source["id"] == "tushare"
    assert source["requires_api_key"] is True
    assert source["status"] == "skipped"
    assert source["reason"] == "missing_api_key"


class _StockFundamentalsPro:
    """Fake Tushare pro client exposing daily_basic + fina_indicator."""

    def __init__(self):
        self.daily_basic_calls: list[dict] = []
        self.fina_indicator_calls: list[dict] = []

    def daily_basic(self, **kwargs):
        self.daily_basic_calls.append(kwargs)
        ts_code = kwargs.get("ts_code", "600519.SH")
        # Most-recent row deliberately listed second to prove the method sorts.
        return pd.DataFrame(
            [
                {
                    "ts_code": ts_code,
                    "trade_date": "20240102",
                    "close": 1650.0,
                    "turnover_rate": 0.40,
                    "pe": 29.5,
                    "pe_ttm": 28.0,
                    "pb": 9.0,
                    "total_mv": 207000000.0,  # 万元
                    "circ_mv": 206000000.0,
                },
                {
                    "ts_code": ts_code,
                    "trade_date": "20240103",
                    "close": 1680.0,
                    "turnover_rate": 0.45,
                    "pe": 30.1,
                    "pe_ttm": 28.5,
                    "pb": 9.2,
                    "total_mv": 211000000.0,  # 万元
                    "circ_mv": 210000000.0,
                },
            ]
        )

    def fina_indicator(self, **kwargs):
        self.fina_indicator_calls.append(kwargs)
        ts_code = kwargs.get("ts_code", "600519.SH")
        return pd.DataFrame(
            [
                {"ts_code": ts_code, "end_date": "20231231", "roe": 31.2, "or_yoy": 18.0, "netprofit_yoy": 19.5},
                {"ts_code": ts_code, "end_date": "20230930", "roe": 24.0, "or_yoy": 16.0, "netprofit_yoy": 17.0},
            ]
        )


def test_get_stock_valuation_maps_latest_daily_basic_to_display_shape():
    provider = TushareProvider(config={"pro_client": _StockFundamentalsPro()})

    val = provider.get_stock_valuation("600519")

    assert "error" not in val
    # Picks the most recent trade_date (20240103), not the first row.
    assert val["pe_ttm"] == 28.5
    assert val["pb"] == 9.2
    assert val["turnover"] == 0.45
    # total_mv is in 万元; market_cap is normalized to raw yuan to match the
    # AKShare/Tencent valuation shape the scorer consumes.
    assert val["market_cap"] == 211000000.0 * 10000
    assert val["source"] == "tushare"


def test_get_stock_valuation_rejects_non_ashare_symbol():
    provider = TushareProvider(config={"pro_client": _StockFundamentalsPro()})

    val = provider.get_stock_valuation("AAPL")

    assert "error" in val


def test_get_stock_financial_data_maps_latest_fina_indicator():
    provider = TushareProvider(config={"pro_client": _StockFundamentalsPro()})

    fin = provider.get_stock_financial_data("600519")

    assert "error" not in fin
    assert fin["roe"] == 31.2
    assert fin["revenue_yoy"] == 18.0
    assert fin["profit_yoy"] == 19.5
    assert fin["source"] == "tushare"


class _BadTokenPro:
    def trade_cal(self, **kwargs):
        raise Exception("您的token不对，请确认。")


class _RateLimitedPro:
    def trade_cal(self, **kwargs):
        raise Exception("抱歉，您每分钟最多访问该接口500次")


def test_health_check_ok_when_reachable():
    provider = TushareProvider(config={"pro_client": _FakeTusharePro()})
    hc = provider.health_check()
    assert hc["ok"] is True
    assert hc["reason"] == "ok"


def test_health_check_flags_invalid_token():
    provider = TushareProvider(config={"pro_client": _BadTokenPro()})
    hc = provider.health_check()
    assert hc["ok"] is False
    assert hc["reason"] == "token_invalid"


def test_health_check_flags_rate_limit():
    provider = TushareProvider(config={"pro_client": _RateLimitedPro()})
    hc = provider.health_check()
    assert hc["ok"] is False
    assert hc["reason"] == "rate_limited"


def test_health_check_flags_missing_token(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TS_TOKEN", raising=False)
    provider = TushareProvider(api_key="")
    hc = provider.health_check()
    assert hc["ok"] is False
    assert hc["reason"] == "token_missing"
