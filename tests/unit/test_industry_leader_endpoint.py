from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
import threading
from unittest.mock import MagicMock

from backend.app.api.v1.endpoints import industry as industry_endpoint
from backend.app.schemas.industry import IndustryBootstrapResponse, LeaderBoardsResponse, LeaderStockResponse
import pandas as pd


class _FakeProvider:
    def get_stock_list_by_industry(self, industry_name):
        return [
            {
                "symbol": "000001",
                "name": f"{industry_name}龙头",
                "market_cap": 12_000_000_000,
                "pe_ratio": 18.5,
                "change_pct": 1.2,
                "amount": 900_000_000,
            }
        ]


class _CountingStockProvider(_FakeProvider):
    def __init__(self):
        self.calls = 0

    def get_stock_list_by_industry(self, industry_name, fast_mode=False):
        self.calls += 1
        return super().get_stock_list_by_industry(industry_name)


class _FakeAnalyzer:
    def __init__(self):
        self.provider = _FakeProvider()

    def rank_industries(self, top_n=5, sort_by="total_score", ascending=False, lookback_days=5):
        return [{
            "rank": 1,
            "industry_name": "测试行业",
            "score": 91.2,
            "momentum": 4.2,
            "change_pct": 4.2,
            "money_flow": 120000000,
            "flow_strength": 0.64,
            "industry_volatility": 1.2,
            "industry_volatility_source": "historical_index",
            "stock_count": 2,
            "total_market_cap": 180000000000,
            "market_cap_source": "snapshot_manual",
            "mini_trend": [98.2, 99.4, 100.7],
        }]

    def build_rank_score_breakdown(self, row):
        return [{"key": "money_flow", "score": 72.0}]

    def analyze_money_flow(self, days=1):
        return pd.DataFrame(
            [
                {
                    "industry_name": "测试行业",
                    "leading_stock": "000001",
                    "leading_stock_change": 9.8,
                    "main_net_ratio": 6.4,
                    "main_net_inflow": 120000000,
                    "change_pct": 4.2,
                }
            ]
        )

    def get_industry_heatmap_data(self, days=5):
        return {
            "industries": [
                {
                    "name": "测试行业",
                    "value": 4.2,
                    "total_score": 91.2,
                    "size": 180000000000,
                    "stockCount": 2,
                    "moneyFlow": 120000000,
                    "turnoverRate": 3.1,
                    "industryVolatility": 1.2,
                    "industryVolatilitySource": "historical_index",
                    "netInflowRatio": 6.4,
                    "leadingStock": "测试龙头",
                    "sizeSource": "snapshot",
                    "marketCapSource": "snapshot_manual",
                    "marketCapSnapshotAgeHours": 2.0,
                    "marketCapSnapshotIsStale": False,
                    "valuationSource": "akshare_sw",
                    "valuationQuality": "industry_level",
                    "dataSources": ["ths"],
                    "industryIndex": 3210.5,
                    "totalInflow": 32.0,
                    "totalOutflow": 18.0,
                    "leadingStockChange": 9.8,
                    "leadingStockPrice": 18.6,
                    "pe_ttm": 16.8,
                    "pb": 2.1,
                    "dividend_yield": 1.2,
                }
            ],
            "max_value": 4.2,
            "min_value": 4.2,
            "update_time": "2026-04-20T00:00:00",
        }


class _CountingAnalyzer(_FakeAnalyzer):
    def __init__(self):
        super().__init__()
        self.rank_calls = 0

    def rank_industries(self, top_n=5, sort_by="total_score", ascending=False, lookback_days=5):
        self.rank_calls += 1
        return super().rank_industries(
            top_n=top_n,
            sort_by=sort_by,
            ascending=ascending,
            lookback_days=lookback_days,
        )


class _CountingStockAnalyzer(_FakeAnalyzer):
    def __init__(self):
        self.provider = _CountingStockProvider()


class _SnapshotWarmupAkshareProvider(_FakeProvider):
    def __init__(self):
        self.cached_calls = 0
        self.live_calls = 0
        self.persist_stock_list_snapshot = MagicMock()

    def get_cached_stock_list_by_industry(
        self,
        industry_name,
        include_market_cap_lookup=False,
        allow_stale=True,
    ):
        self.cached_calls += 1
        return []

    def get_stock_list_by_industry(self, industry_name, include_market_cap_lookup=False):
        self.live_calls += 1
        return super().get_stock_list_by_industry(industry_name)


class _SnapshotWarmupProvider(_FakeProvider):
    def __init__(self):
        self.akshare = _SnapshotWarmupAkshareProvider()

    def get_cached_stock_list_by_industry(self, industry_name):
        return [
            {
                "symbol": "000001",
                "name": f"{industry_name}龙头",
                "market_cap": 12_000_000_000,
                "pe_ratio": 18.5,
                "change_pct": 1.2,
                "amount": 900_000_000,
            }
        ]


class _FakeScorer:
    @staticmethod
    def _persist_financial_cache():
        return None

    def calculate_industry_stats(self, stocks):
        return {
            "count": len(stocks or []),
            "avg_market_cap": 0,
            "median_market_cap": 0,
            "avg_pe": 0,
            "median_pe": 0,
        }

    def score_stock_from_snapshot(self, snapshot, enrich_financial=False, score_type="core", **kwargs):
        return {
            "symbol": snapshot.get("symbol", "000001"),
            "name": snapshot.get("name", snapshot["symbol"]),
            "total_score": 97.2 if score_type == "hot" else 61.31,
            "raw_data": {
                "market_cap": snapshot.get("market_cap", 0),
                "pe_ttm": snapshot.get("pe_ratio", 0),
                "change_pct": snapshot.get("change_pct", 0),
                "roe": None,
            },
            "dimension_scores": {
                "market_cap": 0.4,
                "valuation": 0.9,
                "profitability": 0.5,
                "growth": 0.5,
                "momentum": 0.6,
                "activity": 0.4,
                "score_type": score_type,
            },
        }

    def score_stock_from_industry_snapshot(self, stock, industry_stats, score_type="core"):
        return self.score_stock_from_snapshot(stock, enrich_financial=False, score_type=score_type)

    def get_leader_stocks(self, hot_industries, top_per_industry=5, score_type="hot"):
        return [
            {
                "symbol": "000002",
                "name": "回填龙头A",
                "industry": "测试行业",
                "global_rank": 1,
                "rank": 2,
                "total_score": 88.2,
                "market_cap": 0,
                "pe_ratio": 0,
                "change_pct": 7.6,
                "dimension_scores": {"score_type": score_type, "momentum": 0.88},
            },
            {
                "symbol": "000003",
                "name": "回填龙头B",
                "industry": "测试行业",
                "global_rank": 2,
                "rank": 3,
                "total_score": 76.5,
                "market_cap": 0,
                "pe_ratio": 0,
                "change_pct": 6.1,
                "dimension_scores": {"score_type": score_type, "momentum": 0.76},
            },
        ]

    def get_leader_detail(self, symbol, score_type="core"):
        return {
            "symbol": symbol,
            "name": "详情股票",
            "total_score": 12.34,
            "dimension_scores": {
                "market_cap": 0.2,
                "valuation": 0.3,
                "profitability": 0.4,
                "growth": 0.5,
                "momentum": 0.6,
                "activity": 0.7,
            },
            "raw_data": {
                "market_cap": 15_688_999_999.99,
                "pe_ttm": 30.1,
                "change_pct": 13.32,
                "roe": 8.37,
            },
            "technical_analysis": {},
            "price_data": [],
        }


