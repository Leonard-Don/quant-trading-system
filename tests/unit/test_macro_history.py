from src.analytics.macro_factors.history import MacroHistoryStore


def test_macro_history_store_appends_and_returns_previous(tmp_path):
    store = MacroHistoryStore(tmp_path / "macro_history")

    first = store.append_snapshot(
        {
            "snapshot_timestamp": "2026-03-20T10:00:00",
            "macro_score": 0.2,
            "macro_signal": 0,
            "confidence": 0.6,
            "factors": [{"name": "baseload_mismatch", "value": 0.2, "z_score": 0.6, "signal": 1, "confidence": 0.7, "metadata": {"evidence_summary": {"source_count": 2}}}],
        }
    )
    second = store.append_snapshot(
        {
            "snapshot_timestamp": "2026-03-20T11:00:00",
            "macro_score": 0.34,
            "macro_signal": 1,
            "confidence": 0.66,
            "factors": [{"name": "baseload_mismatch", "value": 0.34, "z_score": 1.1, "signal": 1, "confidence": 0.72, "metadata": {"evidence_summary": {"source_count": 3}}}],
        }
    )

    assert first["snapshot_timestamp"] == "2026-03-20T10:00:00"
    assert second["snapshot_timestamp"] == "2026-03-20T11:00:00"
    assert len(store.list_snapshots(limit=10)) == 2

    previous = store.get_previous_snapshot("2026-03-20T11:00:00")
    assert previous is not None
    assert previous["snapshot_timestamp"] == "2026-03-20T10:00:00"
    assert previous["factors"][0]["metadata"]["evidence_summary"]["source_count"] == 2
