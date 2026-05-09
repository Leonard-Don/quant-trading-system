from backend.app.services.realtime_journal import (
    MAX_REVIEW_SNAPSHOTS,
    MAX_TIMELINE_EVENTS,
    RealtimeJournalStore,
)


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


def test_update_journal_emits_truncation_warnings_when_limits_exceeded(tmp_path):
    store = RealtimeJournalStore(storage_path=tmp_path)

    snapshot_overflow = MAX_REVIEW_SNAPSHOTS + 5
    event_overflow = MAX_TIMELINE_EVENTS + 7
    result = store.update_journal({
        "review_snapshots": [{"id": f"s-{i}"} for i in range(snapshot_overflow)],
        "timeline_events": [{"id": f"e-{i}"} for i in range(event_overflow)],
    })

    warnings = result["_warnings"]
    assert any(
        f"review_snapshots truncated from {snapshot_overflow} to {MAX_REVIEW_SNAPSHOTS}" in warning
        for warning in warnings
    )
    assert any(
        f"timeline_events truncated from {event_overflow} to {MAX_TIMELINE_EVENTS}" in warning
        for warning in warnings
    )


def test_update_journal_omits_warnings_when_within_limits(tmp_path):
    store = RealtimeJournalStore(storage_path=tmp_path)

    result = store.update_journal({
        "review_snapshots": [{"id": "s-only"}],
        "timeline_events": [{"id": "e-only"}],
    })

    assert "_warnings" not in result


def test_realtime_journal_store_sanitizes_unsafe_profile_ids(tmp_path):
    store = RealtimeJournalStore(storage_path=tmp_path)

    store.update_journal(
        {
            "review_snapshots": [{"id": "guarded"}],
            "timeline_events": [{"id": "guarded-event"}],
        },
        profile_id="../escape/../profile",
    )

    written = list(tmp_path.glob("*.json"))
    assert len(written) == 1
    filename = written[0].name
    assert ".." not in filename
    assert "/" not in filename
    assert "\\" not in filename

    journal = store.get_journal(profile_id="../escape/../profile")
    assert journal["review_snapshots"] == [{"id": "guarded"}]
    assert journal["timeline_events"] == [{"id": "guarded-event"}]
