from datetime import datetime

from src.data.alternative.alt_data_manager import AltDataManager
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


def test_alt_data_manager_refresh_and_snapshot():
    manager = AltDataManager(providers={"dummy_policy": DummyAltProvider()})

    signals = manager.refresh_all(force=True)
    assert "dummy_policy" in signals
    assert signals["dummy_policy"]["signal"] == 1

    snapshot = manager.get_dashboard_snapshot()
    assert snapshot["providers"]["dummy_policy"]["history_count"] == 1
    assert snapshot["recent_records"][0]["category"] == "policy"
