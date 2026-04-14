import json

from src.research.workbench import ResearchWorkbenchStore


def test_research_workbench_store_recovers_from_invalid_json(tmp_path):
    storage = tmp_path / "research_workbench"
    storage.mkdir(parents=True, exist_ok=True)
    (storage / "tasks.json").write_text("{invalid json", encoding="utf-8")

    store = ResearchWorkbenchStore(storage_path=storage)

    assert store.list_tasks() == []


def test_research_workbench_store_migrates_legacy_json_into_sqlite(tmp_path):
    storage = tmp_path / "research_workbench"
    storage.mkdir(parents=True, exist_ok=True)
    (storage / "tasks.json").write_text(
        json.dumps(
            [
                {
                    "id": "rw_legacy_1",
                    "type": "pricing",
                    "title": "legacy task",
                    "status": "new",
                    "updated_at": "2026-03-17T10:00:00",
                    "created_at": "2026-03-17T10:00:00",
                }
            ]
        ),
        encoding="utf-8",
    )

    migrated_store = ResearchWorkbenchStore(storage_path=storage)
    assert migrated_store.list_tasks()[0]["id"] == "rw_legacy_1"

    reloaded_store = ResearchWorkbenchStore(storage_path=storage)
    assert reloaded_store.list_tasks()[0]["id"] == "rw_legacy_1"


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
    macro_task = store.create_task(
        {
            "type": "macro_mispricing",
            "title": "[MacroMispricing] BABA structural decay watch",
            "source": "godeye_decay_watch",
            "symbol": "BABA",
            "snapshot": {"headline": "BABA decay watch", "payload": {"structural_decay": {"score": 0.81}}},
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
    thesis_task = store.create_task(
        {
            "type": "trade_thesis",
            "title": "[TradeThesis] BABA macro mispricing basket",
            "source": "macro_mispricing_draft",
            "symbol": "BABA",
            "template": "macro_mispricing_relative_value",
            "snapshot": {
                "headline": "BABA 交易 Thesis",
                "payload": {"trade_thesis": {"symbol": "BABA", "thesis": {"stance": "结构性做空"}}},
            },
        }
    )

    assert pricing_task["id"].startswith("rw_")
    assert cross_task["status"] == "new"
    assert len(store.list_tasks(task_type="pricing")) == 1
    assert len(store.list_tasks(task_type="macro_mispricing")) == 1
    assert len(store.list_tasks(task_type="trade_thesis")) == 1
    assert pricing_task["board_order"] == 0
    assert macro_task["board_order"] == 1
    assert cross_task["board_order"] == 2
    assert thesis_task["board_order"] == 3
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
    assert stats["total"] == 4
    assert stats["status_counts"]["in_progress"] == 1
    assert stats["type_counts"]["cross_market"] == 1
    assert stats["type_counts"]["macro_mispricing"] == 1
    assert stats["type_counts"]["trade_thesis"] == 1
    assert stats["with_timeline"] == 4

    reloaded_store = ResearchWorkbenchStore(storage_path=tmp_path / "research_workbench")
    assert len(reloaded_store.list_tasks()) == 4


def test_research_workbench_store_aggregates_snapshot_view_queues_in_stats(tmp_path):
    store = ResearchWorkbenchStore(storage_path=tmp_path / "research_workbench")

    store.create_task(
        {
            "type": "pricing",
            "title": "[Pricing] AAPL mispricing review",
            "symbol": "AAPL",
            "snapshot": {
                "headline": "AAPL snapshot",
                "payload": {
                    "view_context": {
                        "summary": "快速视图：自动排序升档 · 类型：Pricing",
                        "view_fingerprint": "wv_pricing_focus",
                        "scoped_task_label": "当前定位：rw_aapl",
                    }
                },
            },
        }
    )
    store.create_task(
        {
            "type": "pricing",
            "title": "[Pricing] MSFT mispricing review",
            "symbol": "MSFT",
            "snapshot": {
                "headline": "MSFT snapshot",
                "payload": {
                    "view_context": {
                        "summary": "快速视图：自动排序升档 · 类型：Pricing",
                        "view_fingerprint": "wv_pricing_focus",
                    }
                },
            },
        }
    )
    store.create_task(
        {
            "type": "cross_market",
            "title": "[CrossMarket] Utilities hedge",
            "template": "utilities_vs_growth",
            "snapshot": {
                "headline": "Utilities hedge snapshot",
                "payload": {
                    "view_context": {
                        "summary": "快速视图：自动排序缓和 · 类型：Cross-Market",
                        "view_fingerprint": "wv_cross_relaxed",
                        "scoped_task_label": "当前定位：rw_hedge",
                    }
                },
            },
        }
    )

    stats = store.get_stats()

    assert len(stats["snapshot_view_queues"]) == 2
    assert stats["snapshot_view_queues"][0]["label"] == "快速视图：自动排序升档 · 类型：Pricing"
    assert stats["snapshot_view_queues"][0]["fingerprint"] == "wv_pricing_focus"
    assert stats["snapshot_view_queues"][0]["count"] == 2
    assert stats["snapshot_view_queues"][0]["scoped_count"] == 1
    assert stats["snapshot_view_queues"][0]["type_counts"]["pricing"] == 2
    assert stats["snapshot_view_queues"][1]["fingerprint"] == "wv_cross_relaxed"
    assert stats["snapshot_view_queues"][1]["type_counts"]["cross_market"] == 1


def test_research_workbench_store_bulk_updates_status_and_comment(tmp_path):
    store = ResearchWorkbenchStore(storage_path=tmp_path / "research_workbench")
    task_one = store.create_task({"type": "pricing", "title": "task one", "symbol": "AAPL"})
    task_two = store.create_task({"type": "pricing", "title": "task two", "symbol": "MSFT"})

    updated = store.bulk_update_tasks(
        [task_one["id"], task_two["id"]],
        status="in_progress",
        comment="批量复盘：快速视图：自动排序升档 · 类型：Pricing",
        author="local",
    )

    assert len(updated) == 2
    assert all(item["status"] == "in_progress" for item in updated)
    assert all(item["comments"][0]["body"] == "批量复盘：快速视图：自动排序升档 · 类型：Pricing" for item in updated)
    assert all(item["timeline"][0]["type"] == "status_changed" for item in updated)
    assert all(item["timeline"][1]["type"] == "comment_added" for item in updated)


def test_research_workbench_store_persists_refresh_priority_event_on_create(tmp_path):
    store = ResearchWorkbenchStore(storage_path=tmp_path / "research_workbench")
    task = store.create_task(
        {
            "type": "pricing",
            "title": "[Pricing] AAPL mispricing review",
            "symbol": "AAPL",
            "snapshot": {"headline": "AAPL task", "payload": {"gap_analysis": {"gap_pct": 0.12}}},
            "refresh_priority_event": {
                "reason_key": "structural_decay",
                "reason_label": "结构衰败/系统雷达",
                "severity": "high",
                "lead": "结构性衰败警报，主导失效模式偏向 组织与治理稀释。",
                "detail": "衰败分 0.74；主导失效 组织与治理稀释",
            },
        }
    )

    assert task["timeline"][0]["type"] == "refresh_priority"
    assert task["timeline"][1]["type"] == "snapshot_saved"
    assert task["timeline"][2]["type"] == "created"


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
            "payload": {
                "gap_analysis": {"gap_pct": 0.11},
                "view_context": {
                    "summary": "快速视图：自动排序升档 · 类型：Pricing",
                    "view_fingerprint": "wv_focus_pricing",
                    "scoped_task_label": "当前定位：rw_focus_1",
                    "note": "这次快照是在带筛选的工作台视图下保存的。",
                },
            },
        },
    )
    assert updated["snapshot"]["headline"] == "new snapshot"
    assert updated["snapshot_history"][0]["headline"] == "new snapshot"

    timeline = store.get_timeline(task["id"])
    assert timeline[0]["type"] == "snapshot_saved"
    assert "视图 快速视图：自动排序升档 · 类型：Pricing" in timeline[0]["detail"]
    assert timeline[0]["meta"]["view_context_summary"] == "快速视图：自动排序升档 · 类型：Pricing"
    assert timeline[0]["meta"]["view_context_fingerprint"] == "wv_focus_pricing"
    assert timeline[0]["meta"]["view_context_scoped_task_label"] == "当前定位：rw_focus_1"
    assert timeline[0]["meta"]["view_context_note"] == "这次快照是在带筛选的工作台视图下保存的。"
    assert any(event["type"] == "comment_added" for event in timeline)

    assert store.delete_comment(task["id"], comment["id"]) is True
    assert store.delete_comment(task["id"], comment["id"]) is False


