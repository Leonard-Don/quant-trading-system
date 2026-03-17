from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import research_workbench
from src.research.workbench import ResearchWorkbenchStore


def _build_client(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(research_workbench.router, prefix="/research-workbench")
    store = ResearchWorkbenchStore(storage_path=tmp_path / "research_workbench")
    monkeypatch.setattr(research_workbench, "_get_research_workbench", lambda: store)
    return TestClient(app)


def test_research_workbench_endpoint_create_and_list(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)

    create_response = client.post(
        "/research-workbench/tasks",
        json={
            "type": "pricing",
            "title": "[Pricing] AAPL mispricing review",
            "source": "godeye",
            "symbol": "AAPL",
            "snapshot": {
                "headline": "AAPL pricing snapshot",
                "summary": "pricing summary",
                "highlights": ["gap +8.0%"],
                "payload": {"gap_analysis": {"gap_pct": 0.08}},
            },
        },
    )

    assert create_response.status_code == 200
    task_id = create_response.json()["data"]["id"]

    list_response = client.get("/research-workbench/tasks?type=pricing")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["success"] is True
    assert payload["total"] == 1
    assert payload["data"][0]["id"] == task_id
    assert payload["data"][0]["board_order"] == 0


def test_research_workbench_endpoint_update_and_stats(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)
    created = client.post(
        "/research-workbench/tasks",
        json={
            "type": "cross_market",
            "title": "[CrossMarket] utilities_vs_growth thesis",
            "template": "utilities_vs_growth",
            "snapshot": {
                "headline": "cross snapshot",
                "payload": {"total_return": 0.03, "sharpe_ratio": 0.9},
            },
        },
    ).json()["data"]

    update_response = client.put(
        f"/research-workbench/tasks/{created['id']}",
        json={"status": "blocked", "note": "coverage too low"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["status"] == "blocked"

    stats_response = client.get("/research-workbench/stats")
    assert stats_response.status_code == 200
    stats = stats_response.json()["data"]
    assert stats["status_counts"]["blocked"] == 1
    assert stats["type_counts"]["cross_market"] == 1
    assert stats["with_timeline"] == 1


def test_research_workbench_endpoint_comment_timeline_and_snapshot(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)
    created = client.post(
        "/research-workbench/tasks",
        json={
            "type": "pricing",
            "title": "[Pricing] MSFT mispricing review",
            "symbol": "MSFT",
        },
    ).json()["data"]

    comment_response = client.post(
        f"/research-workbench/tasks/{created['id']}/comments",
        json={"body": "track cloud capex assumptions", "author": "local"},
    )
    assert comment_response.status_code == 200
    assert comment_response.json()["data"]["body"] == "track cloud capex assumptions"

    snapshot_response = client.post(
        f"/research-workbench/tasks/{created['id']}/snapshot",
        json={
            "snapshot": {
                "headline": "MSFT snapshot",
                "summary": "valuation refreshed",
                "payload": {"gap_analysis": {"gap_pct": 0.05}},
            }
        },
    )
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["data"]["snapshot"]["headline"] == "MSFT snapshot"

    timeline_response = client.get(f"/research-workbench/tasks/{created['id']}/timeline")
    assert timeline_response.status_code == 200
    timeline = timeline_response.json()["data"]
    assert timeline[0]["type"] == "snapshot_saved"
    assert any(item["type"] == "comment_added" for item in timeline)

    comment_id = comment_response.json()["data"]["id"]
    delete_response = client.delete(f"/research-workbench/tasks/{created['id']}/comments/{comment_id}")
    assert delete_response.status_code == 200


def test_research_workbench_endpoint_reorder_board(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)
    first = client.post(
        "/research-workbench/tasks",
        json={"type": "pricing", "title": "task 1", "symbol": "AAPL"},
    ).json()["data"]
    second = client.post(
        "/research-workbench/tasks",
        json={"type": "pricing", "title": "task 2", "symbol": "MSFT"},
    ).json()["data"]

    reorder_response = client.post(
        "/research-workbench/board/reorder",
        json={
            "items": [
                {"task_id": first["id"], "status": "in_progress", "board_order": 0},
                {"task_id": second["id"], "status": "new", "board_order": 0},
            ]
        },
    )
    assert reorder_response.status_code == 200

    board_response = client.get("/research-workbench/tasks?view=board")
    assert board_response.status_code == 200
    board_items = board_response.json()["data"]
    moved = next(item for item in board_items if item["id"] == first["id"])
    assert moved["status"] == "in_progress"
    assert moved["board_order"] == 0


def test_research_workbench_endpoint_reorder_archived_returns_400(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)
    task = client.post(
        "/research-workbench/tasks",
        json={"type": "pricing", "title": "task", "symbol": "AAPL"},
    ).json()["data"]

    response = client.post(
        "/research-workbench/board/reorder",
        json={"items": [{"task_id": task["id"], "status": "archived", "board_order": 0}]},
    )

    assert response.status_code == 400


def test_research_workbench_endpoint_delete_missing_comment_returns_404(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)
    created = client.post(
        "/research-workbench/tasks",
        json={"type": "pricing", "title": "task", "symbol": "AAPL"},
    ).json()["data"]

    response = client.delete(f"/research-workbench/tasks/{created['id']}/comments/missing-comment")

    assert response.status_code == 404


def test_research_workbench_endpoint_delete_missing_returns_404(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)

    response = client.delete("/research-workbench/tasks/missing-task")

    assert response.status_code == 404
