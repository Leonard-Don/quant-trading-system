import json
from datetime import datetime

import pytest

from backend.app.services.research_journal import (
    MAX_RESEARCH_JOURNAL_SOURCE_BYTES,
    MAX_RESEARCH_JOURNAL_TAGS,
    ResearchJournalStore,
)


def test_research_journal_store_normalizes_entries_and_builds_summary(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    updated = store.update_snapshot({
        "entries": [
            {
                "id": "bt-1",
                "type": "backtest",
                "title": "AAPL 回测快照",
                "symbol": " aapl ",
                "status": "open",
                "priority": "high",
                "metrics": {"total_return": 0.12},
            },
            {
                "id": "industry-1",
                "type": "industry_watch",
                "title": "半导体观察",
                "industry": "半导体",
                "status": "watching",
                "priority": "medium",
            },
            {
                "id": "ignored",
                "type": "unknown_type",
                "title": "fallback",
                "status": "not-valid",
                "priority": "not-valid",
            },
        ],
        "source_state": {"backtest": {"count": 1}},
    })

    assert updated["entries"][0]["symbol"] == "AAPL"
    fallback_entry = next(entry for entry in updated["entries"] if entry["id"] == "ignored")
    assert fallback_entry["type"] == "manual"
    assert fallback_entry["status"] == "open"
    assert updated["summary"]["total_entries"] == 3
    assert updated["summary"]["type_counts"]["backtest"] == 1
    assert updated["summary"]["top_symbols"][0]["symbol"] == "AAPL"
    assert updated["summary"]["next_actions"][0]["key"] == "review_backtests"


def test_research_journal_store_isolated_by_profile_id(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    store.update_snapshot({
        "entries": [{"id": "entry-a", "type": "manual", "title": "A"}],
    }, profile_id="profile-a")
    store.update_snapshot({
        "entries": [{"id": "entry-b", "type": "manual", "title": "B"}],
    }, profile_id="profile-b")

    assert store.get_snapshot(profile_id="profile-a")["entries"][0]["id"] == "entry-a"
    assert store.get_snapshot(profile_id="profile-b")["entries"][0]["id"] == "entry-b"


def test_research_journal_store_adds_entry_and_updates_status(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    added = store.add_entry({
        "id": "manual-1",
        "type": "manual",
        "title": "盘前计划",
        "status": "open",
    })
    assert added["entries"][0]["id"] == "manual-1"

    updated = store.update_entry_status("manual-1", "done")
    assert updated["entries"][0]["status"] == "done"


def test_research_journal_store_normalizes_tags_with_dedup_trim_and_cap(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "tagged",
                "type": "manual",
                "title": "标签整理",
                "tags": ["a", " a ", "   ", "b", "c", "d", "e", "f", "g", "h", "i"],
            },
            {
                "id": "wrong-shape",
                "type": "manual",
                "title": "tags shape",
                "tags": "not-a-list",
            },
        ],
    })

    by_id = {entry["id"]: entry for entry in snapshot["entries"]}
    expected_tags = list("abcdefgh")[:MAX_RESEARCH_JOURNAL_TAGS]
    assert by_id["tagged"]["tags"] == expected_tags
    assert len(by_id["tagged"]["tags"]) == MAX_RESEARCH_JOURNAL_TAGS
    assert by_id["wrong-shape"]["tags"] == []


def test_research_journal_store_dedupes_entries_keeping_newest_updated_at(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "duplicate",
                "type": "manual",
                "title": "older",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": "duplicate",
                "type": "manual",
                "title": "newer",
                "updated_at": "2026-05-01T00:00:00+00:00",
            },
        ],
    })

    assert len(snapshot["entries"]) == 1
    assert snapshot["entries"][0]["title"] == "newer"


def test_research_journal_store_sorts_entries_by_status_then_priority(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {"id": "archived-high", "type": "manual", "title": "archived",
             "status": "archived", "priority": "high"},
            {"id": "open-low", "type": "manual", "title": "open low",
             "status": "open", "priority": "low"},
            {"id": "open-high", "type": "manual", "title": "open high",
             "status": "open", "priority": "high"},
            {"id": "done-medium", "type": "manual", "title": "done",
             "status": "done", "priority": "medium"},
        ],
    })

    ordered_ids = [entry["id"] for entry in snapshot["entries"]]
    assert ordered_ids == ["open-high", "open-low", "done-medium", "archived-high"]


