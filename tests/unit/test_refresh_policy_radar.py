"""Unit tests for the policy_radar refresh CLI.

Exercises the snapshot-ingestion wiring end-to-end without touching live HTTP:
mock the underlying ``PolicyCrawler.crawl_source``, run the refresh, and verify
the persisted snapshot causes ``/policy-radar/*`` to flip from ``available:false``
(empty cache) to ``available:true`` (real records on disk).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from scripts import refresh_policy_radar
from src.data.alternative.alt_data_manager import AltDataManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_crawl_payload(source_id: str = "ndrc") -> list[dict[str, Any]]:
    """A minimal payload that survives the full PolicySignalProvider pipeline."""
    # Publish date must be relative to "now": /policy-radar/records filters by a
    # datetime.now()-relative window (e.g. 30d), so a hardcoded date silently
    # falls out of the window as wall-clock time advances. A small 2-day offset
    # keeps the record inside both the default 7d and the wider 30d windows.
    recent_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    return [
        {
            "title": f"{source_id.upper()} 加快电网与储能建设若干意见",
            "summary": "进一步加快新型电力系统建设，扩大电网投资规模并支持储能项目落地。",
            "detail_excerpt": (
                "国家发改委、国家能源局联合下发文件，明确推动电网设备升级与"
                "储能装机扩张，要求各地年内完成首轮试点。" * 4
            ),
            "text": (
                "国家发改委、国家能源局联合下发文件，明确推动电网设备升级与"
                "储能装机扩张，要求各地年内完成首轮试点。" * 4
            ),
            "text_length": 480,
            "detail_status": "full_text",
            "detail_quality": "rich",
            "date": recent_date,
            "source": "国家发改委" if source_id == "ndrc" else source_id.upper(),
            "source_id": source_id,
            "link": f"https://example.com/{source_id}/policy",
            "detail_url": f"https://example.com/{source_id}/policy",
            "detail_title": f"{source_id.upper()} 电网政策",
            "ingest_mode": "feed",
        }
    ]


def _stub_all_sources(monkeypatch: pytest.MonkeyPatch, manager: AltDataManager) -> None:
    """Patch every provider's crawler / network surface to return canned data.

    The refresh script triggers a single provider (policy_radar) but the
    build_dashboard_snapshot() call at the tail still iterates every provider's
    history. That's already cached on disk in production, but in this isolated
    tmp_path test we keep things deterministic by emptying any provider whose
    refresh would otherwise be triggered.
    """
    policy_provider = manager.get_provider("policy_radar")
    monkeypatch.setattr(
        policy_provider.crawler,
        "crawl_source",
        lambda source_id, limit=5, days_back=14, fetch_details=True, **_: (
            _stub_crawl_payload(source_id)
        ),
    )


# ---------------------------------------------------------------------------
# Script-level behavior
# ---------------------------------------------------------------------------


def test_refresh_writes_snapshot_to_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """refresh_policy_radar() must create cache/alt_data/providers/policy_radar.json."""
    snapshot_dir = tmp_path / "alt_data"
    manager = AltDataManager(config={"snapshot_dir": str(snapshot_dir)})
    _stub_all_sources(monkeypatch, manager)

    status = refresh_policy_radar.refresh_policy_radar(
        force=True,
        snapshot_dir=snapshot_dir,
        manager=manager,
    )

    assert status["status"] == "success"
    assert status["record_count"] >= 1
    assert status["error"] is None

    snapshot_path = snapshot_dir / "providers" / "policy_radar.json"
    assert snapshot_path.exists()

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["provider"] == "policy_radar"
    assert payload["signal"]["record_count"] >= 1
    assert payload["records"], "snapshot should carry the crawled records"
    first = payload["records"][0]
    assert first["source"].startswith("policy_radar:")
    assert first["category"] == "policy"

    # Dashboard envelope is also persisted so the read endpoint exposes a
    # populated last_refresh timestamp.
    assert (snapshot_dir / "dashboard_snapshot.json").exists()
    assert (snapshot_dir / "refresh_status.json").exists()


def test_main_entrypoint_returns_zero_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main() with --snapshot-dir should run end-to-end and exit 0."""
    snapshot_dir = tmp_path / "alt_data"

    def _factory(*args, **kwargs):
        manager = AltDataManager(config={"snapshot_dir": str(snapshot_dir)})
        _stub_all_sources(monkeypatch, manager)
        return manager

    monkeypatch.setattr(refresh_policy_radar, "AltDataManager", _factory)

    exit_code = refresh_policy_radar.main(
        [
            "--snapshot-dir",
            str(snapshot_dir),
            "--print-json",
        ]
    )

    assert exit_code == 0
    assert (snapshot_dir / "providers" / "policy_radar.json").exists()


