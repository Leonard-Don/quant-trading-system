from backend.app.services.research_journal import ResearchJournalStore


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
