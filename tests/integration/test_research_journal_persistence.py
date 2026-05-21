"""Integration coverage for the research journal disk persistence cycle.

The unit suite asserts in-memory normalization on a per-call basis
(``tests/unit/test_research_journal.py``) and the contract suite mocks
``research_journal_store`` so it never touches disk
(``tests/integration/test_research_journal_contracts.py``). This file
walks the full lifecycle through real files on a ``tmp_path`` fixture:
snapshot write, entry add, status archive, profile-scoped reads, and a
process-restart-style reload via a freshly constructed store on the
same path -- mirroring the ``test_paper_trading_lifecycle.py`` pattern.

Mapping note: spec D4 item 4 lists the lifecycle as
"write -> list -> read -> archive -> delete", but
``backend/app/services/research_journal.py`` does not expose a delete
operation. The closest terminal state in ``ENTRY_STATUSES`` is the
``archived`` status, so that's the cycle endpoint exercised here.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.services.research_journal import ResearchJournalStore

PROFILE = "lifecycle-tester"


def _backtest_entry(entry_id: str, symbol: str, status: str = "open") -> dict:
    return {
        "id": entry_id,
        "type": "backtest",
        "title": f"{symbol} 回测快照",
        "symbol": symbol,
        "status": status,
        "priority": "high",
        "metrics": {"total_return": 0.15, "sharpe": 1.2},
    }


def test_research_journal_lifecycle_round_trips_through_disk(tmp_path: Path):
    """Snapshot write -> add -> archive must survive a process restart."""
    store = ResearchJournalStore(storage_path=tmp_path)

    initial = store.update_snapshot(
        {"entries": [_backtest_entry("bt-1", "AAPL")]},
        profile_id=PROFILE,
    )
    assert initial["summary"]["total_entries"] == 1

    journal_file = tmp_path / f"{PROFILE}.json"
    assert journal_file.exists()
    on_disk = json.loads(journal_file.read_text(encoding="utf-8"))
    assert {entry["id"] for entry in on_disk["entries"]} == {"bt-1"}

    after_add = store.add_entry(
        _backtest_entry("bt-2", "GOOG", status="watching"),
        profile_id=PROFILE,
    )
    assert {entry["id"] for entry in after_add["entries"]} == {"bt-1", "bt-2"}

    archived = store.update_entry_status("bt-1", "archived", profile_id=PROFILE)
    archived_entry = next(entry for entry in archived["entries"] if entry["id"] == "bt-1")
    assert archived_entry["status"] == "archived"

    reloaded_store = ResearchJournalStore(storage_path=tmp_path)
    snapshot = reloaded_store.get_snapshot(profile_id=PROFILE)

    by_id = {entry["id"]: entry for entry in snapshot["entries"]}
    assert by_id["bt-1"]["status"] == "archived"
    assert by_id["bt-2"]["status"] == "watching"
    assert by_id["bt-1"]["symbol"] == "AAPL"
    assert by_id["bt-2"]["title"] == "GOOG 回测快照"
    assert by_id["bt-1"]["metrics"]["total_return"] == 0.15


def test_research_journal_writes_separate_files_per_profile(tmp_path: Path):
    """Each profile must persist to its own JSON file with no bleed-through."""
    store = ResearchJournalStore(storage_path=tmp_path)

    store.update_snapshot(
        {"entries": [_backtest_entry("bt-a", "AAPL")]},
        profile_id="profile-a",
    )
    store.update_snapshot(
        {"entries": [_backtest_entry("bt-b", "GOOG")]},
        profile_id="profile-b",
    )

    file_a = tmp_path / "profile-a.json"
    file_b = tmp_path / "profile-b.json"
    assert file_a.exists() and file_b.exists()

    payload_a = json.loads(file_a.read_text(encoding="utf-8"))
    payload_b = json.loads(file_b.read_text(encoding="utf-8"))
    assert {entry["id"] for entry in payload_a["entries"]} == {"bt-a"}
    assert {entry["id"] for entry in payload_b["entries"]} == {"bt-b"}

    snap_a = store.get_snapshot(profile_id="profile-a")
    snap_b = store.get_snapshot(profile_id="profile-b")
    assert {entry["id"] for entry in snap_a["entries"]} == {"bt-a"}
    assert {entry["id"] for entry in snap_b["entries"]} == {"bt-b"}


def test_research_journal_recovers_from_corrupted_journal_file(tmp_path: Path):
    """A malformed file must not crash get_snapshot; a follow-up write heals it."""
    store = ResearchJournalStore(storage_path=tmp_path)
    journal_file = tmp_path / f"{PROFILE}.json"
    journal_file.write_text("{not valid json", encoding="utf-8")

    snapshot = store.get_snapshot(profile_id=PROFILE)
    assert snapshot["entries"] == []
    assert snapshot["summary"]["total_entries"] == 0

    store.update_snapshot(
        {"entries": [_backtest_entry("bt-recover", "MSFT")]},
        profile_id=PROFILE,
    )
    repaired = json.loads(journal_file.read_text(encoding="utf-8"))
    assert {entry["id"] for entry in repaired["entries"]} == {"bt-recover"}


def test_research_journal_endpoints_round_trip_through_real_disk(
    tmp_path: Path, monkeypatch
):
    """PUT/POST/PATCH/GET endpoints must persist to disk and read back consistently."""
    isolated_store = ResearchJournalStore(storage_path=tmp_path)
    monkeypatch.setattr(
        "backend.app.api.v1.endpoints.research_journal.research_journal_store",
        isolated_store,
    )
    from backend.main import app

    client = TestClient(app)
    headers = {"X-Research-Profile": PROFILE}

    put_response = client.put(
        "/research-journal/snapshot",
        headers=headers,
        json={"entries": [_backtest_entry("bt-1", "AAPL")]},
    )
    assert put_response.status_code == 200, put_response.text

    post_response = client.post(
        "/research-journal/entries",
        headers=headers,
        json={"entry": _backtest_entry("bt-2", "GOOG", status="watching")},
    )
    assert post_response.status_code == 200, post_response.text

    archive_response = client.patch(
        "/research-journal/entries/bt-1/status",
        headers=headers,
        json={"status": "archived"},
    )
    assert archive_response.status_code == 200, archive_response.text

    get_response = client.get("/research-journal/snapshot", headers=headers)
    assert get_response.status_code == 200, get_response.text
    data = get_response.json()["data"]
    by_id = {entry["id"]: entry for entry in data["entries"]}
    assert by_id["bt-1"]["status"] == "archived"
    assert by_id["bt-2"]["status"] == "watching"

    fresh_store = ResearchJournalStore(storage_path=tmp_path)
    fresh_snapshot = fresh_store.get_snapshot(profile_id=PROFILE)
    fresh_by_id = {entry["id"]: entry for entry in fresh_snapshot["entries"]}
    assert fresh_by_id["bt-1"]["status"] == "archived"
    assert fresh_by_id["bt-2"]["title"] == "GOOG 回测快照"