def test_get_leader_stocks_core_allows_none_roe(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    monkeypatch.setattr(industry_endpoint, "get_industry_analyzer", lambda: _FakeAnalyzer())
    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _FakeScorer())

    leaders = industry_endpoint.get_leader_stocks(
        top_n=5,
        top_industries=1,
        per_industry=1,
        list_type="core",
    )

    assert len(leaders) == 1
    assert leaders[0].symbol == "000001"
    assert leaders[0].score_type == "core"
    assert round(leaders[0].total_score, 2) == 61.31


def test_get_leader_stocks_hot_backfills_when_heatmap_underfilled(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    monkeypatch.setattr(industry_endpoint, "get_industry_analyzer", lambda: _FakeAnalyzer())
    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _FakeScorer())

    leaders = industry_endpoint.get_leader_stocks(
        top_n=3,
        top_industries=1,
        per_industry=3,
        list_type="hot",
    )

    assert len(leaders) == 3
    assert leaders[0].symbol == "000001"
    assert {leader.symbol for leader in leaders} == {"000001", "000002", "000003"}
    assert all(leader.score_type == "hot" for leader in leaders)


def test_get_leader_stocks_core_prefers_cached_provider_snapshot(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    cached_provider_stocks = [
        {
            "symbol": "688981",
            "name": "中芯国际",
            "market_cap": 420_000_000_000,
            "pe_ratio": 52.7,
            "change_pct": 1.8,
            "amount": 2_400_000_000,
        },
        {
            "symbol": "603986",
            "name": "兆易创新",
            "market_cap": 96_000_000_000,
            "pe_ratio": 34.2,
            "change_pct": 0.7,
            "amount": 1_100_000_000,
        },
    ]

    class _CachedLeaderProvider(_FakeProvider):
        def get_cached_stock_list_by_industry(self, industry_name):
            return cached_provider_stocks

        def get_stock_list_by_industry(self, industry_name, *args, **kwargs):
            raise AssertionError("live provider fetch should not run when cached leader snapshot exists")

    class _CachedLeaderAnalyzer(_FakeAnalyzer):
        def __init__(self):
            self.provider = _CachedLeaderProvider()

    monkeypatch.setattr(industry_endpoint, "get_industry_analyzer", lambda: _CachedLeaderAnalyzer())
    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _FakeScorer())

    leaders = industry_endpoint.get_leader_stocks(
        top_n=2,
        top_industries=1,
        per_industry=2,
        list_type="core",
    )

    assert [leader.symbol for leader in leaders] == ["688981", "603986"]
    assert all(leader.score_type == "core" for leader in leaders)


def test_get_leader_stocks_hot_prefers_leading_stock_lookup_before_symbol_resolve(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    class _CachedValuationProvider(_FakeProvider):
        def get_stock_valuation(self, symbol, cached_only=False):
            assert cached_only is True
            return {"symbol": symbol, "error": "cache miss"}

    class _LookupAnalyzer(_FakeAnalyzer):
        def __init__(self):
            self.provider = _CachedValuationProvider()

        def analyze_money_flow(self, days=1):
            return pd.DataFrame(
                [
                    {
                        "industry_name": "测试行业",
                        "leading_stock": "重庆银行",
                        "leading_stock_change": 9.8,
                        "main_net_ratio": 6.4,
                        "main_net_inflow": 120000000,
                        "change_pct": 4.2,
                    }
                ]
            )

    monkeypatch.setattr(industry_endpoint, "get_industry_analyzer", lambda: _LookupAnalyzer())
    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _FakeScorer())
    monkeypatch.setattr(industry_endpoint, "_build_leading_stock_symbol_lookup", lambda: {"重庆银行": "601963"})
    monkeypatch.setattr(
        industry_endpoint,
        "_resolve_symbol_with_provider",
        lambda symbol: (_ for _ in ()).throw(AssertionError("symbol resolver should not run when lookup hit")),
    )

    leaders = industry_endpoint.get_leader_stocks(
        top_n=1,
        top_industries=1,
        per_industry=1,
        list_type="hot",
    )

    assert len(leaders) == 1
    assert leaders[0].symbol == "601963"
    assert leaders[0].name == "重庆银行"
    assert leaders[0].score_type == "hot"


