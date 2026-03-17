from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import alt_data, macro
from src.data.alternative.alt_data_manager import AltDataManager
from src.data.alternative.governance import AltDataSnapshotStore
from tests.unit.test_alt_data_pipeline import DummyAltProvider, FailingAltProvider


def _build_client(monkeypatch, manager, scheduler_status=None):
    app = FastAPI()
    app.include_router(alt_data.router, prefix="/alt-data")
    app.include_router(macro.router, prefix="/macro")

    class DummyScheduler:
        def get_status(self):
            return scheduler_status or {"running": False, "jobs": []}

    monkeypatch.setattr(alt_data, "_get_manager", lambda: manager)
    monkeypatch.setattr(alt_data, "_get_scheduler", lambda: DummyScheduler())
    monkeypatch.setattr(macro, "get_alt_data_manager", lambda: manager)
    return TestClient(app)


def test_alt_data_status_and_refresh_endpoints(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"dummy_policy": DummyAltProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    client = _build_client(monkeypatch, manager, scheduler_status={"running": True, "jobs": [{"id": "alt-data-dummy"}]})

    refresh_response = client.post("/alt-data/refresh?provider=all")
    assert refresh_response.status_code == 200
    assert refresh_response.json()["status"] == "success"

    status_response = client.get("/alt-data/status")
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["scheduler"]["running"] is True
    assert "dummy_policy" in payload["providers"]

    history_response = client.get("/alt-data/history?limit=5")
    assert history_response.status_code == 200
    assert history_response.json()["count"] == 1


def test_alt_data_refresh_rejects_unknown_provider(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"dummy_policy": DummyAltProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    client = _build_client(monkeypatch, manager)

    response = client.post("/alt-data/refresh?provider=missing")
    assert response.status_code == 400


def test_alt_data_snapshot_and_macro_survive_provider_failure(monkeypatch, tmp_path):
    store = AltDataSnapshotStore(tmp_path / "alt_data")
    healthy_manager = AltDataManager(
        providers={"dummy_policy": DummyAltProvider()},
        snapshot_store=store,
    )
    healthy_manager.refresh_all(force=True)

    failing_manager = AltDataManager(
        providers={"dummy_policy": FailingAltProvider()},
        snapshot_store=store,
    )
    client = _build_client(monkeypatch, failing_manager)

    snapshot_response = client.get("/alt-data/snapshot?refresh=true")
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["refresh_status"]["dummy_policy"]["status"] == "degraded"

    macro_response = client.get("/macro/overview?refresh=true")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    assert "data_freshness" in macro_payload
    assert "provider_status" in macro_payload
