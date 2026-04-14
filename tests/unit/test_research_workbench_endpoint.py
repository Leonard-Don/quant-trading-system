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
            "refresh_priority_event": {
                "reason_key": "structural_decay",
                "reason_label": "结构衰败/系统雷达",
                "severity": "high",
                "lead": "结构性衰败警报，主导失效模式偏向 组织与治理稀释。",
                "detail": "衰败分 0.74；主导失效 组织与治理稀释",
            },
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
    assert payload["data"][0]["timeline"][0]["type"] == "refresh_priority"


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
        json={
            "status": "blocked",
            "note": "coverage too low",
            "refresh_priority_event": {
                "reason_key": "structural_decay",
                "reason_label": "结构衰败/系统雷达",
                "severity": "high",
                "lead": "系统级结构衰败雷达已升级到警报区",
                "detail": "紧急度 5.0；建议先收缩风险预算。",
                "urgency_score": 5.0,
                "priority_weight": 3.4,
            },
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["status"] == "blocked"
    assert update_response.json()["data"]["timeline"][0]["type"] == "refresh_priority"

    snapshot_response = client.post(
        f"/research-workbench/tasks/{created['id']}/snapshot",
        json={
            "snapshot": {
                "headline": "cross snapshot v2",
                "payload": {
                    "total_return": 0.04,
                    "view_context": {
                        "summary": "快速视图：自动排序缓和 · 类型：Cross-Market",
                        "view_fingerprint": "wv_cross_relaxed",
                        "scoped_task_label": f"当前定位：{created['id']}",
                    },
                },
            },
        },
    )
    assert snapshot_response.status_code == 200

    stats_response = client.get("/research-workbench/stats")
    assert stats_response.status_code == 200
    stats = stats_response.json()["data"]
    assert stats["status_counts"]["blocked"] == 1
    assert stats["type_counts"]["cross_market"] == 1
    assert stats["with_timeline"] == 1
    assert stats["snapshot_view_queues"][0]["label"] == "快速视图：自动排序缓和 · 类型：Cross-Market"
    assert stats["snapshot_view_queues"][0]["fingerprint"] == "wv_cross_relaxed"
    assert stats["snapshot_view_queues"][0]["count"] == 1


def test_research_workbench_endpoint_bulk_updates_tasks(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)
    first = client.post(
        "/research-workbench/tasks",
        json={"type": "pricing", "title": "[Pricing] AAPL review", "symbol": "AAPL"},
    ).json()["data"]
    second = client.post(
        "/research-workbench/tasks",
        json={"type": "pricing", "title": "[Pricing] MSFT review", "symbol": "MSFT"},
    ).json()["data"]

    bulk_response = client.post(
        "/research-workbench/tasks/bulk-update",
        json={
            "task_ids": [first["id"], second["id"]],
            "status": "in_progress",
            "comment": "批量复盘：快速视图：自动排序升档 · 类型：Pricing",
            "author": "local",
        },
    )

    assert bulk_response.status_code == 200
    payload = bulk_response.json()
    assert payload["total"] == 2
    assert all(item["status"] == "in_progress" for item in payload["data"])
    assert all(item["comments"][0]["body"] == "批量复盘：快速视图：自动排序升档 · 类型：Pricing" for item in payload["data"])


def test_research_workbench_endpoint_supports_macro_mispricing_tasks(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)

    create_response = client.post(
        "/research-workbench/tasks",
        json={
            "type": "macro_mispricing",
            "title": "[MacroMispricing] BABA structural decay watch",
            "source": "godeye_decay_watch",
            "symbol": "BABA",
            "snapshot": {
                "headline": "BABA 结构性衰败观察",
                "summary": "人的维度与长期定价证据同步走弱",
                "payload": {
                    "structural_decay": {"score": 0.82, "label": "结构性衰败警报"},
                    "people_layer": {"risk_level": "high"},
                },
            },
        },
    )

    assert create_response.status_code == 200
    task_id = create_response.json()["data"]["id"]

    list_response = client.get("/research-workbench/tasks?type=macro_mispricing")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["data"][0]["id"] == task_id
    assert payload["data"][0]["symbol"] == "BABA"


def test_research_workbench_endpoint_supports_trade_thesis_tasks(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)

    create_response = client.post(
        "/research-workbench/tasks",
        json={
            "type": "trade_thesis",
            "title": "[TradeThesis] BABA macro mispricing basket",
            "source": "macro_mispricing_draft",
            "symbol": "BABA",
            "template": "macro_mispricing_relative_value",
            "snapshot": {
                "headline": "BABA 交易 Thesis",
                "summary": "可继续跟踪多腿组合演化",
                "payload": {
                    "trade_thesis": {
                        "symbol": "BABA",
                        "thesis": {"stance": "结构性做空", "horizon": "6-12m"},
                        "assets": [
                            {"symbol": "BABA", "side": "short"},
                            {"symbol": "KWEB", "side": "long"},
                        ],
                    }
                },
            },
        },
    )

    assert create_response.status_code == 200
    task_id = create_response.json()["data"]["id"]

    list_response = client.get("/research-workbench/tasks?type=trade_thesis")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["data"][0]["id"] == task_id
    assert payload["data"][0]["template"] == "macro_mispricing_relative_value"


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
                "payload": {
                    "gap_analysis": {"gap_pct": 0.05},
                    "view_context": {
                        "summary": "快速视图：自动排序升档 · 类型：Pricing",
                        "view_fingerprint": "wv_msft_pricing",
                        "scoped_task_label": "当前定位：rw_msft",
                        "note": "这次快照是在带筛选的工作台视图下保存的。",
                    },
                },
            },
            "refresh_priority_event": {
                "reason_key": "selection_quality_active",
                "reason_label": "降级运行",
                "severity": "medium",
                "lead": "当前保存结果已经处于降级运行状态",
                "detail": "紧急度 4.0；排序权重 2.2",
            },
        },
    )
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["data"]["snapshot"]["headline"] == "MSFT snapshot"

    timeline_response = client.get(f"/research-workbench/tasks/{created['id']}/timeline")
    assert timeline_response.status_code == 200
    timeline = timeline_response.json()["data"]
    assert timeline[0]["type"] == "refresh_priority"
    assert timeline[1]["type"] == "snapshot_saved"
    assert "视图 快速视图：自动排序升档 · 类型：Pricing" in timeline[1]["detail"]
    assert timeline[1]["meta"]["view_context_summary"] == "快速视图：自动排序升档 · 类型：Pricing"
    assert timeline[1]["meta"]["view_context_fingerprint"] == "wv_msft_pricing"
    assert timeline[1]["meta"]["view_context_scoped_task_label"] == "当前定位：rw_msft"
    assert timeline[1]["meta"]["view_context_note"] == "这次快照是在带筛选的工作台视图下保存的。"
    assert any(item["type"] == "comment_added" for item in timeline)

    comment_id = comment_response.json()["data"]["id"]
    delete_response = client.delete(f"/research-workbench/tasks/{created['id']}/comments/{comment_id}")
    assert delete_response.status_code == 200


