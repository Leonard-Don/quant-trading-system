import json
from datetime import datetime

import pytest

from backend.app.services.research_journal import (
    MAX_RESEARCH_JOURNAL_SOURCE_BYTES,
    MAX_RESEARCH_JOURNAL_TAGS,
    ResearchJournalStore,
    _stable_entry_id,
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


def test_research_journal_store_coerces_falsy_non_none_tag_values_to_strings(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "numeric-tags",
                "type": "manual",
                "title": "numeric",
                "tags": [0, 1, "real"],
            },
        ],
    })

    entry = next(e for e in snapshot["entries"] if e["id"] == "numeric-tags")
    assert entry["tags"] == ["0", "1", "real"]


def test_research_journal_store_ignores_boolean_tag_values(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "bool-tags",
                "type": "manual",
                "title": "bool tags",
                "tags": [True, False, "real", 0],
            },
        ],
    })

    entry = next(e for e in snapshot["entries"] if e["id"] == "bool-tags")
    assert "True" not in entry["tags"]
    assert "False" not in entry["tags"]
    assert entry["tags"] == ["real", "0"]


def test_research_journal_store_boolean_tags_do_not_consume_dedupe_or_cap(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "bool-mixed",
                "type": "manual",
                "title": "dedupe-with-bools",
                "tags": [True, "a", False, "a", " a ", "b", True, "c"],
            },
            {
                "id": "bool-cap",
                "type": "manual",
                "title": "cap-with-bools",
                "tags": [True, "a", False, "b", True, "c", "d", "e", "f", "g", "h", "i"],
            },
        ],
    })

    by_id = {entry["id"]: entry for entry in snapshot["entries"]}
    assert by_id["bool-mixed"]["tags"] == ["a", "b", "c"]
    assert by_id["bool-cap"]["tags"] == list("abcdefgh")[:MAX_RESEARCH_JOURNAL_TAGS]
    assert len(by_id["bool-cap"]["tags"]) == MAX_RESEARCH_JOURNAL_TAGS


def test_research_journal_store_preserves_falsy_non_none_summary_values(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "zero-summary",
                "type": "manual",
                "title": "zero",
                "summary": 0,
            },
            {
                "id": "false-summary",
                "type": "manual",
                "title": "false-bool",
                "summary": False,
            },
            {
                "id": "none-summary",
                "type": "manual",
                "title": "none",
                "summary": None,
            },
            {
                "id": "blank-summary",
                "type": "manual",
                "title": "blank",
                "summary": "   ",
            },
        ],
    })

    by_id = {e["id"]: e for e in snapshot["entries"]}
    assert by_id["zero-summary"]["summary"] == "0"
    assert by_id["false-summary"]["summary"] == "False"
    assert by_id["none-summary"]["summary"] == ""
    assert by_id["blank-summary"]["summary"] == ""


def test_research_journal_store_preserves_falsy_non_none_industry_values(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "zero-industry",
                "type": "industry_watch",
                "title": "zero",
                "industry": 0,
                "industry_name": "fallback",
            },
            {
                "id": "false-industry",
                "type": "industry_watch",
                "title": "false-bool",
                "industry": False,
                "industry_name": "fallback",
            },
            {
                "id": "none-industry",
                "type": "industry_watch",
                "title": "none",
                "industry": None,
                "industry_name": "from-name",
            },
            {
                "id": "empty-string-industry",
                "type": "industry_watch",
                "title": "empty-string",
                "industry": "",
                "industry_name": "from-name",
            },
            {
                "id": "blank-industry",
                "type": "industry_watch",
                "title": "blank",
                "industry": "   ",
                "industry_name": "from-name",
            },
        ],
    })

    by_id = {e["id"]: e for e in snapshot["entries"]}
    assert by_id["zero-industry"]["industry"] == "0"
    assert by_id["false-industry"]["industry"] == "False"
    assert by_id["none-industry"]["industry"] == "from-name"
    assert by_id["empty-string-industry"]["industry"] == "from-name"
    assert by_id["blank-industry"]["industry"] == ""


def test_research_journal_store_preserves_falsy_non_none_source_label_values(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "zero-source-label",
                "type": "manual",
                "title": "zero",
                "source_label": 0,
                "sourceLabel": "from-camel",
            },
            {
                "id": "false-source-label",
                "type": "manual",
                "title": "false-bool",
                "source_label": False,
                "sourceLabel": "from-camel",
            },
            {
                "id": "none-source-label",
                "type": "manual",
                "title": "none",
                "source_label": None,
                "sourceLabel": "from-camel",
            },
            {
                "id": "empty-string-source-label",
                "type": "manual",
                "title": "empty-string",
                "source_label": "",
                "sourceLabel": "from-camel",
            },
            {
                "id": "blank-source-label",
                "type": "manual",
                "title": "blank",
                "source_label": "   ",
                "sourceLabel": "from-camel",
            },
        ],
    })

    by_id = {e["id"]: e for e in snapshot["entries"]}
    assert by_id["zero-source-label"]["source_label"] == "0"
    assert by_id["false-source-label"]["source_label"] == "False"
    assert by_id["none-source-label"]["source_label"] == "from-camel"
    assert by_id["empty-string-source-label"]["source_label"] == "from-camel"
    assert by_id["blank-source-label"]["source_label"] == ""