def test_research_journal_store_sanitizes_unsafe_profile_ids(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    store.update_snapshot(
        {"entries": [{"id": "x", "type": "manual", "title": "p"}]},
        profile_id="../escape/../profile",
    )

    written = list(tmp_path.glob("*.json"))
    assert len(written) == 1
    filename = written[0].name
    assert ".." not in filename
    assert "/" not in filename
    assert "\\" not in filename

    snapshot = store.get_snapshot(profile_id="../escape/../profile")
    assert snapshot["entries"][0]["id"] == "x"


def test_research_journal_store_truncates_oversized_source_state(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    huge_blob = "a" * (MAX_RESEARCH_JOURNAL_SOURCE_BYTES + 32 * 1024)
    snapshot = store.update_snapshot({
        "entries": [{"id": "x", "type": "manual", "title": "p"}],
        "source_state": {"blob": huge_blob},
    })

    assert snapshot["source_state"]["truncated"] is True
    assert snapshot["source_state"]["original_size_bytes"] >= len(huge_blob)
    assert "blob" not in snapshot["source_state"]


def test_research_journal_store_handles_cyclic_source_state(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    cyclic: dict[str, object] = {"secret_blob": "a" * 4096}
    cyclic["self"] = cyclic

    snapshot = store.update_snapshot({
        "entries": [{"id": "x", "type": "manual", "title": "p"}],
        "source_state": cyclic,
    })

    assert snapshot["source_state"].get("truncated") is True
    assert "secret_blob" not in snapshot["source_state"]
    assert "self" not in snapshot["source_state"]


def test_research_journal_store_strips_unserializable_nested_source_state_values(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [{"id": "x", "type": "manual", "title": "p"}],
        "source_state": {"audit_set": {1, 2, 3}, "raw_bytes": b"\x00\xff"},
    })

    json.dumps(snapshot["source_state"])
    assert set(snapshot["source_state"]) == {"audit_set", "raw_bytes"}

    written = list(tmp_path.glob("*.json"))
    assert len(written) == 1
    with open(written[0], encoding="utf-8") as fh:
        reloaded = json.load(fh)
    json.dumps(reloaded["source_state"])
    assert reloaded["source_state"] == snapshot["source_state"]


def test_research_journal_store_coerces_tuple_source_state_values_to_lists(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [{"id": "x", "type": "manual", "title": "p"}],
        "source_state": {
            "pair": (1, 2),
            "nested": {"trio": (3, 4, 5)},
            "mixed": [0, (6, 7), 8],
        },
    })

    assert snapshot["source_state"]["pair"] == [1, 2]
    assert isinstance(snapshot["source_state"]["pair"], list)
    assert snapshot["source_state"]["nested"]["trio"] == [3, 4, 5]
    assert isinstance(snapshot["source_state"]["nested"]["trio"], list)
    assert snapshot["source_state"]["mixed"] == [0, [6, 7], 8]
    assert isinstance(snapshot["source_state"]["mixed"][1], list)

    reloaded = store.get_snapshot()
    assert reloaded["source_state"] == snapshot["source_state"]


def test_research_journal_store_stringifies_non_string_source_state_keys(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [{"id": "x", "type": "manual", "title": "p"}],
        "source_state": {
            1: "top_level_int",
            "nested": {2: "nested_int", 3: {4: "deep_int"}},
        },
    })

    assert all(isinstance(key, str) for key in snapshot["source_state"])
    assert all(isinstance(key, str) for key in snapshot["source_state"]["nested"])
    assert all(isinstance(key, str) for key in snapshot["source_state"]["nested"]["3"])
    assert snapshot["source_state"]["1"] == "top_level_int"
    assert snapshot["source_state"]["nested"]["2"] == "nested_int"
    assert snapshot["source_state"]["nested"]["3"]["4"] == "deep_int"

    reloaded = store.get_snapshot()
    assert reloaded["source_state"] == snapshot["source_state"]


