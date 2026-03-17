import json

from src.research.workbench import ResearchWorkbenchStore


def test_research_workbench_store_recovers_from_invalid_json(tmp_path):
    storage = tmp_path / "research_workbench"
    storage.mkdir(parents=True, exist_ok=True)
    (storage / "tasks.json").write_text("{invalid json", encoding="utf-8")

    store = ResearchWorkbenchStore(storage_path=storage)

    assert store.list_tasks() == []


def test_research_workbench_store_create_update_and_filter(tmp_path):
    store = ResearchWorkbenchStore(storage_path=tmp_path / "research_workbench")

    pricing_task = store.create_task(
        {
            "type": "pricing",
            "title": "[Pricing] NVDA mispricing review",
            "source": "godeye",
            "symbol": "NVDA",
            "snapshot": {"headline": "NVDA task", "payload": {"gap_analysis": {"gap_pct": 0.12}}},
        }
    )
    cross_task = store.create_task(
        {
            "type": "cross_market",
            "title": "[CrossMarket] utilities_vs_growth thesis",
            "source": "godeye",
            "template": "utilities_vs_growth",
            "snapshot": {"headline": "Template task", "payload": {"total_return": 0.08}},
        }
    )

    assert pricing_task["id"].startswith("rw_")
    assert cross_task["status"] == "new"
    assert len(store.list_tasks(task_type="pricing")) == 1
    assert pricing_task["timeline"][0]["type"] == "snapshot_saved"
    assert pricing_task["timeline"][1]["type"] == "created"
    assert len(pricing_task["snapshot_history"]) == 1

    updated = store.update_task(pricing_task["id"], {"status": "in_progress", "note": "check valuation anchors"})
    assert updated["status"] == "in_progress"
    assert updated["note"] == "check valuation anchors"
    assert {updated["timeline"][0]["type"], updated["timeline"][1]["type"]} == {
        "metadata_updated",
        "status_changed",
    }

    stats = store.get_stats()
    assert stats["total"] == 2
    assert stats["status_counts"]["in_progress"] == 1
    assert stats["type_counts"]["cross_market"] == 1
    assert stats["with_timeline"] == 2

    saved_payload = json.loads((tmp_path / "research_workbench" / "tasks.json").read_text(encoding="utf-8"))
    assert len(saved_payload) == 2


def test_research_workbench_store_comment_snapshot_and_timeline(tmp_path):
    store = ResearchWorkbenchStore(storage_path=tmp_path / "research_workbench")
    task = store.create_task({"type": "pricing", "title": "task", "symbol": "AAPL"})

    comment = store.add_comment(task["id"], "watch policy risk", author="local")
    assert comment["body"] == "watch policy risk"

    updated = store.add_snapshot(
        task["id"],
        {
            "headline": "new snapshot",
            "summary": "refreshed result",
            "payload": {"gap_analysis": {"gap_pct": 0.11}},
        },
    )
    assert updated["snapshot"]["headline"] == "new snapshot"
    assert updated["snapshot_history"][0]["headline"] == "new snapshot"

    timeline = store.get_timeline(task["id"])
    assert timeline[0]["type"] == "snapshot_saved"
    assert any(event["type"] == "comment_added" for event in timeline)

    assert store.delete_comment(task["id"], comment["id"]) is True
    assert store.delete_comment(task["id"], comment["id"]) is False


def test_research_workbench_store_delete(tmp_path):
    store = ResearchWorkbenchStore(storage_path=tmp_path / "research_workbench")
    task = store.create_task({"type": "pricing", "title": "task"})

    assert store.delete_task(task["id"]) is True
    assert store.get_task(task["id"]) is None
    assert store.delete_task(task["id"]) is False