def test_research_journal_store_preserves_falsy_non_none_source_values(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "zero-source",
                "type": "manual",
                "title": "zero",
                "source": 0,
            },
            {
                "id": "false-source",
                "type": "manual",
                "title": "false-bool",
                "source": False,
            },
            {
                "id": "none-source",
                "type": "manual",
                "title": "none",
                "source": None,
            },
            {
                "id": "blank-source",
                "type": "manual",
                "title": "blank",
                "source": "   ",
            },
        ],
    })

    by_id = {e["id"]: e for e in snapshot["entries"]}
    assert by_id["zero-source"]["source"] == "0"
    assert by_id["false-source"]["source"] == "False"
    assert by_id["none-source"]["source"] == "manual"
    assert by_id["blank-source"]["source"] == "manual"


def test_research_journal_store_preserves_falsy_non_none_note_values(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "zero-note",
                "type": "manual",
                "title": "zero",
                "note": 0,
            },
            {
                "id": "false-note",
                "type": "manual",
                "title": "false-bool",
                "note": False,
            },
            {
                "id": "none-note",
                "type": "manual",
                "title": "none",
                "note": None,
            },
            {
                "id": "blank-note",
                "type": "manual",
                "title": "blank",
                "note": "   ",
            },
        ],
    })

    by_id = {e["id"]: e for e in snapshot["entries"]}
    assert by_id["zero-note"]["note"] == "0"
    assert by_id["false-note"]["note"] == "False"
    assert by_id["none-note"]["note"] == ""
    assert by_id["blank-note"]["note"] == ""


def test_research_journal_store_preserves_falsy_non_none_id_values(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": 0,
                "type": "manual",
                "title": "zero-id",
            },
            {
                "id": False,
                "type": "manual",
                "title": "false-id",
            },
        ],
    })

    ids = {entry["id"] for entry in snapshot["entries"]}
    assert "0" in ids
    assert "False" in ids


def test_research_journal_store_preserves_falsy_non_none_title_values(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "zero-title",
                "type": "manual",
                "title": 0,
            },
            {
                "id": "false-title",
                "type": "manual",
                "title": False,
            },
            {
                "id": "none-title",
                "type": "manual",
                "title": None,
            },
            {
                "id": "blank-title",
                "type": "manual",
                "title": "   ",
            },
        ],
    })

    by_id = {e["id"]: e for e in snapshot["entries"]}
    assert by_id["zero-title"]["title"] == "0"
    assert by_id["false-title"]["title"] == "False"
    assert by_id["none-title"]["title"] == "研究记录"
    assert by_id["blank-title"]["title"] == "研究记录"


def test_stable_entry_id_falls_back_to_createdAt_only_for_none_or_empty_created_at():
    base = {"type": "manual", "title": "stable-id"}
    fallback_camel = "2026-01-01T00:00:00Z"

    canonical_id = _stable_entry_id({**base, "created_at": fallback_camel})

    assert _stable_entry_id({**base, "created_at": None, "createdAt": fallback_camel}) == canonical_id
    assert _stable_entry_id({**base, "created_at": "", "createdAt": fallback_camel}) == canonical_id
    assert _stable_entry_id({**base, "createdAt": fallback_camel}) == canonical_id


def test_stable_entry_id_preserves_falsy_non_none_created_at_values():
    base = {"type": "manual", "title": "stable-id"}
    fallback_camel = "2026-01-01T00:00:00Z"

    canonical_id = _stable_entry_id({**base, "created_at": fallback_camel})

    assert _stable_entry_id({**base, "created_at": 0, "createdAt": fallback_camel}) != canonical_id
    assert _stable_entry_id({**base, "created_at": False, "createdAt": fallback_camel}) != canonical_id


def test_research_journal_store_falls_back_to_camelcase_dates_only_for_none_or_empty(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)
    camel_created = "2026-01-01T00:00:00Z"
    camel_updated = "2026-01-02T00:00:00Z"

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "none-dates",
                "type": "manual",
                "title": "none",
                "created_at": None,
                "createdAt": camel_created,
                "updated_at": None,
                "updatedAt": camel_updated,
            },
            {
                "id": "empty-dates",
                "type": "manual",
                "title": "empty",
                "created_at": "",
                "createdAt": camel_created,
                "updated_at": "",
                "updatedAt": camel_updated,
            },
            {
                "id": "missing-dates",
                "type": "manual",
                "title": "missing",
                "createdAt": camel_created,
                "updatedAt": camel_updated,
            },
        ],
    })

    by_id = {e["id"]: e for e in snapshot["entries"]}
    for entry_id in ("none-dates", "empty-dates", "missing-dates"):
        assert by_id[entry_id]["created_at"] == camel_created
        assert by_id[entry_id]["updated_at"] == camel_updated