def test_research_journal_store_coerces_tuple_entry_mapping_values_to_lists(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "json-entry",
                "type": "manual",
                "title": "json-ready",
                "metrics": {"history": (1, 2, 3), "nested": {"pair": (4, 5)}},
                "action": {"steps": (10, 20)},
                "raw": {"tuple_field": (7, 8)},
            },
        ],
    })

    entry = next(e for e in snapshot["entries"] if e["id"] == "json-entry")
    json.dumps(entry["metrics"])
    json.dumps(entry["action"])
    json.dumps(entry["raw"])
    assert entry["metrics"]["history"] == [1, 2, 3]
    assert isinstance(entry["metrics"]["history"], list)
    assert entry["metrics"]["nested"]["pair"] == [4, 5]
    assert isinstance(entry["metrics"]["nested"]["pair"], list)
    assert entry["action"]["steps"] == [10, 20]
    assert entry["raw"]["tuple_field"] == [7, 8]

    reloaded = store.get_snapshot()
    reloaded_entry = next(e for e in reloaded["entries"] if e["id"] == "json-entry")
    assert reloaded_entry["metrics"] == entry["metrics"]
    assert reloaded_entry["action"] == entry["action"]
    assert reloaded_entry["raw"] == entry["raw"]


def test_research_journal_store_summary_action_queue_entries_are_independent_copies(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "alert-1",
                "type": "realtime_alert",
                "title": "alert",
                "status": "open",
                "priority": "high",
                "metrics": {"score": 0.5},
            },
        ],
    })

    queue_entry = snapshot["summary"]["action_queue"][0]
    queue_entry["metrics"]["score"] = 999
    queue_entry["metrics"]["leaked"] = True

    main_entry = next(e for e in snapshot["entries"] if e["id"] == "alert-1")
    assert main_entry["metrics"] == {"score": 0.5}


def test_research_journal_store_summary_symbol_timeline_entries_are_independent_copies(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "alert-1",
                "type": "realtime_alert",
                "title": "alert",
                "symbol": "AAPL",
                "status": "open",
                "priority": "high",
                "metrics": {"score": 0.5},
            },
        ],
    })

    timeline_view = snapshot["summary"]["symbol_timeline"][0]
    assert timeline_view["symbol"] == "AAPL"
    timeline_entry = timeline_view["entries"][0]
    timeline_entry["metrics"]["score"] = 999
    timeline_entry["metrics"]["leaked"] = True
    timeline_entry["status"] = "archived"

    main_entry = next(e for e in snapshot["entries"] if e["id"] == "alert-1")
    assert main_entry["metrics"] == {"score": 0.5}
    assert main_entry["status"] == "open"


def test_research_journal_store_update_entry_status_rejects_invalid_status(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)
    store.add_entry({"id": "valid", "type": "manual", "title": "valid"})

    with pytest.raises(ValueError):
        store.update_entry_status("valid", "frozen")

    with pytest.raises(KeyError):
        store.update_entry_status("missing", "done")


@pytest.mark.parametrize(
    "invalid_entry",
    [None, [], "not-a-dict", 42, ("id", "manual"), {"id", "manual"}],
)
def test_research_journal_store_add_entry_rejects_non_dict_input(tmp_path, invalid_entry):
    store = ResearchJournalStore(storage_path=tmp_path)

    with pytest.raises(ValueError, match="entry must be an object"):
        store.add_entry(invalid_entry)

    assert list(tmp_path.glob("*.json")) == []
    assert store.get_snapshot()["entries"] == []


def test_research_journal_store_preserves_z_suffix_and_falls_back_on_invalid_iso(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "z-date",
                "type": "manual",
                "title": "z-suffix",
                "created_at": "2026-05-02T00:00:00Z",
                "updated_at": "2026-05-03T00:00:00Z",
            },
            {
                "id": "bad-date",
                "type": "manual",
                "title": "bad",
                "created_at": "not-a-date",
                "updated_at": "also-bad",
            },
        ],
    })

    by_id = {entry["id"]: entry for entry in snapshot["entries"]}
    assert by_id["z-date"]["created_at"] == "2026-05-02T00:00:00Z"
    assert by_id["z-date"]["updated_at"] == "2026-05-03T00:00:00Z"

    bad_entry = by_id["bad-date"]
    datetime.fromisoformat(bad_entry["created_at"].replace("Z", "+00:00"))
    assert bad_entry["created_at"] == bad_entry["updated_at"]
