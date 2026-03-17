from datetime import datetime

from src.data.alternative.alt_data_manager import AltDataManager
from src.data.alternative.governance import AltDataSnapshotStore
from src.data.alternative.base_alt_provider import (
    AltDataCategory,
    AltDataRecord,
    BaseAltDataProvider,
)


class DummyAltProvider(BaseAltDataProvider):
    name = "dummy_policy"
    category = AltDataCategory.POLICY

    def fetch(self, **kwargs):
        return [{"title": "test"}]

    def parse(self, raw_data):
        return raw_data

    def normalize(self, parsed_data):
        return [
            AltDataRecord(
                timestamp=datetime(2026, 3, 17, 0, 0, 0),
                source="dummy",
                category=self.category,
                raw_value=parsed_data[0],
                normalized_score=0.4,
                confidence=0.8,
            )
        ]


class FailingAltProvider(DummyAltProvider):
    def fetch(self, **kwargs):
        raise RuntimeError("boom")


def test_alt_data_manager_refresh_and_snapshot(tmp_path):
    manager = AltDataManager(
        providers={"dummy_policy": DummyAltProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )

    report = manager.refresh_all(force=True)
    assert "dummy_policy" in report["signals"]
    assert report["signals"]["dummy_policy"]["signal"] == 1

    snapshot = manager.get_dashboard_snapshot()
    assert snapshot["providers"]["dummy_policy"]["history_count"] == 1
    assert snapshot["recent_records"][0]["category"] == "policy"
    assert snapshot["refresh_status"]["dummy_policy"]["status"] == "success"


def test_alt_data_manager_bootstraps_from_snapshot_store(tmp_path):
    store = AltDataSnapshotStore(tmp_path / "alt_data")
    manager = AltDataManager(
        providers={"dummy_policy": DummyAltProvider()},
        snapshot_store=store,
    )
    manager.refresh_all(force=True)

    reloaded = AltDataManager(
        providers={"dummy_policy": DummyAltProvider()},
        snapshot_store=store,
    )
    snapshot = reloaded.get_dashboard_snapshot()
    assert snapshot["recent_records"]
    assert snapshot["providers"]["dummy_policy"]["history_count"] == 1


def test_alt_data_manager_returns_stale_snapshot_when_provider_fails(tmp_path):
    store = AltDataSnapshotStore(tmp_path / "alt_data")
    healthy = AltDataManager(
        providers={"dummy_policy": DummyAltProvider()},
        snapshot_store=store,
    )
    healthy.refresh_all(force=True)

    failing = AltDataManager(
        providers={"dummy_policy": FailingAltProvider()},
        snapshot_store=store,
    )
    report = failing.refresh_all(force=True)
    snapshot = failing.get_dashboard_snapshot()

    assert report["refresh_status"]["dummy_policy"]["status"] == "degraded"
    assert snapshot["refresh_status"]["dummy_policy"]["status"] == "degraded"
    assert snapshot["recent_records"][0]["category"] == "policy"
