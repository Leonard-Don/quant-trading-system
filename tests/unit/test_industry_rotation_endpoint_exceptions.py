from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import industry as industry_endpoint
from backend.app.api.v1.endpoints.industry import rotation as rotation_endpoint


def _clear_rotation_endpoint_state() -> None:
    industry_endpoint._endpoint_cache.clear()
    industry_endpoint._stocks_full_build_inflight.clear()


def _client_for_rotation_endpoint() -> TestClient:
    app = FastAPI()
    app.include_router(rotation_endpoint.router, prefix="/industry")
    return TestClient(app)


def test_hot_industries_preserves_stale_cache_for_runtime_errors(monkeypatch):
    _clear_rotation_endpoint_state()
    stale = [
        industry_endpoint.IndustryRankResponse(
            rank=1,
            industry_name="缓存行业",
            score=88.0,
        )
    ]
    industry_endpoint._endpoint_cache["hot:v3:10:5:total_score:desc:policy=0"] = {
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


def test_industry_trend_degrades_when_no_stocks_are_found(monkeypatch):
    _clear_rotation_endpoint_state()

    class _NoStocksAnalyzer:
        def get_industry_trend(self, industry_name, days=30):
            return {"error": f"No stocks found for industry: {industry_name}"}

    monkeypatch.setattr(
        industry_endpoint,
        "get_industry_analyzer",
        lambda: _NoStocksAnalyzer(),
    )

    result = industry_endpoint.get_industry_trend("电子化学品", days=30)

    assert result.industry_name == "电子化学品"
    assert result.stock_count == 0
    assert result.period_days == 30
    assert result.degraded is True
    assert "成分股" in (result.note or "")


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


def test_policy_signal_overlay_degrades_for_operational_runtime_errors(monkeypatch):
    _clear_rotation_endpoint_state()

    class _RuntimeFailingAltManager:
        def get_alt_signals(self, **kwargs):
            raise RuntimeError("alt snapshot store offline")

    monkeypatch.setattr(
        "src.data.alternative.runtime.get_alt_data_manager",
        lambda: _RuntimeFailingAltManager(),
    )

    assert rotation_endpoint._load_policy_signal_overlay() == ({}, None)


def test_policy_signal_overlay_does_not_mask_programmer_assertions(monkeypatch):
    _clear_rotation_endpoint_state()

    class _BuggyAltManager:
        def get_alt_signals(self, **kwargs):
            raise AssertionError("policy overlay contract drift")

    monkeypatch.setattr(
        "src.data.alternative.runtime.get_alt_data_manager",
        lambda: _BuggyAltManager(),
    )

    with pytest.raises(AssertionError, match="policy overlay contract drift"):
        rotation_endpoint._load_policy_signal_overlay()


def test_policy_signal_overlay_does_not_mask_attribute_contract_errors(monkeypatch):
    _clear_rotation_endpoint_state()

    class _BuggyAltManager:
        def get_alt_signals(self, **kwargs):
            raise AttributeError("policy signal envelope missing expected API")

    monkeypatch.setattr(
        "src.data.alternative.runtime.get_alt_data_manager",
        lambda: _BuggyAltManager(),
    )

    with pytest.raises(AttributeError, match="missing expected API"):
        rotation_endpoint._load_policy_signal_overlay()


# ============================================================
# include_policy_signal coverage (policy_radar surfacing in
# industry ranking — see docs/CHANGELOG.md Unreleased).
# ============================================================


class _StubRankingAnalyzer:
    """Minimal analyzer that returns two ranking rows. Mirrors the dict
    shape ``_build_hot_industry_rank_responses`` consumes."""

    def __init__(self, rows):
        self._rows = rows

    def rank_industries(self, **kwargs):
        return list(self._rows)

    def build_rank_score_breakdown(self, record):
        # Returning [] keeps the schema valid without dragging the full
        # breakdown calculator into the test fixture.
        return []


def test_hot_industries_include_policy_signal_attaches_policy_radar_payload(monkeypatch):
    """include_policy_signal=true joins policy_radar industry_signals onto each row.

    Verifies the happy path: matched industry gets the full nested object;
    unmatched industry gets ``policy_signal=None``.
    """
    _clear_rotation_endpoint_state()

    rows = [
        {
            "rank": 1,
            "industry_name": "新能源汽车",
            "score": 88.0,
            "change_pct": 2.5,
        },
        {
            "rank": 2,
            "industry_name": "无政策覆盖行业",
            "score": 77.0,
            "change_pct": 1.0,
        },
    ]
    monkeypatch.setattr(
        industry_endpoint,
        "get_industry_analyzer",
        lambda: _StubRankingAnalyzer(rows),
    )

    fake_overlay = {
        "新能源汽车": {
            "avg_impact": -0.32,
            "mentions": 119,
            "signal": "bearish",
        },
    }
    last_refresh_iso = "2026-05-17T07:29:47.810070"
    # Patch the policy loader inside the rotation submodule so we don't
    # touch the alt-data manager.
    from backend.app.api.v1.endpoints.industry import rotation as rotation_endpoint

    monkeypatch.setattr(
        rotation_endpoint,
        "_load_policy_signal_overlay",
        lambda: (fake_overlay, last_refresh_iso),
    )

    result = industry_endpoint.get_hot_industries(
        top_n=10,
        lookback_days=5,
        sort_by="total_score",
        order="desc",
        include_policy_signal=True,
    )

    assert len(result) == 2
    first = result[0]
    assert first.industry_name == "新能源汽车"
    assert first.policy_signal is not None
    assert first.policy_signal.signal == "bearish"
    assert first.policy_signal.mentions == 119
    assert first.policy_signal.avg_impact == pytest.approx(-0.32)
    assert first.policy_signal.last_refresh_at == last_refresh_iso

    second = result[1]
    assert second.industry_name == "无政策覆盖行业"
    assert second.policy_signal is None, (
        "Industries with no policy_radar data must surface as None, not an "
        "empty IndustryPolicySignal — frontend renders '-' for that case."
    )


def test_hot_industries_include_policy_signal_degrades_when_policy_radar_unavailable(
    monkeypatch,
):
    """When policy_radar provider is cold/offline the loader returns an empty
    dict and a None last_refresh; the endpoint must still respond 200 with
    every row's ``policy_signal`` set to ``None``. Mirrors the local-first
    degradation contract used by ``/policy-radar/signal`` itself."""
    _clear_rotation_endpoint_state()

    rows = [
        {"rank": 1, "industry_name": "银行", "score": 70.0},
    ]
    monkeypatch.setattr(
        industry_endpoint,
        "get_industry_analyzer",
        lambda: _StubRankingAnalyzer(rows),
    )

    from backend.app.api.v1.endpoints.industry import rotation as rotation_endpoint

    monkeypatch.setattr(
        rotation_endpoint,
        "_load_policy_signal_overlay",
        lambda: ({}, None),
    )

    result = industry_endpoint.get_hot_industries(
        top_n=10,
        lookback_days=5,
        sort_by="total_score",
        order="desc",
        include_policy_signal=True,
    )

    assert len(result) == 1
    assert result[0].industry_name == "银行"
    assert result[0].policy_signal is None


def test_hot_industries_without_include_policy_signal_preserves_existing_payload(
    monkeypatch,
):
    """Default call path (no include_policy_signal flag) must not touch the
    policy_radar loader and must keep ``policy_signal`` absent / None — the
    'opt-in' contract that protects existing consumers from a sudden payload
    drift."""
    _clear_rotation_endpoint_state()

    rows = [
        {"rank": 1, "industry_name": "钢铁", "score": 60.0},
    ]
    monkeypatch.setattr(
        industry_endpoint,
        "get_industry_analyzer",
        lambda: _StubRankingAnalyzer(rows),
    )

    from backend.app.api.v1.endpoints.industry import rotation as rotation_endpoint

    def _fail_loader() -> tuple[dict[str, object], object]:
        # If this gets called, the opt-in contract is broken.
        raise AssertionError(
            "policy_radar loader called for default ranking request"
        )

    monkeypatch.setattr(
        rotation_endpoint, "_load_policy_signal_overlay", _fail_loader
    )

    result = industry_endpoint.get_hot_industries(
        top_n=10,
        lookback_days=5,
        sort_by="total_score",
        order="desc",
        # Pass ``False`` explicitly to bypass the Query() sentinel default.
        include_policy_signal=False,
    )

    assert len(result) == 1
    assert result[0].industry_name == "钢铁"
    assert result[0].policy_signal is None


def test_hot_industries_default_fastapi_json_omits_policy_signal(monkeypatch):
    """FastAPI serialization must match the opt-in contract.

    The Python model still has ``policy_signal=None`` as a safe internal
    default, but the default HTTP JSON response should not expose the new key
    unless the caller opts in.
    """
    _clear_rotation_endpoint_state()

    rows = [
        {"rank": 1, "industry_name": "钢铁", "score": 60.0},
    ]
    monkeypatch.setattr(
        rotation_endpoint,
        "get_industry_analyzer",
        lambda: _StubRankingAnalyzer(rows),
    )

    def _fail_loader() -> tuple[dict[str, object], object]:
        raise AssertionError("policy overlay should remain opt-in")

    monkeypatch.setattr(rotation_endpoint, "_load_policy_signal_overlay", _fail_loader)

    response = _client_for_rotation_endpoint().get(
        "/industry/industries/hot?top_n=10&lookback_days=5&sort_by=total_score&order=desc"
    )

    assert response.status_code == 200
    row = response.json()[0]
    assert row["industry_name"] == "钢铁"
    assert "policy_signal" not in row
    assert "momentum" in row, "existing default ranking fields should stay serialized"


def test_hot_industries_opt_in_fastapi_json_keeps_null_policy_signal(monkeypatch):
    _clear_rotation_endpoint_state()

    rows = [
        {"rank": 1, "industry_name": "银行", "score": 70.0},
    ]
    monkeypatch.setattr(
        rotation_endpoint,
        "get_industry_analyzer",
        lambda: _StubRankingAnalyzer(rows),
    )
    monkeypatch.setattr(
        rotation_endpoint,
        "_load_policy_signal_overlay",
        lambda: ({}, None),
    )

    response = _client_for_rotation_endpoint().get(
        "/industry/industries/hot"
        "?top_n=10&lookback_days=5&sort_by=total_score&order=desc"
        "&include_policy_signal=true"
    )

    assert response.status_code == 200
    row = response.json()[0]
    assert row["industry_name"] == "银行"
    assert row["policy_signal"] is None
