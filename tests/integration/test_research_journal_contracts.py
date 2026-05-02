from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app


def test_research_journal_snapshot_endpoint_accepts_profile_header():
    client = TestClient(app)

    with patch(
        "backend.app.api.v1.endpoints.research_journal.research_journal_store.update_snapshot",
        return_value={
            "entries": [{"id": "bt-1", "type": "backtest", "title": "AAPL 回测"}],
            "source_state": {},
            "generated_at": "2026-05-02T00:00:00+00:00",
            "updated_at": "2026-05-02T00:00:00+00:00",
            "summary": {"total_entries": 1},
        },
    ) as update_snapshot:
        response = client.put(
            "/research-journal/snapshot",
            headers={"X-Research-Profile": "browser-a"},
            json={
                "entries": [{"id": "bt-1", "type": "backtest", "title": "AAPL 回测"}],
                "source_state": {"backtest": {"count": 1}},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["summary"]["total_entries"] == 1
    update_snapshot.assert_called_once()
    assert update_snapshot.call_args.kwargs["profile_id"] == "browser-a"


def test_research_journal_entry_status_endpoint_maps_missing_entry_to_404():
    client = TestClient(app)

    with patch(
        "backend.app.api.v1.endpoints.research_journal.research_journal_store.update_entry_status",
        side_effect=KeyError("missing"),
    ):
        response = client.patch(
            "/research-journal/entries/missing/status?profile_id=browser-a",
            json={"status": "done"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "entry not found"
