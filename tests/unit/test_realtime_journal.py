from backend.app.services.realtime_journal import RealtimeJournalStore


def test_realtime_journal_store_limits_snapshot_and_timeline_counts(tmp_path):
    store = RealtimeJournalStore(storage_path=tmp_path)

    updated = store.update_journal({
        "review_snapshots": [{"id": f"snapshot-{index}"} for index in range(60)],
        "timeline_events": [{"id": f"event-{index}"} for index in range(140)],
    })

    assert len(updated["review_snapshots"]) == 48
    assert len(updated["timeline_events"]) == 120
    assert updated["review_snapshots"][0]["id"] == "snapshot-0"
    assert updated["timeline_events"][0]["id"] == "event-0"


def test_realtime_journal_store_isolated_by_profile_id(tmp_path):
    store = RealtimeJournalStore(storage_path=tmp_path)

    store.update_journal({
        "review_snapshots": [{"id": "snapshot-a"}],
        "timeline_events": [{"id": "event-a"}],
    }, profile_id="browser-a")
    store.update_journal({
        "review_snapshots": [{"id": "snapshot-b"}],
        "timeline_events": [{"id": "event-b"}],
    }, profile_id="browser-b")

    assert store.get_journal(profile_id="browser-a") == {
        "review_snapshots": [{"id": "snapshot-a"}],
        "timeline_events": [{"id": "event-a"}],
    }
    assert store.get_journal(profile_id="browser-b") == {
        "review_snapshots": [{"id": "snapshot-b"}],
        "timeline_events": [{"id": "event-b"}],
    }
