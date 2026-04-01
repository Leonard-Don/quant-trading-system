from datetime import datetime

import pandas as pd
import src.analytics.industry_analyzer as industry_analyzer_module
import src.analytics.leader_stock_scorer as leader_scorer_module

from src.backtest.industry_backtest import IndustryBacktester


def _price_frame(values, start="2024-01-01"):
    dates = pd.date_range(start=start, periods=len(values), freq="B")
    prices = pd.Series(values, index=dates)
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": 1_000_000,
        }
    )


class DummyIndustryDataManager:
    def __init__(self, frames):
        self.frames = frames

    def get_historical_data(self, symbol, start_date=None, end_date=None, interval="1d", period=None):
        frame = self.frames.get(symbol, pd.DataFrame()).copy()
        if frame.empty:
            return frame
        if start_date is not None:
            frame = frame[frame.index >= pd.Timestamp(start_date)]
        if end_date is not None:
            frame = frame[frame.index <= pd.Timestamp(end_date)]
        return frame


class DummyIndustryProvider:
    def get_industry_money_flow(self, days=5):
        return pd.DataFrame()

    def get_stock_list_by_industry(self, industry_name: str):
        return []

    def get_stock_financial_data(self, symbol: str):
        return {}


def test_industry_backtester_uses_proxy_prices_and_real_benchmark():
    frames = {
        "XLK": _price_frame([100, 102, 104, 103, 108, 110, 112, 111, 115, 118]),
        "SPY": _price_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109]),
    }
    backtester = IndustryBacktester(
        data_manager=DummyIndustryDataManager(frames),
        initial_capital=100000,
        benchmark_symbol="SPY",
        industry_proxy_map={
            "电子": [{"symbol": "XLK", "name": "科技 ETF", "market_cap": 1_000_000_000}],
        },
    )

    result = backtester.run_backtest(
        start_date="2024-01-01",
        end_date="2024-01-31",
        rebalance_freq="monthly",
        top_industries=1,
        stocks_per_industry=1,
    )

    comparison = backtester.compare_with_benchmark("SPY", result)

    assert result.trade_count >= 1
    assert result.benchmark_return > 0
    assert comparison["benchmark_return"] > 0
    assert comparison["benchmark"] == "SPY"
    assert result.diagnostics["industry_selection_source"] == "proxy"
    assert result.diagnostics["leader_selection_source"] == "proxy"
    assert result.diagnostics["benchmark_data_available"] is True
    assert result.diagnostics["proxy_coverage_ratio"] > 0


def test_industry_backtester_ranks_industries_from_proxy_data_without_analyzer():
    frames = {
        "XLK": _price_frame([100, 102, 104, 106, 108, 110, 112, 114, 116, 118]),
        "XLF": _price_frame([100, 100, 99, 98, 97, 96, 95, 94, 93, 92]),
        "SPY": _price_frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109]),
    }
    backtester = IndustryBacktester(
        data_manager=DummyIndustryDataManager(frames),
        initial_capital=100000,
        benchmark_symbol="SPY",
        industry_proxy_map={
            "电子": [{"symbol": "XLK", "name": "科技 ETF", "market_cap": 1_000_000_000}],
            "金融": [{"symbol": "XLF", "name": "金融 ETF", "market_cap": 900_000_000}],
        },
        ranking_lookback_days=10,
        min_price_observations=5,
        strict_data_validation=True,
    )

    ranked = backtester._rank_industries_from_proxies(
        date=datetime(2024, 1, 31),
        top_industries=2,
    )

    assert ranked[0]["industry_name"] == "电子"
    assert ranked[0]["score"] > ranked[1]["score"]


def test_industry_backtester_strict_mode_skips_missing_proxy_data():
    frames = {
        "SPY": _price_frame([100, 101, 102, 103, 104, 105]),
    }
    backtester = IndustryBacktester(
        data_manager=DummyIndustryDataManager(frames),
        initial_capital=100000,
        benchmark_symbol="SPY",
        industry_proxy_map={
            "电子": [{"symbol": "XLK", "name": "科技 ETF", "market_cap": 1_000_000_000}],
        },
        strict_data_validation=True,
    )

    result = backtester.run_backtest(
        start_date="2024-01-01",
        end_date="2024-01-10",
        rebalance_freq="monthly",
        top_industries=1,
        stocks_per_industry=1,
    )

    assert result.trade_count == 0
    assert result.total_return == 0
    assert result.diagnostics["industry_selection_source"] == "none"
    assert "XLK" in result.diagnostics["symbols_missing"]


def test_industry_backtester_bootstraps_analyzer_and_scorer_from_provider(monkeypatch):
    class FakeAnalyzer:
        def __init__(self, provider):
            self.provider = provider

    class FakeScorer:
        def __init__(self, provider):
            self.provider = provider

    monkeypatch.setattr(industry_analyzer_module, "IndustryAnalyzer", FakeAnalyzer)
    monkeypatch.setattr(leader_scorer_module, "LeaderStockScorer", FakeScorer)

    provider = DummyIndustryProvider()
    backtester = IndustryBacktester(
        data_manager=DummyIndustryDataManager({}),
        data_provider=provider,
        strict_data_validation=True,
    )

    assert isinstance(backtester.analyzer, FakeAnalyzer)
    assert isinstance(backtester.scorer, FakeScorer)
    assert backtester.analyzer.provider is provider
    assert backtester.scorer.provider is provider


def test_industry_backtester_run_wrapper_exposes_diagnostics():
    frames = {
        "XLK": _price_frame([100, 102, 104, 106, 108, 110]),
        "SPY": _price_frame([100, 101, 102, 103, 104, 105]),
    }
    payload = IndustryBacktester(
        data_manager=DummyIndustryDataManager(frames),
        benchmark_symbol="SPY",
        industry_proxy_map={
            "电子": [{"symbol": "XLK", "name": "科技 ETF", "market_cap": 1_000_000_000}],
        },
    ).run(
        start_date="2024-01-01",
        end_date="2024-01-12",
        rebalance_freq="monthly",
        top_industries=1,
        stocks_per_industry=1,
    )

    assert "diagnostics" in payload
    assert payload["diagnostics"]["provider_name"] is None
    assert payload["diagnostics"]["strict_data_validation"] is True


def test_industry_backtester_default_proxy_map_includes_a_share_etfs():
    proxy_map = IndustryBacktester.DEFAULT_INDUSTRY_PROXY_MAP

    assert proxy_map["电子"][0]["symbol"] == "159995"
    assert proxy_map["医药生物"][0]["symbol"] == "512010"
    assert proxy_map["新能源"][0]["symbol"] == "516160"
    assert proxy_map["金融"][0]["symbol"] == "512800"
