"""Unit tests for the policy_radar HTTP surface.

The endpoints should:
1. Surface AltDataManager's existing policy data without triggering crawl/NLP
2. Filter records by industry tag when requested
3. Degrade to an empty payload (HTTP 200) when the manager is unavailable,
   per the project's local-first philosophy
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
from src.data.alternative.base_alt_provider import AltDataCategory, AltDataRecord


def _make_record(industry: str, days_ago: int = 0, source_id: str = "ndrc") -> AltDataRecord:
    timestamp = datetime(2026, 5, 1, 12, 0, 0)
    return AltDataRecord(
        timestamp=timestamp,
        source=f"policy_radar:{source_id}",
        category=AltDataCategory.POLICY,
        raw_value={
            "title": f"{industry} 政策通稿",
            "policy_shift": 0.4,
            "will_intensity": 65.0,
            "summary": f"{industry} 行业利好",
            "industry_impact": {industry: {"impact": "positive", "score": 0.4, "mentions": 2}},
        },
        normalized_score=0.42,
        confidence=0.7,
        metadata={
            "link": "https://example.com/policy/1",
            "detail_quality": "rich",
            "detail_status": "full_text",
        },
        tags=[industry],
    )


class _FakeManager:
    """Minimal AltDataManager stub returning controllable canned data."""

    def __init__(self, signal_payload, records):
        self._signal_payload = signal_payload
        self._records = records

    def get_alt_signals(self, category=None, timeframe="7d", refresh_if_empty=False):
        return self._signal_payload

    def get_records(self, category=None, timeframe="7d", limit=200):
        return list(self._records)


# ---------------------------------------------------------------------------
# /policy-radar/signal
# ---------------------------------------------------------------------------


def test_signal_endpoint_extracts_policy_signal_from_envelope():
    fake_signal = {
        "signals": [
            {
                "category": "policy",
                "score": 0.32,
                "industry_signals": {
                    "新能源": {"avg_impact": 0.34, "mentions": 5, "signal": "bullish"},
                },
                "policy_count": 7,
                "source_health": {"ndrc": {"level": "healthy"}},
            },
        ],
        "last_refresh": "2026-05-03T08:00:00",
    }
    manager = _FakeManager(fake_signal, [])

    with patch(
        "backend.app.api.v1.endpoints.policy_radar._get_alt_manager",
        return_value=manager,
    ):
        client = TestClient(app)
        response = client.get("/policy-radar/signal")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["available"] is True
    assert data["policy_count"] == 7
    assert "新能源" in data["industry_signals"]
    assert data["source_health"]["ndrc"]["level"] == "healthy"
    assert data["last_refresh"] == "2026-05-03T08:00:00"


def test_signal_endpoint_returns_empty_skeleton_when_manager_raises():
    def _raise(*args, **kwargs):
        raise RuntimeError("alt manager not initialized")

    with patch(
        "backend.app.api.v1.endpoints.policy_radar._get_alt_manager",
        side_effect=_raise,
    ):
        client = TestClient(app)
        response = client.get("/policy-radar/signal")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["available"] is False
    assert data["policy_count"] == 0
    assert data["industry_signals"] == {}


def test_signal_endpoint_empty_when_no_policy_in_envelope():
    """Manager returns signals but none in the policy category — still HTTP 200."""
    fake_signal = {
        "signals": [{"category": "media_sentiment", "score": 0.1}],
        "last_refresh": "2026-05-03T07:00:00",
    }
    manager = _FakeManager(fake_signal, [])

    with patch(
        "backend.app.api.v1.endpoints.policy_radar._get_alt_manager",
        return_value=manager,
    ):
        client = TestClient(app)
        response = client.get("/policy-radar/signal")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["available"] is False
    assert data["policy_count"] == 0
    assert data["last_refresh"] == "2026-05-03T07:00:00"


# ---------------------------------------------------------------------------
# /policy-radar/records
# ---------------------------------------------------------------------------


def test_records_endpoint_returns_serialized_records_in_descending_time():
    earlier = AltDataRecord(
        timestamp=datetime(2026, 4, 30, 10, 0, 0),
        source="policy_radar:ndrc",
        category=AltDataCategory.POLICY,
        raw_value={"title": "old"},
        normalized_score=0.1,
        confidence=0.5,
        metadata={},
        tags=["新能源"],
    )
    later = _make_record("新能源", source_id="nea")
    manager = _FakeManager({"signals": []}, [earlier, later])

    with patch(
        "backend.app.api.v1.endpoints.policy_radar._get_alt_manager",
        return_value=manager,
    ):
        client = TestClient(app)
        response = client.get("/policy-radar/records?timeframe=30d")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["available"] is True
    assert len(data["records"]) == 2
    assert data["records"][0]["timestamp"] >= data["records"][1]["timestamp"]


def test_records_endpoint_filters_by_industry_tag():
    energy = _make_record("新能源", source_id="ndrc")
    semi = _make_record("半导体", source_id="ndrc")
    manager = _FakeManager({"signals": []}, [energy, semi])

    with patch(
        "backend.app.api.v1.endpoints.policy_radar._get_alt_manager",
        return_value=manager,
    ):
        client = TestClient(app)
        response = client.get("/policy-radar/records?industry=新能源")

    assert response.status_code == 200
    records = response.json()["data"]["records"]
    assert len(records) == 1
    assert records[0]["raw_value"]["title"].startswith("新能源")


def test_records_endpoint_returns_empty_skeleton_when_manager_raises():
    def _raise(*args, **kwargs):
        raise RuntimeError("alt manager unavailable")

    with patch(
        "backend.app.api.v1.endpoints.policy_radar._get_alt_manager",
        side_effect=_raise,
    ):
        client = TestClient(app)
        response = client.get("/policy-radar/records?industry=新能源&timeframe=30d&limit=20")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["available"] is False
    assert data["records"] == []
    assert data["industry"] == "新能源"
    assert data["timeframe"] == "30d"
    assert data["limit"] == 20


def test_records_endpoint_validates_limit_range():
    client = TestClient(app)
    # limit > 200 should be rejected by Query validator before manager runs
    response = client.get("/policy-radar/records?limit=999")
    assert response.status_code == 422