def test_research_journal_store_preserves_falsy_non_none_created_at_values(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)
    camel_created = "2026-01-01T00:00:00Z"
    camel_updated = "2026-01-02T00:00:00Z"

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "zero-created-at",
                "type": "manual",
                "title": "zero",
                "created_at": 0,
                "createdAt": camel_created,
                "updated_at": camel_updated,
            },
            {
                "id": "false-created-at",
                "type": "manual",
                "title": "false",
                "created_at": False,
                "createdAt": camel_created,
                "updated_at": camel_updated,
            },
        ],
    })

    by_id = {e["id"]: e for e in snapshot["entries"]}
    assert by_id["zero-created-at"]["created_at"] != camel_created
    assert by_id["false-created-at"]["created_at"] != camel_created
    datetime.fromisoformat(by_id["zero-created-at"]["created_at"].replace("Z", "+00:00"))
    datetime.fromisoformat(by_id["false-created-at"]["created_at"].replace("Z", "+00:00"))


def test_research_journal_store_preserves_falsy_non_none_updated_at_values(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)
    camel_created = "2026-01-01T00:00:00Z"
    camel_updated = "2026-01-02T00:00:00Z"

    snapshot = store.update_snapshot({
        "entries": [
            {
                "id": "zero-updated-at",
                "type": "manual",
                "title": "zero",
                "created_at": camel_created,
                "updated_at": 0,
                "updatedAt": camel_updated,
            },
            {
                "id": "false-updated-at",
                "type": "manual",
                "title": "false",
                "created_at": camel_created,
                "updated_at": False,
                "updatedAt": camel_updated,
            },
        ],
    })

    by_id = {e["id"]: e for e in snapshot["entries"]}
    assert by_id["zero-updated-at"]["updated_at"] != camel_updated
    assert by_id["false-updated-at"]["updated_at"] != camel_updated
    assert by_id["zero-updated-at"]["updated_at"] == camel_created
    assert by_id["false-updated-at"]["updated_at"] == camel_created


def test_research_journal_store_falls_back_to_camelcase_generated_at_only_for_none_or_empty(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)
    camel_generated = "2026-01-01T00:00:00Z"

    snapshot_none = store.update_snapshot({
        "entries": [],
        "generated_at": None,
        "generatedAt": camel_generated,
    })
    assert snapshot_none["generated_at"] == camel_generated

    snapshot_empty = store.update_snapshot({
        "entries": [],
        "generated_at": "",
        "generatedAt": camel_generated,
    })
    assert snapshot_empty["generated_at"] == camel_generated

    snapshot_missing = store.update_snapshot({
        "entries": [],
        "generatedAt": camel_generated,
    })
    assert snapshot_missing["generated_at"] == camel_generated


def test_research_journal_store_preserves_falsy_non_none_generated_at_values(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)
    camel_generated = "2026-01-01T00:00:00Z"

    snapshot_zero = store.update_snapshot({
        "entries": [],
        "generated_at": 0,
        "generatedAt": camel_generated,
    })
    assert snapshot_zero["generated_at"] != camel_generated
    datetime.fromisoformat(snapshot_zero["generated_at"].replace("Z", "+00:00"))

    snapshot_false = store.update_snapshot({
        "entries": [],
        "generated_at": False,
        "generatedAt": camel_generated,
    })
    assert snapshot_false["generated_at"] != camel_generated
    datetime.fromisoformat(snapshot_false["generated_at"].replace("Z", "+00:00"))


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


def test_research_journal_store_treats_none_and_blank_profile_ids_as_default(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    store.update_snapshot(
        {"entries": [{"id": "default-entry", "type": "manual", "title": "default"}]},
        profile_id=None,
    )

    assert store.get_snapshot(profile_id=None)["entries"][0]["id"] == "default-entry"
    assert store.get_snapshot(profile_id="")["entries"][0]["id"] == "default-entry"
    assert store.get_snapshot(profile_id="   ")["entries"][0]["id"] == "default-entry"

    written = {p.name for p in tmp_path.glob("*.json")}
    assert written == {"default.json"}


def test_research_journal_store_preserves_falsy_non_none_profile_ids(tmp_path):
    store = ResearchJournalStore(storage_path=tmp_path)

    store.update_snapshot(
        {"entries": [{"id": "default-entry", "type": "manual", "title": "default"}]},
        profile_id=None,
    )
    store.update_snapshot(
        {"entries": [{"id": "zero-entry", "type": "manual", "title": "zero"}]},
        profile_id=0,
    )
    store.update_snapshot(
        {"entries": [{"id": "false-entry", "type": "manual", "title": "false"}]},
        profile_id=False,
    )

    assert store.get_snapshot(profile_id=None)["entries"][0]["id"] == "default-entry"
    assert store.get_snapshot(profile_id=0)["entries"][0]["id"] == "zero-entry"
    assert store.get_snapshot(profile_id=False)["entries"][0]["id"] == "false-entry"

    written = {p.name for p in tmp_path.glob("*.json")}
    assert "default.json" in written
    assert "0.json" in written
    assert "false.json" in written


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
