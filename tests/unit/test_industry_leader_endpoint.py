from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app.api.v1.endpoints import industry as industry_endpoint
from backend.app.schemas.industry import LeaderStockResponse
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


class _FakeAnalyzer:
    def __init__(self):
        self.provider = _FakeProvider()

    def rank_industries(self, top_n=5):
        return [{"industry_name": "测试行业"}]

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