def test_research_workbench_endpoint_deduplicates_refresh_priority_events(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)
    created = client.post(
        "/research-workbench/tasks",
        json={
            "type": "pricing",
            "title": "[Pricing] MSFT mispricing review",
            "symbol": "MSFT",
        },
    ).json()["data"]
    refresh_priority_event = {
        "reason_key": "structural_decay",
        "reason_label": "结构衰败/系统雷达",
        "severity": "high",
        "lead": "系统级结构衰败雷达已升级到警报区",
        "detail": "紧急度 5.0；建议先收缩风险预算。",
        "urgency_score": 5.0,
        "priority_weight": 3.4,
    }

    update_response = client.put(
        f"/research-workbench/tasks/{created['id']}",
        json={
            "status": "blocked",
            "refresh_priority_event": refresh_priority_event,
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["timeline"][0]["type"] == "refresh_priority"

    snapshot_response = client.post(
        f"/research-workbench/tasks/{created['id']}/snapshot",
        json={
            "snapshot": {
                "headline": "MSFT snapshot",
                "summary": "valuation refreshed",
                "payload": {"gap_analysis": {"gap_pct": 0.05}},
            },
            "refresh_priority_event": refresh_priority_event,
        },
    )
    assert snapshot_response.status_code == 200
    timeline = snapshot_response.json()["data"]["timeline"]
    assert timeline[0]["type"] == "snapshot_saved"
    assert sum(1 for item in timeline if item["type"] == "refresh_priority") == 1


def test_research_workbench_endpoint_marks_refresh_priority_escalation(monkeypatch, tmp_path):
    client = _build_client(monkeypatch, tmp_path)
    created = client.post(
        "/research-workbench/tasks",
        json={
            "type": "pricing",
            "title": "[Pricing] BABA mispricing review",
            "symbol": "BABA",
        },
    ).json()["data"]

    client.put(
        f"/research-workbench/tasks/{created['id']}",
        json={
            "status": "in_progress",
            "refresh_priority_event": {
                "reason_key": "people_layer",
                "reason_label": "人的维度",
                "severity": "medium",
                "lead": "人的维度开始走弱",
                "detail": "紧急度 3.0；建议关注关键岗位变化。",
                "urgency_score": 3.0,
                "priority_weight": 2.0,
            },
        },
    )

    snapshot_response = client.post(
        f"/research-workbench/tasks/{created['id']}/snapshot",
        json={
            "snapshot": {
                "headline": "BABA snapshot",
                "summary": "valuation refreshed",
                "payload": {"gap_analysis": {"gap_pct": 0.11}},
            },
            "refresh_priority_event": {
                "reason_key": "structural_decay",
                "reason_label": "结构衰败/系统雷达",
                "severity": "high",
                "lead": "系统级结构衰败雷达已升级到警报区",
                "detail": "紧急度 5.0；建议先收缩风险预算。",
                "urgency_score": 5.0,
                "priority_weight": 3.4,
            },
        },
    )

    assert snapshot_response.status_code == 200
    timeline = snapshot_response.json()["data"]["timeline"]
    assert timeline[0]["label"] == "系统自动重排升级：结构衰败/系统雷达"
    assert timeline[0]["meta"]["change_type"] == "escalated"
    assert timeline[0]["meta"]["previous_reason_label"] == "人的维度"


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
                {
                    "task_id": first["id"],
                    "status": "in_progress",
                    "board_order": 0,
                    "refresh_priority_event": {
                        "reason_key": "structural_decay",
                        "reason_label": "结构衰败/系统雷达",
                        "severity": "high",
                        "lead": "系统级结构衰败雷达已升级到警报区",
                        "detail": "紧急度 5.0；建议先收缩风险预算。",
                    },
                },
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

    timeline_response = client.get(f"/research-workbench/tasks/{first['id']}/timeline")
    assert timeline_response.status_code == 200
    timeline = timeline_response.json()["data"]
    assert timeline[0]["type"] == "refresh_priority"
    assert timeline[1]["type"] == "status_changed"


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
