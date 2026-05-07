from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.app.api.v1.endpoints import industry as industry_endpoint


def _clear_rotation_endpoint_state() -> None:
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._stocks_full_build_inflight.clear()


def test_hot_industries_preserves_stale_cache_for_runtime_errors(monkeypatch):
    _clear_rotation_endpoint_state()
    stale = [
        industry_endpoint.IndustryRankResponse(
            rank=1,
            industry_name="缓存行业",
            score=88.0,
        )
    ]
    industry_endpoint._endpoint_cache["hot:v3:10:5:total_score:desc"] = {
        "data": stale,
        "ts": 0,
    }

    class _RuntimeFailingAnalyzer:
        def rank_industries(self, **kwargs):
            raise RuntimeError("ranking feed offline")

    monkeypatch.setattr(
        industry_endpoint,
        "get_industry_analyzer",
        lambda: _RuntimeFailingAnalyzer(),
    )

    assert (
        industry_endpoint.get_hot_industries(
            top_n=10,
            lookback_days=5,
            sort_by="total_score",
            order="desc",
        )
        == stale
    )


def test_hot_industries_does_not_mask_programmer_assertions(monkeypatch):
    _clear_rotation_endpoint_state()

    class _BuggyAnalyzer:
        def rank_industries(self, **kwargs):
            raise AssertionError("rank response contract drift")

    monkeypatch.setattr(industry_endpoint, "get_industry_analyzer", lambda: _BuggyAnalyzer())

    with pytest.raises(AssertionError, match="rank response contract drift"):
        industry_endpoint.get_hot_industries(
            top_n=10,
            lookback_days=5,
            sort_by="total_score",
            order="desc",
        )


def test_industry_stocks_cached_loader_runtime_error_keeps_live_fallback(monkeypatch):
    _clear_rotation_endpoint_state()
    quick_rows = [
        industry_endpoint.StockResponse(
            symbol="600036",
            name="招商银行",
            rank=1,
            total_score=88.0,
            scoreStage="quick",
            industry="银行",
        )
    ]

    class _TransientCachedProvider:
        def get_cached_stock_list_by_industry(self, *args, **kwargs):
            raise RuntimeError("snapshot cache temporarily unavailable")

        def get_stock_list_by_industry(self, industry_name):
            return [{"symbol": "600036", "name": "招商银行"}]

    monkeypatch.setattr(
        industry_endpoint,
        "_get_or_create_provider",
        lambda: _TransientCachedProvider(),
    )
    monkeypatch.setattr(
        industry_endpoint,
        "_build_quick_industry_stock_response",
        lambda *args, **kwargs: quick_rows,
    )
    monkeypatch.setattr(
        industry_endpoint,
        "_schedule_full_stock_cache_build",
        lambda industry_name, top_n: None,
    )

    assert industry_endpoint.get_industry_stocks("银行", top_n=20) == quick_rows


def test_industry_stocks_cached_loader_does_not_mask_programmer_assertions(monkeypatch):
    _clear_rotation_endpoint_state()

    class _BuggyCachedProvider:
        def get_cached_stock_list_by_industry(self, *args, **kwargs):
            raise AssertionError("cached stock loader contract drift")

        def get_stock_list_by_industry(self, industry_name):
            return []

    monkeypatch.setattr(
        industry_endpoint,
        "_get_or_create_provider",
        lambda: _BuggyCachedProvider(),
    )
    monkeypatch.setattr(
        industry_endpoint,
        "_build_full_industry_stock_response",
        lambda *args, **kwargs: [],
    )

    with pytest.raises(AssertionError, match="cached stock loader contract drift"):
        industry_endpoint.get_industry_stocks("银行", top_n=20)


def test_industry_stocks_live_fetch_does_not_mask_programmer_assertions(monkeypatch):
    _clear_rotation_endpoint_state()

    class _BuggyLiveProvider:
        def get_stock_list_by_industry(self, industry_name):
            raise AssertionError("live stock fetch contract drift")

    monkeypatch.setattr(
        industry_endpoint,
        "_get_or_create_provider",
        lambda: _BuggyLiveProvider(),
    )

    with pytest.raises(AssertionError, match="live stock fetch contract drift"):
        industry_endpoint.get_industry_stocks("银行", top_n=20)


def test_industry_trend_preserves_stale_cache_for_runtime_errors(monkeypatch):
    _clear_rotation_endpoint_state()
    stale = industry_endpoint.IndustryTrendResponse(
        industry_name="缓存行业",
        stock_count=3,
        update_time="2026-05-07T00:00:00",
    )
    industry_endpoint._endpoint_cache["trend:v5:银行:30"] = {
        "data": stale,
        "ts": 0,
    }

    class _RuntimeFailingAnalyzer:
        def get_industry_trend(self, industry_name, days=30):
            raise RuntimeError("trend feed offline")

    monkeypatch.setattr(
        industry_endpoint,
        "get_industry_analyzer",
        lambda: _RuntimeFailingAnalyzer(),
    )

    assert industry_endpoint.get_industry_trend("银行", days=30) == stale


def test_industry_trend_does_not_mask_programmer_assertions(monkeypatch):
    _clear_rotation_endpoint_state()

    class _BuggyAnalyzer:
        def get_industry_trend(self, industry_name, days=30):
            raise AssertionError("trend response contract drift")

    monkeypatch.setattr(industry_endpoint, "get_industry_analyzer", lambda: _BuggyAnalyzer())

    with pytest.raises(AssertionError, match="trend response contract drift"):
        industry_endpoint.get_industry_trend("银行", days=30)


def test_industry_clusters_preserves_generic_500_for_runtime_errors(monkeypatch):
    _clear_rotation_endpoint_state()

    class _RuntimeFailingAnalyzer:
        def cluster_hot_industries(self, n_clusters=4):
            raise RuntimeError("cluster engine offline")

    monkeypatch.setattr(
        industry_endpoint,
        "get_industry_analyzer",
        lambda: _RuntimeFailingAnalyzer(),
    )

    with pytest.raises(HTTPException) as excinfo:
        industry_endpoint.get_industry_clusters(n_clusters=4)

    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == "cluster engine offline"


def test_industry_clusters_does_not_mask_programmer_assertions(monkeypatch):
    _clear_rotation_endpoint_state()

    class _BuggyAnalyzer:
        def cluster_hot_industries(self, n_clusters=4):
            raise AssertionError("cluster response contract drift")

    monkeypatch.setattr(industry_endpoint, "get_industry_analyzer", lambda: _BuggyAnalyzer())

    with pytest.raises(AssertionError, match="cluster response contract drift"):
        industry_endpoint.get_industry_clusters(n_clusters=4)