def test_main_returns_nonzero_when_provider_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When PolicySignalProvider raises, refresh_service degrades and main() returns nonzero."""
    snapshot_dir = tmp_path / "alt_data"

    def _factory(*args, **kwargs):
        manager = AltDataManager(config={"snapshot_dir": str(snapshot_dir)})
        # Force the underlying provider to raise — RefreshService should catch
        # it, classify status as "error" / "degraded", and main() should return
        # a nonzero exit code so cron alerts on it.
        policy_provider = manager.get_provider("policy_radar")
        monkeypatch.setattr(
            policy_provider,
            "run_pipeline",
            lambda **_: (_ for _ in ()).throw(RuntimeError("simulated network failure")),
        )
        return manager

    monkeypatch.setattr(refresh_policy_radar, "AltDataManager", _factory)

    exit_code = refresh_policy_radar.main(["--snapshot-dir", str(snapshot_dir)])
    assert exit_code != 0


# ---------------------------------------------------------------------------
# Endpoint integration: snapshot -> AltDataManager -> /policy-radar/*
# ---------------------------------------------------------------------------


def test_endpoint_flips_to_available_true_after_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Persisted snapshot must drive /policy-radar/signal to available=True.

    This validates the wiring: refresh script writes snapshot, a fresh
    AltDataManager bootstraps from that snapshot, and the HTTP layer surfaces
    the policy signal without any extra crawl/NLP work.
    """
    snapshot_dir = tmp_path / "alt_data"

    # 1) Run the refresh once with a stubbed crawler so we land real records.
    seed_manager = AltDataManager(config={"snapshot_dir": str(snapshot_dir)})
    _stub_all_sources(monkeypatch, seed_manager)
    refresh_policy_radar.refresh_policy_radar(
        force=True, snapshot_dir=snapshot_dir, manager=seed_manager
    )

    # 2) Build a brand-new AltDataManager that bootstraps purely from disk —
    #    mirroring how the FastAPI process would start cold.
    read_manager = AltDataManager(config={"snapshot_dir": str(snapshot_dir)})
    assert "policy_radar" in read_manager.latest_signals
    assert read_manager.latest_signals["policy_radar"]["record_count"] >= 1

    monkeypatch.setattr(
        "backend.app.api.v1.endpoints.policy_radar._get_alt_manager",
        lambda: read_manager,
    )

    client = TestClient(app)
    signal_resp = client.get("/policy-radar/signal")
    assert signal_resp.status_code == 200
    signal_data = signal_resp.json()["data"]
    assert signal_data["available"] is True, signal_data
    assert signal_data["policy_count"] >= 1
    assert signal_data["last_refresh"] is not None

    records_resp = client.get("/policy-radar/records?timeframe=30d&limit=10")
    assert records_resp.status_code == 200
    records_data = records_resp.json()["data"]
    assert records_data["available"] is True
    assert len(records_data["records"]) >= 1
    assert records_data["records"][0]["category"] == "policy"
    assert records_data["records"][0]["source"].startswith("policy_radar:")


def test_fresh_checkout_returns_available_false_without_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sanity guard: without snapshots on disk, the endpoint stays at available:false.

    This pins down the user-visible contract before/after the refresh wiring:
    a fresh checkout that hasn't been bootstrapped should NOT pretend to have
    data. Once cron runs refresh_policy_radar.py, the endpoint flips to True.
    """
    snapshot_dir = tmp_path / "alt_data_empty"
    cold_manager = AltDataManager(config={"snapshot_dir": str(snapshot_dir)})
    # No refresh has run — latest_signals should be empty for policy_radar.
    assert cold_manager.latest_signals.get("policy_radar", {}).get("record_count", 0) == 0

    monkeypatch.setattr(
        "backend.app.api.v1.endpoints.policy_radar._get_alt_manager",
        lambda: cold_manager,
    )

    client = TestClient(app)
    response = client.get("/policy-radar/signal")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["available"] is False
    assert data["policy_count"] == 0