def test_leader_boards_overview_reuses_shared_industry_ranking(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    analyzer = _CountingAnalyzer()
    monkeypatch.setattr(industry_endpoint, "get_industry_analyzer", lambda: analyzer)
    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _FakeScorer())

    app = FastAPI()
    app.include_router(industry_endpoint.router, prefix="/industry")
    client = TestClient(app)

    response = client.get(
        "/industry/leaders/overview",
        params={"top_n": 3, "top_industries": 1, "per_industry": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert analyzer.rank_calls == 1
    assert payload["errors"] == {}
    assert len(payload["core"]) == 1
    assert len(payload["hot"]) == 3
    assert payload["core"][0]["score_type"] == "core"
    assert all(item["score_type"] == "hot" for item in payload["hot"])


def test_leader_boards_overview_reuses_provider_stock_fetch_between_core_and_hot(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    analyzer = _CountingStockAnalyzer()
    monkeypatch.setattr(industry_endpoint, "get_industry_analyzer", lambda: analyzer)
    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _FakeScorer())

    app = FastAPI()
    app.include_router(industry_endpoint.router, prefix="/industry")
    client = TestClient(app)

    response = client.get(
        "/industry/leaders/overview",
        params={"top_n": 3, "top_industries": 1, "per_industry": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["core"]) == 1
    assert len(payload["hot"]) == 3
    assert analyzer.provider.calls == 1


def test_compute_core_leader_stocks_avoids_threadpool_for_local_snapshot_path(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    analyzer = _FakeAnalyzer()
    analyzer.provider = _SnapshotWarmupProvider()
    hot_industries = analyzer.rank_industries(top_n=1)

    def _threadpool_should_not_run(*args, **kwargs):
        raise AssertionError("core leader path should stay serial for local snapshots")

    monkeypatch.setattr(industry_endpoint, "ThreadPoolExecutor", _threadpool_should_not_run)
    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _FakeScorer())

    leaders = industry_endpoint._compute_core_leader_stocks(
        analyzer,
        hot_industries,
        top_n=2,
        per_industry=2,
        provider_stock_cache={},
        provider_stock_cache_lock=threading.Lock(),
    )

    assert len(leaders) == 1
    assert leaders[0].symbol == "000001"


def test_build_leading_stock_symbol_lookup_prefers_persistent_sina_list(monkeypatch):
    industry_endpoint._leading_stock_symbol_lookup_cache.clear()
    industry_endpoint._leading_stock_symbol_lookup_cache_time = 0

    persistent_df = pd.DataFrame(
        [
            {
                "industry_code": "new_test",
                "industry_name": "测试行业",
                "leading_stock_name": "重庆银行",
                "leading_stock_code": "sh601963",
            }
        ]
    )

    class _DeadSinaProvider:
        def get_industry_list(self):
            raise AssertionError("live sina industry list should not run when persistent cache exists")

    class _Provider:
        sina = _DeadSinaProvider()

    monkeypatch.setattr(industry_endpoint, "_get_or_create_provider", lambda: _Provider())
    monkeypatch.setattr(
        "src.data.providers.sina_provider.SinaFinanceProvider._load_persistent_industry_list",
        lambda: persistent_df,
    )

    lookup = industry_endpoint._build_leading_stock_symbol_lookup()

    assert lookup == {"重庆银行": "601963"}


def test_leader_boards_overview_schedules_snapshot_prewarm(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    analyzer = _CountingAnalyzer()
    scheduled = {}

    monkeypatch.setattr(industry_endpoint, "get_industry_analyzer", lambda: analyzer)
    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _FakeScorer())

    def _fake_schedule(analyzer_arg, hot_industries):
        scheduled["analyzer"] = analyzer_arg
        scheduled["hot_industries"] = hot_industries

    monkeypatch.setattr(industry_endpoint, "_schedule_leader_stock_snapshot_prewarm", _fake_schedule)

    app = FastAPI()
    app.include_router(industry_endpoint.router, prefix="/industry")
    client = TestClient(app)

    response = client.get(
        "/industry/leaders/overview",
        params={"top_n": 3, "top_industries": 1, "per_industry": 3},
    )

    assert response.status_code == 200
    assert scheduled["analyzer"] is analyzer
    assert scheduled["hot_industries"][0]["industry_name"] == "测试行业"


def test_prewarm_leader_stock_snapshot_uses_akshare_provider_when_cache_missing():
    analyzer = _FakeAnalyzer()
    analyzer.provider = _SnapshotWarmupProvider()

    industry_endpoint._prewarm_leader_stock_snapshot("测试行业", analyzer)

    assert analyzer.provider.akshare.persist_stock_list_snapshot.called
    assert analyzer.provider.akshare.cached_calls == 0
    assert analyzer.provider.akshare.live_calls == 0


def test_compute_hot_leader_stocks_backfills_from_provider_before_full_scorer(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    analyzer = _CountingStockAnalyzer()

    def _analyze_money_flow(days=1):
        return pd.DataFrame(
            [
                {
                    "industry_name": "测试行业",
                    "leading_stock": "未解析龙头",
                    "leading_stock_change": 9.8,
                    "main_net_ratio": 6.4,
                    "main_net_inflow": 120000000,
                    "change_pct": 4.2,
                }
            ]
        )

    analyzer.analyze_money_flow = _analyze_money_flow

    class _NoHeavyFallbackScorer(_FakeScorer):
        def get_leader_stocks(self, hot_industries, top_per_industry=5, score_type="hot"):
            raise AssertionError("full scorer fallback should not run when provider backfill is available")

    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _NoHeavyFallbackScorer())
    monkeypatch.setattr(industry_endpoint, "_build_leading_stock_symbol_lookup", lambda: {})
    monkeypatch.setattr(industry_endpoint, "_resolve_symbol_with_provider", lambda symbol: symbol)

    leaders = industry_endpoint._compute_hot_leader_stocks(
        analyzer=analyzer,
        hot_industries=[{"industry_name": "测试行业"}],
        top_industry_names={"测试行业"},
        top_n=1,
        per_industry=1,
    )

    assert len(leaders) == 1
    assert leaders[0].symbol == "000001"
    assert leaders[0].name == "测试行业龙头"
    assert analyzer.provider.calls == 1


def test_compute_hot_leader_stocks_prefers_lightweight_money_flow_loader(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    analyzer = _CountingStockAnalyzer()
    analyzer.analyze_money_flow = MagicMock(side_effect=AssertionError("full money flow should not run"))
    analyzer._load_lightweight_money_flow = MagicMock(
        return_value=pd.DataFrame(
            [
                {
                    "industry_name": "测试行业",
                    "leading_stock": "000001",
                    "leading_stock_change": 9.8,
                    "main_net_ratio": 6.4,
                    "main_net_inflow": 120000000,
                    "change_pct": 4.2,
                }
            ]
        )
    )

    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _FakeScorer())
    monkeypatch.setattr(industry_endpoint, "_build_leading_stock_symbol_lookup", lambda: {})
    monkeypatch.setattr(industry_endpoint, "_resolve_symbol_with_provider", lambda symbol: symbol)

    leaders = industry_endpoint._compute_hot_leader_stocks(
        analyzer=analyzer,
        hot_industries=[{"industry_name": "测试行业"}],
        top_industry_names={"测试行业"},
        top_n=1,
        per_industry=1,
    )

    assert len(leaders) == 1
    assert leaders[0].symbol == "000001"
    analyzer._load_lightweight_money_flow.assert_called_once_with(days=1)


def test_industry_bootstrap_reuses_shared_industry_ranking(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    analyzer = _CountingAnalyzer()
    monkeypatch.setattr(industry_endpoint, "get_industry_analyzer", lambda: analyzer)
    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _FakeScorer())
    monkeypatch.setattr(industry_endpoint, "_build_leading_stock_symbol_lookup", lambda: {"测试龙头": "000001"})
    industry_endpoint._set_endpoint_cache(
        industry_endpoint._get_leader_overview_cache_key(3, 1, 3),
        LeaderBoardsResponse(
            core=[
                LeaderStockResponse(
                    symbol="000001",
                    name="测试行业龙头",
                    industry="测试行业",
                    score_type="core",
                    global_rank=1,
                    industry_rank=1,
                    total_score=61.31,
                    market_cap=12_000_000_000,
                    pe_ratio=18.5,
                    change_pct=1.2,
                )
            ],
            hot=[
                LeaderStockResponse(
                    symbol="000001",
                    name="测试行业龙头",
                    industry="测试行业",
                    score_type="hot",
                    global_rank=1,
                    industry_rank=1,
                    total_score=97.2,
                    market_cap=12_000_000_000,
                    pe_ratio=18.5,
                    change_pct=9.8,
                )
            ],
        ),
    )

    app = FastAPI()
    app.include_router(industry_endpoint.router, prefix="/industry")
    client = TestClient(app)

    response = client.get(
        "/industry/bootstrap",
        params={"days": 5, "ranking_top_n": 20, "leader_top_n": 3, "top_industries": 1, "per_industry": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert analyzer.rank_calls == 1
    assert payload["errors"] == {}
    assert payload["heatmap"]["industries"][0]["name"] == "测试行业"
    assert len(payload["hot_industries"]) == 1
    assert len(payload["leaders"]["core"]) == 1
    assert len(payload["leaders"]["hot"]) == 1
    assert payload["leaders"]["core"][0]["symbol"] == "000001"


def test_industry_bootstrap_schedules_leader_warmup_when_overview_missing(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    analyzer = _CountingAnalyzer()
    scheduled = {}

    monkeypatch.setattr(industry_endpoint, "get_industry_analyzer", lambda: analyzer)
    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _FakeScorer())
    monkeypatch.setattr(industry_endpoint, "_build_leading_stock_symbol_lookup", lambda: {"测试龙头": "000001"})

    def _fake_schedule(**kwargs):
        scheduled["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(industry_endpoint, "_schedule_leader_overview_build", _fake_schedule)

    app = FastAPI()
    app.include_router(industry_endpoint.router, prefix="/industry")
    client = TestClient(app)

    response = client.get(
        "/industry/bootstrap",
        params={"days": 5, "ranking_top_n": 20, "leader_top_n": 3, "top_industries": 1, "per_industry": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert analyzer.rank_calls == 1
    assert payload["errors"] == {}
    assert payload["leaders"]["core"] == []
    assert payload["leaders"]["hot"] == []
    assert scheduled["kwargs"]["top_n"] == 3
    assert scheduled["kwargs"]["top_industries"] == 1
    assert scheduled["kwargs"]["per_industry"] == 3
    assert scheduled["kwargs"]["hot_industries"][0]["industry_name"] == "测试行业"


def test_industry_bootstrap_cached_partial_payload_hydrates_ready_leader_overview():
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    bootstrap_cache_key = "industry_bootstrap:v2:5:20:3:1:3"
    overview_cache_key = industry_endpoint._get_leader_overview_cache_key(3, 1, 3)

    industry_endpoint._set_endpoint_cache(
        bootstrap_cache_key,
        IndustryBootstrapResponse(
            days=5,
            ranking_top_n=20,
            ranking_type="gainers",
            ranking_sort_by="total_score",
            ranking_order="desc",
            heatmap={
                "industries": [
                    {
                        "name": "测试行业",
                        "value": 4.2,
                        "total_score": 91.2,
                        "size": 180000000000,
                        "stockCount": 2,
                        "moneyFlow": 120000000,
                        "turnoverRate": 3.1,
                        "industryVolatility": 1.2,
                        "industryVolatilitySource": "historical_index",
                        "netInflowRatio": 6.4,
                        "leadingStock": "测试龙头",
                        "leadingStockSymbol": "000001",
                        "sizeSource": "snapshot",
                        "marketCapSource": "snapshot_manual",
                        "marketCapSnapshotAgeHours": 2.0,
                        "marketCapSnapshotIsStale": False,
                        "valuationSource": "akshare_sw",
                        "valuationQuality": "industry_level",
                        "dataSources": ["ths"],
                        "industryIndex": 3210.5,
                        "totalInflow": 32.0,
                        "totalOutflow": 18.0,
                        "leadingStockChange": 9.8,
                        "leadingStockPrice": 18.6,
                        "pe_ttm": 16.8,
                        "pb": 2.1,
                        "dividend_yield": 1.2,
                    }
                ],
                "max_value": 4.2,
                "min_value": 4.2,
                "update_time": "2026-04-20T00:00:00",
            },
            hot_industries=[],
            leaders=LeaderBoardsResponse(),
            errors={"leaders": "龙头股榜单预热中"},
        ),
    )
    industry_endpoint._set_endpoint_cache(
        overview_cache_key,
        LeaderBoardsResponse(
            core=[
                LeaderStockResponse(
                    symbol="000001",
                    name="测试行业龙头",
                    industry="测试行业",
                    score_type="core",
                    global_rank=1,
                    industry_rank=1,
                    total_score=61.31,
                    market_cap=12_000_000_000,
                    pe_ratio=18.5,
                    change_pct=1.2,
                )
            ],
            hot=[
                LeaderStockResponse(
                    symbol="000001",
                    name="测试行业龙头",
                    industry="测试行业",
                    score_type="hot",
                    global_rank=1,
                    industry_rank=1,
                    total_score=97.2,
                    market_cap=12_000_000_000,
                    pe_ratio=18.5,
                    change_pct=9.8,
                )
            ],
        ),
    )

    app = FastAPI()
    app.include_router(industry_endpoint.router, prefix="/industry")
    client = TestClient(app)

    response = client.get(
        "/industry/bootstrap",
        params={"days": 5, "ranking_top_n": 20, "leader_top_n": 3, "top_industries": 1, "per_industry": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["errors"] == {}
    assert len(payload["leaders"]["core"]) == 1
    assert len(payload["leaders"]["hot"]) == 1
    hydrated = industry_endpoint._get_endpoint_cache(bootstrap_cache_key)
    assert hydrated is not None
    assert len(hydrated.leaders.core) == 1
    assert len(hydrated.leaders.hot) == 1


def test_leader_stocks_rejects_invalid_list_type():
    app = FastAPI()
    app.include_router(industry_endpoint.router, prefix="/industry")
    client = TestClient(app)

    response = client.get("/industry/leaders", params={"list_type": "weird"})

    assert response.status_code == 422


def test_leader_detail_rejects_invalid_score_type():
    app = FastAPI()
    app.include_router(industry_endpoint.router, prefix="/industry")
    client = TestClient(app)

    response = client.get("/industry/leaders/000001/detail", params={"score_type": "weird"})

    assert response.status_code == 422


def test_leader_detail_preserves_real_fundamentals_when_parity_snapshot_is_sparse(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _FakeScorer())
    monkeypatch.setattr(industry_endpoint, "_resolve_symbol_with_provider", lambda symbol: symbol)

    industry_endpoint._set_parity_cache(
        "000001",
        "hot",
        LeaderStockResponse(
            symbol="000001",
            name="榜单股票",
            industry="测试行业",
            score_type="hot",
            global_rank=1,
            industry_rank=1,
            total_score=97.2,
            market_cap=0,
            pe_ratio=0,
            change_pct=0,
            dimension_scores={"score_type": "hot", "momentum": 0.97, "money_flow": 0.83},
        ),
    )

    detail = industry_endpoint.get_leader_detail("000001", score_type="hot")

    assert detail.total_score == 97.2
    assert detail.dimension_scores["score_type"] == "hot"
    assert detail.raw_data["market_cap"] == 15_688_999_999.99
    assert detail.raw_data["pe_ttm"] == 30.1
    assert detail.raw_data["change_pct"] == 13.32


class _TransientLeaderDetailScorer:
    def get_leader_detail(self, symbol, score_type="core"):
        return {"symbol": symbol, "error": "Remote end closed connection without response"}


def test_leader_detail_uses_parity_name_match_as_degraded_fallback(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _TransientLeaderDetailScorer())
    monkeypatch.setattr(industry_endpoint, "_resolve_symbol_with_provider", lambda symbol: symbol)

    industry_endpoint._set_parity_cache(
        "601963",
        "hot",
        LeaderStockResponse(
            symbol="601963",
            name="重庆银行",
            industry="银行",
            score_type="hot",
            global_rank=1,
            industry_rank=1,
            total_score=81.6,
            market_cap=125_000_000_000,
            pe_ratio=6.4,
            change_pct=2.18,
            dimension_scores={"score_type": "hot", "momentum": 0.81, "money_flow": 0.72},
            mini_trend=[10.1, 10.3, 10.4, 10.25],
        ),
    )

    detail = industry_endpoint.get_leader_detail("重庆银行", score_type="hot")

    assert detail.symbol == "601963"
    assert detail.name == "重庆银行"
    assert detail.degraded is True
    assert "榜单快照" in (detail.note or "")
    assert detail.raw_data["source"] == "leader_parity_cache"
    assert len(detail.price_data) >= 2


def test_leader_detail_returns_502_for_transient_upstream_error_without_parity(monkeypatch):
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._parity_cache.clear()

    monkeypatch.setattr(industry_endpoint, "get_leader_scorer", lambda: _TransientLeaderDetailScorer())
    monkeypatch.setattr(industry_endpoint, "_resolve_symbol_with_provider", lambda symbol: symbol)

    with pytest.raises(HTTPException) as excinfo:
        industry_endpoint.get_leader_detail("重庆银行", score_type="hot")

    assert excinfo.value.status_code == 502


class _SparseIndustryScorer:
    def __init__(self, ranked_stocks):
        self._ranked_stocks = ranked_stocks

    def rank_stocks_in_industry(self, industry_name, top_n=20):
        return self._ranked_stocks[:top_n]


class _IndustryDetailProvider:
    def __init__(self, stocks, valuations=None):
        self._stocks = stocks
        self._valuations = valuations or {}

    def get_stock_list_by_industry(self, industry_name):
        return self._stocks

    def get_stock_valuation(self, symbol):
        return self._valuations.get(symbol, {"symbol": symbol, "error": "not found"})


def _clear_stock_endpoint_state():
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._stocks_full_build_inflight.clear()


def test_get_industry_stocks_returns_quick_provider_rows_and_schedules_full_build(monkeypatch):
    _clear_stock_endpoint_state()

    provider_stocks = [
        {
            "symbol": "600036",
            "name": "招商银行",
            "market_cap": 1_020_000_000_000,
            "pe_ratio": 7.3,
            "change_pct": 1.26,
        },
        {
            "symbol": "601288",
            "name": "农业银行",
            "market_cap": 1_510_000_000_000,
            "pe_ratio": 6.8,
            "change_pct": 0.54,
        },
    ]
    scheduled = []

    class _FailIfRankCalledScorer:
        def rank_stocks_in_industry(self, *args, **kwargs):
            raise AssertionError("full ranking should not run in quick path")

        def calculate_industry_stats(self, stocks):
            return {"count": len(stocks), "avg_market_cap": 0, "median_market_cap": 0, "avg_pe": 0, "median_pe": 0}

        def score_stock_from_industry_snapshot(self, stock, industry_stats, score_type="core"):
            score_map = {
                "600036": 88.2,
                "601288": 76.4,
            }
            return {
                "symbol": stock["symbol"],
                "name": stock["name"],
                "total_score": score_map[stock["symbol"]],
            }

    monkeypatch.setattr(
        industry_endpoint,
        "_get_or_create_provider",
        lambda: _IndustryDetailProvider(provider_stocks),
    )
    monkeypatch.setattr(
        industry_endpoint,
        "get_leader_scorer",
        lambda: _FailIfRankCalledScorer(),
    )
    monkeypatch.setattr(
        industry_endpoint,
        "_schedule_full_stock_cache_build",
        lambda industry_name, top_n: scheduled.append((industry_name, top_n)),
    )

    stocks = industry_endpoint.get_industry_stocks("银行", top_n=20)

    assert [stock.symbol for stock in stocks[:2]] == ["600036", "601288"]
    assert [stock.rank for stock in stocks[:2]] == [1, 2]
    assert [stock.total_score for stock in stocks[:2]] == [88.2, 76.4]
    assert [stock.scoreStage for stock in stocks[:2]] == ["quick", "quick"]
    assert stocks[0].market_cap == 1_020_000_000_000
    assert stocks[0].pe_ratio == 7.3
    assert stocks[0].change_pct == 1.26
    assert stocks[1].market_cap == 1_510_000_000_000
    assert scheduled == [("银行", 20)]


def test_get_industry_stocks_quick_path_promotes_detail_ready_rows_into_first_screen(monkeypatch):
    _clear_stock_endpoint_state()

    provider_stocks = [
        {"symbol": "000001", "name": "高分无明细A"},
        {"symbol": "000002", "name": "高分无明细B"},
        {"symbol": "000003", "name": "高分无明细C"},
        {"symbol": "000004", "name": "高分无明细D"},
        {"symbol": "000005", "name": "高分无明细E"},
        {"symbol": "000006", "name": "有明细F"},
        {"symbol": "000007", "name": "有明细G"},
    ]
    valuations = {
        "000006": {"symbol": "000006", "market_cap": 320_000_000_000, "pe_ratio": 18.3, "change_pct": 1.2},
        "000007": {"symbol": "000007", "market_cap": 280_000_000_000, "pe_ratio": 16.9, "change_pct": -0.6},
    }

    class _QuickScoreScorer:
        def calculate_industry_stats(self, stocks):
            return {"count": len(stocks), "avg_market_cap": 0, "median_market_cap": 0, "avg_pe": 0, "median_pe": 0}

        def score_stock_from_industry_snapshot(self, stock, industry_stats, score_type="core"):
            score_map = {
                "000001": 99,
                "000002": 97,
                "000003": 95,
                "000004": 93,
                "000005": 91,
                "000006": 89,
                "000007": 87,
            }
            return {
                "symbol": stock["symbol"],
                "name": stock["name"],
                "total_score": score_map[stock["symbol"]],
            }

    monkeypatch.setattr(
        industry_endpoint,
        "_get_or_create_provider",
        lambda: _IndustryDetailProvider(provider_stocks, valuations=valuations),
    )
    monkeypatch.setattr(
        industry_endpoint,
        "get_leader_scorer",
        lambda: _QuickScoreScorer(),
    )
    monkeypatch.setattr(
        industry_endpoint,
        "_schedule_full_stock_cache_build",
        lambda industry_name, top_n: None,
    )

    stocks = industry_endpoint.get_industry_stocks("银行", top_n=7)

    first_screen = stocks[:5]
    assert sum(1 for stock in first_screen if stock.market_cap is not None or stock.pe_ratio is not None) >= 2
    assert {stock.symbol for stock in first_screen}.issuperset({"000006", "000007"})


def test_get_industry_stocks_prefers_cached_provider_snapshot_before_live_fetch(monkeypatch):
    _clear_stock_endpoint_state()

    cached_provider_stocks = [
        {
            "symbol": "688981",
            "name": "中芯国际",
            "market_cap": 420_000_000_000,
            "pe_ratio": 52.7,
            "change_pct": 1.8,
        },
        {
            "symbol": "603986",
            "name": "兆易创新",
            "market_cap": 96_000_000_000,
            "pe_ratio": 34.2,
            "change_pct": 0.7,
        },
    ]
    scheduled = []

    class _CachedSnapshotProvider(_IndustryDetailProvider):
        def get_cached_stock_list_by_industry(self, industry_name):
            return cached_provider_stocks

        def get_stock_list_by_industry(self, industry_name):
            raise AssertionError("live provider fetch should be deferred to background build")

        def get_stock_valuation(self, symbol):
            raise AssertionError("cached snapshot quick path should not trigger valuation backfill")

    class _CachedQuickScorer:
        def calculate_industry_stats(self, stocks):
            return {"count": len(stocks), "avg_market_cap": 0, "median_market_cap": 0, "avg_pe": 0, "median_pe": 0}

        def score_stock_from_industry_snapshot(self, stock, industry_stats, score_type="core"):
            score_map = {
                "688981": 96.5,
                "603986": 89.1,
            }
            return {
                "symbol": stock["symbol"],
                "name": stock["name"],
                "total_score": score_map[stock["symbol"]],
            }

    monkeypatch.setattr(
        industry_endpoint,
        "_get_or_create_provider",
        lambda: _CachedSnapshotProvider([]),
    )
    monkeypatch.setattr(
        industry_endpoint,
        "get_leader_scorer",
        lambda: _CachedQuickScorer(),
    )
    monkeypatch.setattr(
        industry_endpoint,
        "_schedule_full_stock_cache_build",
        lambda industry_name, top_n: scheduled.append((industry_name, top_n)),
    )

    stocks = industry_endpoint.get_industry_stocks("半导体", top_n=20)

    assert [stock.symbol for stock in stocks[:2]] == ["688981", "603986"]
    assert [stock.scoreStage for stock in stocks[:2]] == ["quick", "quick"]
    assert [stock.total_score for stock in stocks[:2]] == [96.5, 89.1]
    assert scheduled == [("半导体", 20)]


def test_get_industry_stocks_prefers_full_cache_when_available(monkeypatch):
    _clear_stock_endpoint_state()

    full_key = industry_endpoint._get_stock_cache_keys("半导体", 20)[1]
    cached_rows = [
        industry_endpoint.StockResponse(
            symbol="688981",
            name="中芯国际",
            rank=1,
            total_score=96.5,
            scoreStage="full",
            market_cap=420_000_000_000,
            pe_ratio=52.7,
            change_pct=-0.85,
            industry="半导体",
        )
    ]
    industry_endpoint._set_endpoint_cache(full_key, cached_rows)

    monkeypatch.setattr(
        industry_endpoint,
        "_get_or_create_provider",
        lambda: pytest.fail("provider should not be called when full cache exists"),
    )

    stocks = industry_endpoint.get_industry_stocks("半导体", top_n=20)

    assert len(stocks) == 1
    assert stocks[0].symbol == "688981"
    assert stocks[0].total_score == 96.5
    assert stocks[0].scoreStage == "full"


def test_build_full_industry_stock_response_merges_provider_details_into_ranked_results(monkeypatch):
    _clear_stock_endpoint_state()

    ranked_stocks = [
        {
            "symbol": "600036",
            "name": "招商银行",
            "rank": 1,
            "total_score": 98.2,
            "market_cap": 0,
            "pe_ratio": 0,
            "change_pct": 0,
        },
        {
            "symbol": "601288",
            "name": "农业银行",
            "rank": 2,
            "total_score": 92.4,
            "market_cap": 0,
            "pe_ratio": 0,
            "change_pct": 0,
        },
    ]
    provider_stocks = [
        {
            "symbol": "600036",
            "name": "招商银行",
            "market_cap": 1_020_000_000_000,
            "pe_ratio": 7.3,
            "change_pct": 1.26,
        },
        {
            "symbol": "601288",
            "name": "农业银行",
            "market_cap": 1_510_000_000_000,
            "pe_ratio": 6.8,
            "change_pct": 0.54,
        },
    ]

    monkeypatch.setattr(
        industry_endpoint,
        "get_leader_scorer",
        lambda: _SparseIndustryScorer(ranked_stocks),
    )
    monkeypatch.setattr(
        industry_endpoint,
        "_get_or_create_provider",
        lambda: _IndustryDetailProvider(provider_stocks),
    )

    stocks = industry_endpoint._build_full_industry_stock_response("银行", top_n=20)

    assert [stock.symbol for stock in stocks[:2]] == ["600036", "601288"]
    assert [stock.rank for stock in stocks[:2]] == [1, 2]
    assert [stock.total_score for stock in stocks[:2]] == [98.2, 92.4]
    assert [stock.scoreStage for stock in stocks[:2]] == ["full", "full"]
    assert stocks[0].market_cap == 1_020_000_000_000
    assert stocks[0].pe_ratio == 7.3
    assert stocks[0].change_pct == 1.26
    assert stocks[1].market_cap == 1_510_000_000_000


def test_build_full_industry_stock_response_keeps_sparse_ranked_fields_nullable_when_provider_is_partial(monkeypatch):
    _clear_stock_endpoint_state()

    ranked_stocks = [
        {
            "symbol": "688981",
            "name": "中芯国际",
            "rank": 1,
            "total_score": 96.5,
            "market_cap": 0,
            "pe_ratio": 0,
            "change_pct": 0,
        },
        {
            "symbol": "603986",
            "name": "兆易创新",
            "rank": 2,
            "total_score": 90.1,
            "market_cap": 0,
            "pe_ratio": 0,
            "change_pct": 0,
        },
    ]
    provider_stocks = [
        {
            "symbol": "688981",
            "name": "中芯国际",
            "market_cap": 420_000_000_000,
            "pe_ratio": 52.7,
            "change_pct": -0.85,
        }
    ]

    monkeypatch.setattr(
        industry_endpoint,
        "get_leader_scorer",
        lambda: _SparseIndustryScorer(ranked_stocks),
    )
    monkeypatch.setattr(
        industry_endpoint,
        "_get_or_create_provider",
        lambda: _IndustryDetailProvider(provider_stocks),
    )

    stocks = industry_endpoint._build_full_industry_stock_response("半导体", top_n=20)

    assert stocks[0].market_cap == 420_000_000_000
    assert stocks[0].pe_ratio == 52.7
    assert stocks[0].change_pct == -0.85
    assert stocks[1].symbol == "603986"
    assert stocks[1].market_cap is None
    assert stocks[1].pe_ratio is None
    assert stocks[1].change_pct == 0


def test_get_industry_stocks_falls_back_to_full_build_when_provider_is_empty(monkeypatch):
    _clear_stock_endpoint_state()

    full_rows = [
        industry_endpoint.StockResponse(
            symbol="600196",
            name="复星医药",
            rank=1,
            total_score=88.0,
            scoreStage="full",
            market_cap=68_000_000_000,
            pe_ratio=21.5,
            change_pct=1.08,
            industry="医药生物",
        )
    ]

    monkeypatch.setattr(industry_endpoint, "_get_or_create_provider", lambda: _IndustryDetailProvider([]))
    monkeypatch.setattr(
        industry_endpoint,
        "_build_full_industry_stock_response",
        lambda industry_name, top_n, provider=None: full_rows,
    )

    stocks = industry_endpoint.get_industry_stocks("医药生物", top_n=20)

    assert len(stocks) == 1
    assert stocks[0].symbol == "600196"
    assert stocks[0].total_score == 88.0
    assert stocks[0].scoreStage == "full"


def test_build_full_industry_stock_response_backfills_missing_market_cap_with_symbol_valuation(monkeypatch):
    _clear_stock_endpoint_state()

    ranked_stocks = [
        {
            "symbol": "600036",
            "name": "招商银行",
            "rank": 1,
            "total_score": 98.2,
            "market_cap": 0,
            "pe_ratio": 6.68,
            "change_pct": 0.66,
        }
    ]
    provider_stocks = [
        {
            "symbol": "600036",
            "name": "招商银行",
            "market_cap": 0,
            "pe_ratio": 6.68,
            "change_pct": 0.66,
        }
    ]
    valuations = {
        "600036": {
            "symbol": "600036",
            "market_cap": 1_002_741_061_096,
            "pe_ttm": 6.68,
            "change_pct": 0.66,
        }
    }

    monkeypatch.setattr(
        industry_endpoint,
        "get_leader_scorer",
        lambda: _SparseIndustryScorer(ranked_stocks),
    )
    monkeypatch.setattr(
        industry_endpoint,
        "_get_or_create_provider",
        lambda: _IndustryDetailProvider(provider_stocks, valuations=valuations),
    )

    stocks = industry_endpoint._build_full_industry_stock_response("银行", top_n=20)

    assert len(stocks) == 1
    assert stocks[0].market_cap == 1_002_741_061_096
    assert stocks[0].pe_ratio == 6.68
    assert stocks[0].change_pct == 0.66


def test_get_industry_trend_realigns_degraded_summary_with_stock_rows(monkeypatch):
    _clear_stock_endpoint_state()

    aligned_rows = [
        {
            "symbol": "002155",
            "name": "高置信样本A",
            "market_cap": 47_100_000_000,
            "pe_ratio": 31.7,
            "change_pct": 5.6,
            "money_flow": 2_005_409_613,
        },
        {
            "symbol": "000960",
            "name": "高置信样本B",
            "market_cap": 41_800_000_000,
            "pe_ratio": 22.4,
            "change_pct": 2.1,
            "money_flow": 1_203_000_000,
        },
        {
            "symbol": "002460",
            "name": "高置信样本C",
            "market_cap": 38_200_000_000,
            "pe_ratio": 18.2,
            "change_pct": -1.3,
            "money_flow": -306_000_000,
        },
        {
            "symbol": "002466",
            "name": "高置信样本D",
            "market_cap": 35_600_000_000,
            "pe_ratio": 19.8,
            "change_pct": 0.7,
            "money_flow": 210_000_000,
        },
        {
            "symbol": "603799",
            "name": "高置信样本E",
            "market_cap": 29_300_000_000,
            "pe_ratio": 24.3,
            "change_pct": 0.4,
            "money_flow": 82_000_000,
        },
    ]

    class _TrendAnalyzer:
        provider = _IndustryDetailProvider([])

        def get_industry_trend(self, industry_name, days=30):
            return {
                "industry_name": industry_name,
                "stock_count": 1,
                "expected_stock_count": 12,
                "total_market_cap": 26_100_000_000,
                "avg_pe": 47.1,
                "industry_volatility": 7.71,
                "industry_volatility_source": "turnover_rate_proxy",
                "period_days": days,
                "period_change_pct": 21.25,
                "period_money_flow": -2_003_000_000,
                "top_gainers": [{"name": "旧样本", "change_pct": 7.18}],
                "top_losers": [{"name": "旧样本", "change_pct": 7.18}],
                "rise_count": 1,
                "fall_count": 0,
                "flat_count": 0,
                "stock_coverage_ratio": 0.0833,
                "change_coverage_ratio": 0.0833,
                "market_cap_coverage_ratio": 0.0833,
                "pe_coverage_ratio": 0.0833,
                "total_market_cap_fallback": True,
                "avg_pe_fallback": False,
                "market_cap_source": "akshare_metadata",
                "valuation_source": "unavailable",
                "valuation_quality": "unavailable",
                "trend_series": [],
                "degraded": True,
                "note": "成分股列表可能不完整（获取到 1 只，预期约 12 只）。当前展示可能存在偏差。",
                "update_time": "2026-04-17T22:00:00",
            }

    monkeypatch.setattr(industry_endpoint, "get_industry_analyzer", lambda: _TrendAnalyzer())
    monkeypatch.setattr(
        industry_endpoint,
        "_load_trend_alignment_stock_rows",
        lambda industry_name, expected_count, provider=None: aligned_rows,
    )

    result = industry_endpoint.get_industry_trend("能源金属", days=30)

    assert result.degraded is False
    assert result.note is None
    assert result.stock_count == len(aligned_rows)
    assert result.stock_coverage_ratio == round(len(aligned_rows) / 12, 4)
    assert result.top_gainers[0]["name"] == "高置信样本A"
    assert result.top_losers[0]["name"] == "高置信样本C"


def test_get_industry_trend_realigns_overbroad_summary_with_stock_rows(monkeypatch):
    _clear_stock_endpoint_state()

    aligned_rows = [
        {
            "symbol": "000807",
            "name": "云铝股份",
            "market_cap": 127_169_998_041.35,
            "pe_ratio": 20.954,
            "change_pct": 0.686,
            "money_flow": 1_630_263_972,
        },
        {
            "symbol": "002155",
            "name": "湖南黄金",
            "market_cap": 47_113_937_177.4,
            "pe_ratio": 31.737,
            "change_pct": 1.379,
            "money_flow": 2_005_409_613,
        },
        {
            "symbol": "000960",
            "name": "锡业股份",
            "market_cap": 28_800_000_000,
            "pe_ratio": 18.6,
            "change_pct": 1.102,
            "money_flow": 530_000_000,
        },
        {
            "symbol": "600549",
            "name": "厦门钨业",
            "market_cap": 29_700_000_000,
            "pe_ratio": 24.2,
            "change_pct": -0.812,
            "money_flow": -106_000_000,
        },
    ]

    class _TrendAnalyzer:
        provider = _IndustryDetailProvider([])

        def get_industry_trend(self, industry_name, days=30):
            return {
                "industry_name": industry_name,
                "stock_count": 50,
                "expected_stock_count": 12,
                "total_market_cap": 1_568_287_155_717.5,
                "avg_pe": 32.83,
                "industry_volatility": 7.71,
                "industry_volatility_source": "turnover_rate_proxy",
                "period_days": days,
                "period_change_pct": 21.25,
                "period_money_flow": -2_003_000_000,
                "top_gainers": [{"name": "株冶集团", "change_pct": 10.01}],
                "top_losers": [{"name": "旧宽口径样本", "change_pct": -9.2}],
                "rise_count": 32,
                "fall_count": 18,
                "flat_count": 0,
                "stock_coverage_ratio": 1.0,
                "change_coverage_ratio": 1.0,
                "market_cap_coverage_ratio": 1.0,
                "pe_coverage_ratio": 1.0,
                "total_market_cap_fallback": False,
                "avg_pe_fallback": False,
                "market_cap_source": "akshare_metadata",
                "valuation_source": "unavailable",
                "valuation_quality": "unavailable",
                "trend_series": [],
                "degraded": False,
                "note": None,
                "update_time": "2026-04-17T22:00:00",
            }

    monkeypatch.setattr(industry_endpoint, "get_industry_analyzer", lambda: _TrendAnalyzer())
    monkeypatch.setattr(
        industry_endpoint,
        "_load_trend_alignment_stock_rows",
        lambda industry_name, expected_count, provider=None: aligned_rows,
    )

    result = industry_endpoint.get_industry_trend("能源金属", days=30)

    assert result.degraded is False
    assert result.stock_count == len(aligned_rows)
    assert result.top_gainers[0]["name"] == "湖南黄金"
    assert result.top_losers[0]["name"] == "厦门钨业"
    assert result.rise_count == 3
    assert result.fall_count == 1