def test_research_workbench_store_persists_refresh_priority_events(tmp_path):
    store = ResearchWorkbenchStore(storage_path=tmp_path / "research_workbench")
    task = store.create_task({"type": "cross_market", "title": "task", "template": "utilities_vs_growth"})

    updated = store.update_task(
        task["id"],
        {
            "status": "blocked",
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

    assert updated["timeline"][0]["type"] == "refresh_priority"
    assert updated["timeline"][0]["label"] == "系统自动重排：结构衰败/系统雷达"
    assert updated["timeline"][0]["meta"]["priority_reason"] == "structural_decay"
    assert updated["timeline"][1]["type"] == "status_changed"

    refreshed = store.add_snapshot(
        task["id"],
        {"headline": "snapshot", "payload": {"total_return": 0.12}},
        refresh_priority_event={
            "reason_key": "selection_quality_active",
            "reason_label": "降级运行",
            "severity": "medium",
            "lead": "当前保存结果已经处于降级运行状态",
            "detail": "紧急度 4.0；排序权重 2.2",
        },
    )

    assert refreshed["timeline"][0]["type"] == "refresh_priority"
    assert refreshed["timeline"][0]["meta"]["priority_reason"] == "selection_quality_active"
    assert refreshed["timeline"][1]["type"] == "snapshot_saved"


def test_research_workbench_store_deduplicates_identical_refresh_priority_events(tmp_path):
    store = ResearchWorkbenchStore(storage_path=tmp_path / "research_workbench")
    task = store.create_task({"type": "cross_market", "title": "task", "template": "utilities_vs_growth"})
    refresh_priority_event = {
        "reason_key": "structural_decay",
        "reason_label": "结构衰败/系统雷达",
        "severity": "high",
        "lead": "系统级结构衰败雷达已升级到警报区",
        "detail": "紧急度 5.0；建议先收缩风险预算。",
        "urgency_score": 5.0,
        "priority_weight": 3.4,
    }

    updated = store.update_task(
        task["id"],
        {
            "status": "blocked",
            "refresh_priority_event": refresh_priority_event,
        },
    )
    refreshed = store.add_snapshot(
        task["id"],
        {"headline": "snapshot", "payload": {"total_return": 0.12}},
        refresh_priority_event=refresh_priority_event,
    )

    assert updated["timeline"][0]["type"] == "refresh_priority"
    assert refreshed["timeline"][0]["type"] == "snapshot_saved"
    assert sum(1 for event in refreshed["timeline"] if event["type"] == "refresh_priority") == 1


def test_research_workbench_store_marks_refresh_priority_escalation(tmp_path):
    store = ResearchWorkbenchStore(storage_path=tmp_path / "research_workbench")
    task = store.create_task({"type": "cross_market", "title": "task", "template": "utilities_vs_growth"})

    store.update_task(
        task["id"],
        {
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
    escalated = store.add_snapshot(
        task["id"],
        {"headline": "snapshot", "payload": {"total_return": 0.12}},
        refresh_priority_event={
            "reason_key": "structural_decay",
            "reason_label": "结构衰败/系统雷达",
            "severity": "high",
            "lead": "系统级结构衰败雷达已升级到警报区",
            "detail": "紧急度 5.0；建议先收缩风险预算。",
            "urgency_score": 5.0,
            "priority_weight": 3.4,
        },
    )

    assert escalated["timeline"][0]["label"] == "系统自动重排升级：结构衰败/系统雷达"
    assert escalated["timeline"][0]["meta"]["change_type"] == "escalated"
    assert escalated["timeline"][0]["meta"]["previous_reason_label"] == "人的维度"
    assert escalated["timeline"][0]["meta"]["urgency_delta"] == 2.0


def test_research_workbench_store_backfills_board_order_and_reorders(tmp_path):
    storage = tmp_path / "research_workbench"
    storage.mkdir(parents=True, exist_ok=True)
    (storage / "tasks.json").write_text(
        json.dumps(
            [
                {
                    "id": "rw_old_1",
                    "type": "pricing",
                    "title": "task 1",
                    "status": "new",
                    "updated_at": "2026-03-17T10:00:00",
                    "created_at": "2026-03-17T10:00:00",
                },
                {
                    "id": "rw_old_2",
                    "type": "pricing",
                    "title": "task 2",
                    "status": "new",
                    "updated_at": "2026-03-17T09:00:00",
                    "created_at": "2026-03-17T09:00:00",
                },
            ]
        ),
        encoding="utf-8",
    )

    store = ResearchWorkbenchStore(storage_path=storage)
    board_tasks = store.list_tasks(view="board")
    assert board_tasks[0]["board_order"] == 0
    assert board_tasks[1]["board_order"] == 1

    store.reorder_board(
        [
            {
                "task_id": "rw_old_1",
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
            {"task_id": "rw_old_2", "status": "new", "board_order": 0},
        ]
    )
    moved = store.get_task("rw_old_1")
    assert moved["status"] == "in_progress"
    assert moved["board_order"] == 0
    assert moved["timeline"][0]["type"] == "refresh_priority"
    assert moved["timeline"][1]["type"] == "status_changed"

    restored = store.update_task("rw_old_1", {"status": "archived"})
    assert restored["status"] == "archived"
    reopened = store.update_task("rw_old_1", {"status": "new"})
    assert reopened["status"] == "new"
    assert reopened["board_order"] == 1


def test_research_workbench_store_delete(tmp_path):
    store = ResearchWorkbenchStore(storage_path=tmp_path / "research_workbench")
    task = store.create_task({"type": "pricing", "title": "task"})

    assert store.delete_task(task["id"]) is True
    assert store.get_task(task["id"]) is None
    assert store.delete_task(task["id"]) is False


def test_research_workbench_store_supports_buffered_persistence(tmp_path):
    storage = tmp_path / "research_workbench"
    store = ResearchWorkbenchStore(
        storage_path=storage,
        persist_immediately=False,
        persist_debounce_ms=10_000,
    )

    task = store.create_task({"type": "pricing", "title": "buffered task", "symbol": "AAPL"})

    assert task["id"].startswith("rw_")
    assert not (storage / "tasks.json").exists()

    store.flush()

    reloaded_store = ResearchWorkbenchStore(storage_path=storage)
    persisted = reloaded_store.list_tasks()
    assert len(persisted) == 1
    assert persisted[0]["title"] == "buffered task"
