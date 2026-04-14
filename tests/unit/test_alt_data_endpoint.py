from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.v1.endpoints import alt_data, macro
from src.analytics.macro_factors.history import MacroHistoryStore
from src.data.alternative.alt_data_manager import AltDataManager
from src.data.alternative.base_alt_provider import AltDataCategory, AltDataRecord, BaseAltDataProvider
from src.data.alternative.governance import AltDataSnapshotStore
from src.data.alternative.people import PeopleLayerProvider
from src.data.alternative.policy_radar import PolicyExecutionProvider
from tests.unit.test_alt_data_pipeline import (
    DummyAltProvider,
    DummyPolicyRadarProvider,
    FailingAltProvider,
)


def _build_client(monkeypatch, manager, scheduler_status=None, history_store=None):
    app = FastAPI()
    app.include_router(alt_data.router, prefix="/alt-data")
    app.include_router(macro.router, prefix="/macro")

    class DummyScheduler:
        def get_status(self):
            return scheduler_status or {"running": False, "jobs": []}

    monkeypatch.setattr(alt_data, "_get_manager", lambda: manager)
    monkeypatch.setattr(alt_data, "_get_scheduler", lambda: DummyScheduler())
    monkeypatch.setattr(macro, "get_alt_data_manager", lambda: manager)
    if history_store is not None:
        monkeypatch.setattr(macro, "_history_store", history_store)
    return TestClient(app)


class ConflictingPolicyProvider(BaseAltDataProvider):
    name = "conflicting_policy"
    category = AltDataCategory.POLICY

    def fetch(self, **kwargs):
        return [{"title": "NVIDIA AI policy push"}, {"title": "NVIDIA AI policy rollback"}]

    def parse(self, raw_data):
        return raw_data

    def normalize(self, parsed_data):
        return [
            AltDataRecord(
                timestamp=datetime(2026, 3, 14, 0, 0, 0),
                source="policy_radar:ndrc",
                category=self.category,
                raw_value={
                    "title": "NVIDIA AI policy expansion",
                    "policy_shift": 0.61,
                    "will_intensity": 0.58,
                },
                normalized_score=0.52,
                confidence=0.8,
                tags=["nvidia", "ai_compute"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 15, 0, 0, 0),
                source="policy_radar:ndrc",
                category=self.category,
                raw_value={
                    "title": "NVIDIA AI subsidy extension",
                    "policy_shift": 0.55,
                    "will_intensity": 0.57,
                },
                normalized_score=0.47,
                confidence=0.78,
                tags=["NVDA", "ai_compute"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 17, 0, 0, 0),
                source="policy_radar:ndrc",
                category=self.category,
                raw_value={
                    "title": "NVIDIA AI policy push",
                    "policy_shift": 0.82,
                    "will_intensity": 0.71,
                },
                normalized_score=0.72,
                confidence=0.86,
                tags=["nvidia", "ai_compute"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 18, 0, 0, 0),
                source="policy_radar:nea",
                category=self.category,
                raw_value={
                    "title": "NVIDIA AI policy rollback",
                    "policy_shift": -0.76,
                    "will_intensity": 0.68,
                },
                normalized_score=-0.69,
                confidence=0.83,
                tags=["NVDA", "ai_compute"],
            ),
        ]


class ThinCoveragePolicyProvider(BaseAltDataProvider):
    name = "thin_policy"
    category = AltDataCategory.POLICY

    def fetch(self, **kwargs):
        return [{"title": "Grid build policy boost"}]

    def parse(self, raw_data):
        return raw_data

    def normalize(self, parsed_data):
        return [
            AltDataRecord(
                timestamp=datetime(2026, 3, 19, 0, 0, 0),
                source="policy_radar:ndrc",
                category=self.category,
                raw_value={
                    "title": "Grid build policy boost",
                    "policy_shift": 0.88,
                    "will_intensity": 0.82,
                },
                normalized_score=0.81,
                confidence=0.91,
                tags=["grid"],
            ),
        ]


class VolatilePolicyProvider(BaseAltDataProvider):
    name = "volatile_policy"
    category = AltDataCategory.POLICY

    def fetch(self, **kwargs):
        return [{"title": "Policy swings"}]

    def parse(self, raw_data):
        return raw_data

    def normalize(self, parsed_data):
        return [
            AltDataRecord(
                timestamp=datetime(2026, 3, 14, 0, 0, 0),
                source="policy_radar:ndrc",
                category=self.category,
                raw_value={"title": "Policy phase 1", "policy_shift": 0.78, "will_intensity": 0.7},
                normalized_score=0.78,
                confidence=0.88,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 15, 0, 0, 0),
                source="policy_radar:ndrc",
                category=self.category,
                raw_value={"title": "Policy phase 2", "policy_shift": 0.05, "will_intensity": 0.42},
                normalized_score=0.05,
                confidence=0.84,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 16, 0, 0, 0),
                source="policy_radar:ndrc",
                category=self.category,
                raw_value={"title": "Policy phase 3", "policy_shift": 0.81, "will_intensity": 0.73},
                normalized_score=0.81,
                confidence=0.86,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 17, 0, 0, 0),
                source="policy_radar:ndrc",
                category=self.category,
                raw_value={"title": "Policy phase 4", "policy_shift": 0.08, "will_intensity": 0.4},
                normalized_score=0.08,
                confidence=0.82,
                tags=["grid"],
            ),
        ]


class StalePolicyProvider(BaseAltDataProvider):
    name = "stale_policy"
    category = AltDataCategory.POLICY

    def fetch(self, **kwargs):
        return [{"title": "Old policy"}]

    def parse(self, raw_data):
        return raw_data

    def normalize(self, parsed_data):
        return [
            AltDataRecord(
                timestamp=datetime(2026, 3, 1, 0, 0, 0),
                source="policy_radar:ndrc",
                category=self.category,
                raw_value={"title": "Old policy anchor", "policy_shift": 0.72, "will_intensity": 0.76},
                normalized_score=0.74,
                confidence=0.9,
                tags=["grid"],
            ),
        ]


class SourceDriftPolicyProvider(BaseAltDataProvider):
    name = "source_drift_policy"
    category = AltDataCategory.POLICY

    def fetch(self, **kwargs):
        return [{"title": "Source drift"}]

    def parse(self, raw_data):
        return raw_data

    def normalize(self, parsed_data):
        return [
            AltDataRecord(
                timestamp=datetime(2026, 3, 12, 0, 0, 0),
                source="policy_radar:ndrc",
                category=self.category,
                raw_value={"title": "Official policy base", "policy_shift": 0.61, "will_intensity": 0.67},
                normalized_score=0.62,
                confidence=0.86,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 13, 0, 0, 0),
                source="policy_radar:nea",
                category=self.category,
                raw_value={"title": "Official policy extension", "policy_shift": 0.58, "will_intensity": 0.63},
                normalized_score=0.59,
                confidence=0.83,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 18, 0, 0, 0),
                source="macro_blog:derived",
                category=self.category,
                raw_value={"title": "Derived interpretation 1", "policy_shift": 0.55, "will_intensity": 0.61},
                normalized_score=0.56,
                confidence=0.78,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 19, 0, 0, 0),
                source="macro_blog:derived",
                category=self.category,
                raw_value={"title": "Derived interpretation 2", "policy_shift": 0.52, "will_intensity": 0.6},
                normalized_score=0.54,
                confidence=0.76,
                tags=["grid"],
            ),
        ]


class BrokenFlowPolicyProvider(BaseAltDataProvider):
    name = "broken_flow_policy"
    category = AltDataCategory.POLICY

    def fetch(self, **kwargs):
        return [{"title": "Broken flow"}]

    def parse(self, raw_data):
        return raw_data

    def normalize(self, parsed_data):
        return [
            AltDataRecord(
                timestamp=datetime(2026, 3, 1, 0, 0, 0),
                source="policy_radar:ndrc",
                category=self.category,
                raw_value={"title": "Policy cadence 1", "policy_shift": 0.49, "will_intensity": 0.55},
                normalized_score=0.5,
                confidence=0.82,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 2, 0, 0, 0),
                source="policy_radar:ndrc",
                category=self.category,
                raw_value={"title": "Policy cadence 2", "policy_shift": 0.51, "will_intensity": 0.57},
                normalized_score=0.52,
                confidence=0.84,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 10, 0, 0, 0),
                source="policy_radar:ndrc",
                category=self.category,
                raw_value={"title": "Policy cadence gap", "policy_shift": 0.5, "will_intensity": 0.56},
                normalized_score=0.51,
                confidence=0.83,
                tags=["grid"],
            ),
        ]


class PolicyHealthProvider(BaseAltDataProvider):
    name = "policy_radar"
    category = AltDataCategory.POLICY

    def fetch(self, **kwargs):
        return [{"title": "Policy health"}]

    def parse(self, raw_data):
        return raw_data

    def normalize(self, parsed_data):
        return [
            AltDataRecord(
                timestamp=datetime(2026, 3, 24, 0, 0, 0),
                source="policy_radar:ndrc",
                category=self.category,
                raw_value={"title": "Grid build directive", "policy_shift": 0.71, "will_intensity": 0.66},
                normalized_score=0.68,
                confidence=0.84,
                tags=["grid"],
            )
        ]

    def to_signal(self, records):
        signal = super().to_signal(records)
        signal["source_health"] = {
            "ndrc": {
                "record_count": 1,
                "full_text_ratio": 0.2,
                "avg_text_length": 120.0,
                "ingest_modes": {"html": 1},
                "detail_quality": {"thin": 1},
                "level": "fragile",
            }
        }
        return signal


class ConfirmedCrossSourcePolicyProvider(BaseAltDataProvider):
    name = "confirmed_cross_source_policy"
    category = AltDataCategory.POLICY

    def fetch(self, **kwargs):
        return [{"title": "Cross confirmation"}]

    def parse(self, raw_data):
        return raw_data

    def normalize(self, parsed_data):
        return [
            AltDataRecord(
                timestamp=datetime(2026, 3, 18, 0, 0, 0),
                source="policy_radar:ndrc",
                category=AltDataCategory.POLICY,
                raw_value={"title": "Official policy support", "policy_shift": 0.71, "will_intensity": 0.73},
                normalized_score=0.72,
                confidence=0.88,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 18, 6, 0, 0),
                source="supply_chain:bidding",
                category=AltDataCategory.BIDDING,
                raw_value={"title": "Grid capex tender acceleration", "industry": "grid", "amount": 160000000},
                normalized_score=0.62,
                confidence=0.81,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 18, 12, 0, 0),
                source="supply_chain:env_assessment",
                category=AltDataCategory.ENV_ASSESSMENT,
                raw_value={"title": "Grid substation filing approved", "industry": "grid", "amount": 1},
                normalized_score=0.58,
                confidence=0.79,
                tags=["grid"],
            ),
        ]


class DivergentConsensusPolicyProvider(BaseAltDataProvider):
    name = "divergent_consensus_policy"
    category = AltDataCategory.POLICY

    def fetch(self, **kwargs):
        return [{"title": "Divergent consensus"}]

    def parse(self, raw_data):
        return raw_data

    def normalize(self, parsed_data):
        return [
            AltDataRecord(
                timestamp=datetime(2026, 3, 20, 0, 0, 0),
                source="policy_radar:ndrc",
                category=AltDataCategory.POLICY,
                raw_value={"title": "Official very strong support", "policy_shift": 0.86, "will_intensity": 0.82},
                normalized_score=0.84,
                confidence=0.88,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 20, 6, 0, 0),
                source="supply_chain:bidding",
                category=AltDataCategory.BIDDING,
                raw_value={"title": "Tender support but modest", "industry": "grid", "amount": 20000000},
                normalized_score=0.26,
                confidence=0.76,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 20, 12, 0, 0),
                source="supply_chain:env_assessment",
                category=AltDataCategory.ENV_ASSESSMENT,
                raw_value={"title": "Filing support but weak", "industry": "grid", "amount": 1},
                normalized_score=0.19,
                confidence=0.74,
                tags=["grid"],
            ),
        ]


class ReversalPolicyProvider(BaseAltDataProvider):
    name = "reversal_policy"
    category = AltDataCategory.POLICY

    def fetch(self, **kwargs):
        return [{"title": "Reversal"}]

    def parse(self, raw_data):
        return raw_data

    def normalize(self, parsed_data):
        return [
            AltDataRecord(
                timestamp=datetime(2026, 3, 16, 0, 0, 0),
                source="policy_radar:ndrc",
                category=AltDataCategory.POLICY,
                raw_value={"title": "Earlier positive policy", "policy_shift": 0.74, "will_intensity": 0.69},
                normalized_score=0.76,
                confidence=0.86,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 17, 0, 0, 0),
                source="policy_radar:nea",
                category=AltDataCategory.POLICY,
                raw_value={"title": "Positive policy extension", "policy_shift": 0.63, "will_intensity": 0.61},
                normalized_score=0.62,
                confidence=0.82,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 20, 0, 0, 0),
                source="policy_radar:ndrc",
                category=AltDataCategory.POLICY,
                raw_value={"title": "Policy reversal signal", "policy_shift": -0.58, "will_intensity": 0.66},
                normalized_score=-0.57,
                confidence=0.83,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 21, 0, 0, 0),
                source="policy_radar:nea",
                category=AltDataCategory.POLICY,
                raw_value={"title": "Negative policy follow-through", "policy_shift": -0.66, "will_intensity": 0.7},
                normalized_score=-0.64,
                confidence=0.84,
                tags=["grid"],
            ),
        ]


class ReversalPrecursorPolicyProvider(BaseAltDataProvider):
    name = "reversal_precursor_policy"
    category = AltDataCategory.POLICY

    def fetch(self, **kwargs):
        return [{"title": "Reversal precursor"}]

    def parse(self, raw_data):
        return raw_data

    def normalize(self, parsed_data):
        return [
            AltDataRecord(
                timestamp=datetime(2026, 3, 16, 0, 0, 0),
                source="policy_radar:ndrc",
                category=AltDataCategory.POLICY,
                raw_value={"title": "Earlier strong support", "policy_shift": 0.78, "will_intensity": 0.73},
                normalized_score=0.8,
                confidence=0.88,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 17, 0, 0, 0),
                source="policy_radar:nea",
                category=AltDataCategory.POLICY,
                raw_value={"title": "Support easing", "policy_shift": 0.54, "will_intensity": 0.56},
                normalized_score=0.5,
                confidence=0.81,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 20, 0, 0, 0),
                source="policy_radar:ndrc",
                category=AltDataCategory.POLICY,
                raw_value={"title": "Support near neutral", "policy_shift": 0.24, "will_intensity": 0.41},
                normalized_score=0.23,
                confidence=0.76,
                tags=["grid"],
            ),
            AltDataRecord(
                timestamp=datetime(2026, 3, 21, 0, 0, 0),
                source="policy_radar:nea",
                category=AltDataCategory.POLICY,
                raw_value={"title": "Support almost flat", "policy_shift": 0.21, "will_intensity": 0.38},
                normalized_score=0.21,
                confidence=0.75,
                tags=["grid"],
            ),
        ]


class ResonancePolicyProvider(BaseAltDataProvider):
    name = "resonance_policy"
    category = AltDataCategory.POLICY

    def __init__(self):
        super().__init__()
        self.calls = 0

    def fetch(self, **kwargs):
        self.calls += 1
        return [{"title": "Resonance policy"}]

    def parse(self, raw_data):
        return raw_data

    def normalize(self, parsed_data):
        if self.calls <= 1:
            score = 0.28
            confidence = 0.72
            title = "Initial policy support"
        else:
            score = 0.78
            confidence = 0.88
            title = "Accelerating policy support"
        return [
            AltDataRecord(
                timestamp=datetime(2026, 3, 22, self.calls, 0, 0),
                source="policy_radar:ndrc",
                category=AltDataCategory.POLICY,
                raw_value={"title": title, "policy_shift": score, "will_intensity": score},
                normalized_score=score,
                confidence=confidence,
                tags=["grid"],
            ),
        ]


class ResonanceBiddingProvider(BaseAltDataProvider):
    name = "resonance_bidding"
    category = AltDataCategory.BIDDING

    def __init__(self):
        super().__init__()
        self.calls = 0

    def fetch(self, **kwargs):
        self.calls += 1
        return [{"title": "Resonance bidding"}]

    def parse(self, raw_data):
        return raw_data

    def normalize(self, parsed_data):
        if self.calls <= 1:
            score = 0.24
            amount = 50000000
        else:
            score = 0.71
            amount = 220000000
        return [
            AltDataRecord(
                timestamp=datetime(2026, 3, 22, self.calls, 30, 0),
                source="supply_chain:bidding",
                category=AltDataCategory.BIDDING,
                raw_value={"title": "Grid capex bidding", "industry": "grid", "amount": amount},
                normalized_score=score,
                confidence=0.79,
                tags=["grid"],
            ),
        ]


def test_alt_data_status_and_refresh_endpoints(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"dummy_policy": DummyAltProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    client = _build_client(monkeypatch, manager, scheduler_status={"running": True, "jobs": [{"id": "alt-data-dummy"}]})

    refresh_response = client.post("/alt-data/refresh?provider=all")
    assert refresh_response.status_code == 200
    assert refresh_response.json()["status"] == "success"

    status_response = client.get("/alt-data/status")
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["scheduler"]["running"] is True
    assert "dummy_policy" in payload["providers"]

    history_response = client.get("/alt-data/history?limit=5")
    assert history_response.status_code == 200
    assert history_response.json()["count"] == 1
    assert "category_trends" in history_response.json()
    assert "category_series" in history_response.json()
    assert "overall_trend" in history_response.json()
    assert "evidence_summary" in history_response.json()
    assert "excerpt" in history_response.json()["evidence_summary"]["latest_record"]
    assert "facts" in history_response.json()["evidence_summary"]["latest_record"]
    assert "canonical_entity" in history_response.json()["evidence_summary"]["latest_record"]
    assert "top_entities" in history_response.json()["evidence_summary"]
    assert "freshness_label" in history_response.json()["evidence_summary"]["latest_record"]
    assert "trust_score" in history_response.json()["evidence_summary"]["latest_record"]
    assert "weighted_evidence_score" in history_response.json()["evidence_summary"]


def test_alt_data_refresh_rejects_unknown_provider(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"dummy_policy": DummyAltProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    client = _build_client(monkeypatch, manager)

    response = client.post("/alt-data/refresh?provider=missing")
    assert response.status_code == 400


def test_alt_data_snapshot_and_macro_survive_provider_failure(monkeypatch, tmp_path):
    store = AltDataSnapshotStore(tmp_path / "alt_data")
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    healthy_manager = AltDataManager(
        providers={"dummy_policy": DummyAltProvider()},
        snapshot_store=store,
    )
    healthy_manager.refresh_all(force=True)

    failing_manager = AltDataManager(
        providers={"dummy_policy": FailingAltProvider()},
        snapshot_store=store,
    )
    client = _build_client(monkeypatch, failing_manager, history_store=history_store)

    snapshot_response = client.get("/alt-data/snapshot?refresh=true")
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["refresh_status"]["dummy_policy"]["status"] == "degraded"
    assert "evidence_summary" in snapshot_response.json()

    macro_response = client.get("/macro/overview?refresh=true")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    assert "data_freshness" in macro_payload
    assert "provider_status" in macro_payload
    assert "trend" in macro_payload
    assert "evidence_summary" in macro_payload
    assert "evidence_summary" in macro_payload["factors"][0]["metadata"]
    assert "excerpt" in macro_payload["factors"][0]["metadata"]["evidence_summary"]["recent_evidence"][0]
    assert "facts" in macro_payload["factors"][0]["metadata"]["evidence_summary"]["recent_evidence"][0]
    assert "top_entities" in macro_payload["factors"][0]["metadata"]["evidence_summary"]
    assert "source_tier" in macro_payload["factors"][0]["metadata"]["evidence_summary"]["recent_evidence"][0]
    assert "freshness_label" in macro_payload["factors"][0]["metadata"]["evidence_summary"]["recent_evidence"][0]
    assert "weighted_evidence_score" in macro_payload["factors"][0]["metadata"]["evidence_summary"]


def test_macro_history_endpoint_returns_persisted_records(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"dummy_policy": DummyAltProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    first = client.get("/macro/overview?refresh=true")
    assert first.status_code == 200
    second = client.get("/macro/overview?refresh=false")
    assert second.status_code == 200

    payload = second.json()
    assert "trend" in payload
    assert "macro_score_delta" in payload["trend"]

    history_response = client.get("/macro/history?limit=5")
    assert history_response.status_code == 200
    history_payload = history_response.json()
    assert history_payload["count"] >= 1
    assert history_payload["records"][0]["snapshot_timestamp"]


def test_alt_data_and_macro_expose_conflict_summary(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"conflicting_policy": ConflictingPolicyProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    snapshot_response = client.get("/alt-data/snapshot?refresh=true")
    assert snapshot_response.status_code == 200
    snapshot_payload = snapshot_response.json()
    assert snapshot_payload["evidence_summary"]["conflict_count"] >= 1
    assert snapshot_payload["evidence_summary"]["conflict_level"] in {"medium", "high"}
    assert snapshot_payload["evidence_summary"]["conflicts"][0]["target"] == "NVDA"
    assert snapshot_payload["evidence_summary"]["conflicts"][0]["source_pattern"] == "official_split"
    assert snapshot_payload["evidence_summary"]["conflict_trend"] == "rising"

    macro_response = client.get("/macro/overview?refresh=true")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    factor_evidence = macro_payload["factors"][0]["metadata"]["evidence_summary"]
    assert factor_evidence["conflict_count"] >= 1
    assert factor_evidence["conflict_level"] in {"medium", "high"}
    assert factor_evidence["conflicts"][0]["target"] == "NVDA"
    assert factor_evidence["conflicts"][0]["source_pattern"] == "official_split"
    assert factor_evidence["conflict_trend"] == "rising"
    assert factor_evidence["coverage_summary"]["coverage_label"] in {"thin", "partial", "strong"}
    assert factor_evidence["coverage_summary"]["overall_coverage_ratio"] > 0
    assert macro_payload["factors"][0]["metadata"]["confidence_penalty"] > 0
    assert macro_payload["factors"][0]["metadata"]["confidence_support_bonus"] > 0
    assert macro_payload["factors"][0]["metadata"]["effective_confidence"] < macro_payload["factors"][0]["metadata"]["raw_confidence"]
    assert "blind_spot_warning" in macro_payload["factors"][0]["metadata"]
    assert "blind_spot_level" in macro_payload["factors"][0]["metadata"]
    assert macro_payload["confidence_adjustment"]["penalized_factor_count"] >= 1
    assert macro_payload["confidence_adjustment"]["boosted_factor_count"] >= 1
    assert "blind_spot_factor_count" in macro_payload["confidence_adjustment"]


def test_macro_exposes_blind_spot_warning_for_thin_high_confidence(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"thin_policy": ThinCoveragePolicyProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    macro_response = client.get("/macro/overview?refresh=true")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    first_factor = macro_payload["factors"][0]
    concentration_summary = first_factor["metadata"]["evidence_summary"]["concentration_summary"]
    assert first_factor["metadata"]["blind_spot_warning"] is True
    assert first_factor["metadata"]["blind_spot_level"] in {"medium", "high"}
    assert first_factor["metadata"]["blind_spot_missing_categories"]
    assert concentration_summary["label"] == "high"
    assert concentration_summary["top_source_share"] == 1.0
    assert first_factor["metadata"]["concentration_warning"] is True
    assert first_factor["metadata"]["concentration_level"] == "high"
    assert macro_payload["confidence_adjustment"]["blind_spot_factor_count"] >= 1
    assert macro_payload["confidence_adjustment"]["concentrated_factor_count"] >= 1


def test_macro_exposes_stability_warning_for_volatile_factor(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"volatile_policy": VolatilePolicyProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    macro_response = client.get("/macro/overview?refresh=true")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    first_factor = macro_payload["factors"][0]
    stability_summary = first_factor["metadata"]["evidence_summary"]["stability_summary"]
    assert stability_summary["label"] in {"choppy", "unstable"}
    assert first_factor["metadata"]["stability_warning"] is True
    assert first_factor["metadata"]["stability_level"] in {"medium", "high"}
    assert macro_payload["confidence_adjustment"]["unstable_factor_count"] >= 1


def test_macro_exposes_lag_warning_for_stale_factor(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"stale_policy": StalePolicyProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    macro_response = client.get("/macro/overview?refresh=true")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    first_factor = macro_payload["factors"][0]
    lag_summary = first_factor["metadata"]["evidence_summary"]["lag_summary"]
    assert lag_summary["level"] in {"medium", "high"}
    assert first_factor["metadata"]["lag_warning"] is True
    assert first_factor["metadata"]["lag_level"] in {"medium", "high"}
    assert macro_payload["confidence_adjustment"]["lagging_factor_count"] >= 1


def test_macro_exposes_source_drift_warning(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"source_drift_policy": SourceDriftPolicyProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    macro_response = client.get("/macro/overview?refresh=true")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    first_factor = macro_payload["factors"][0]
    source_drift_summary = first_factor["metadata"]["evidence_summary"]["source_drift_summary"]
    dominance_summary = first_factor["metadata"]["evidence_summary"]["source_dominance_summary"]
    assert source_drift_summary["label"] == "degrading"
    assert source_drift_summary["recent_official_share"] < source_drift_summary["previous_official_share"]
    assert dominance_summary["label"] in {"rotating", "derived_dominant"}
    assert dominance_summary["recent_dominant_tier"] in {"derived", "official"}
    assert first_factor["metadata"]["source_drift_warning"] is True
    assert first_factor["metadata"]["source_drift_level"] == "high"
    assert first_factor["metadata"]["source_dominance_warning"] is True
    assert first_factor["metadata"]["source_dominance_level"] in {"medium", "high"}
    assert macro_payload["confidence_adjustment"]["drifting_factor_count"] >= 1
    assert macro_payload["confidence_adjustment"]["dominance_shift_factor_count"] >= 1


def test_macro_exposes_policy_source_health_summary(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"policy_radar": PolicyHealthProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    macro_response = client.get("/macro/overview?refresh=true")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    first_factor = macro_payload["factors"][0]
    health_summary = first_factor["metadata"]["evidence_summary"]["policy_source_health_summary"]
    assert health_summary["label"] == "fragile"
    assert "ndrc" in health_summary["fragile_sources"]
    assert first_factor["metadata"]["policy_source_warning"] is True
    assert first_factor["metadata"]["policy_source_level"] == "fragile"
    assert macro_payload["confidence_adjustment"]["policy_source_fragile_factor_count"] >= 1
    assert macro_payload["input_reliability_summary"]["label"] in {"watch", "fragile"}
    assert "政策源脆弱" in " ".join(macro_payload["input_reliability_summary"]["dominant_issue_labels"])
    assert macro_payload["input_reliability_summary"]["issue_factor_hits"] >= 1
    assert macro_payload["people_layer_summary"]["label"] in {"watch", "fragile", "stable"}
    assert macro_payload["people_layer_summary"]["watchlist"]
    assert "avg_fragility_score" in macro_payload["people_layer_summary"]


def test_macro_exposes_source_gap_warning(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"broken_flow_policy": BrokenFlowPolicyProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    macro_response = client.get("/macro/overview?refresh=true")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    first_factor = macro_payload["factors"][0]
    source_gap_summary = first_factor["metadata"]["evidence_summary"]["source_gap_summary"]
    assert source_gap_summary["label"] in {"stretching", "broken"}
    assert source_gap_summary["latest_gap_hours"] > source_gap_summary["baseline_gap_hours"]
    assert first_factor["metadata"]["source_gap_warning"] is True
    assert first_factor["metadata"]["source_gap_level"] in {"medium", "high"}
    assert macro_payload["confidence_adjustment"]["broken_flow_factor_count"] >= 1


def test_macro_exposes_cross_confirmation_summary(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"confirmed_cross_source_policy": ConfirmedCrossSourcePolicyProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    macro_response = client.get("/macro/overview?refresh=true")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    first_factor = macro_payload["factors"][0]
    confirmation = first_factor["metadata"]["evidence_summary"]["cross_confirmation_summary"]
    consistency = first_factor["metadata"]["evidence_summary"]["consistency_summary"]
    assert confirmation["label"] == "strong"
    assert confirmation["dominant_direction"] == "positive"
    assert len(confirmation["confirming_source_tiers"]) >= 3
    assert "policy" in confirmation["confirming_categories"]
    dominance_summary = first_factor["metadata"]["evidence_summary"]["source_dominance_summary"]
    assert consistency["label"] in {"strong", "moderate"}
    assert dominance_summary["recent_dominant_tier"]
    assert first_factor["metadata"]["confidence_support_bonus"] > 0
    assert macro_payload["confidence_adjustment"]["confirmed_factor_count"] >= 1


def test_macro_exposes_consistency_warning_for_divergent_strength(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"divergent_consensus_policy": DivergentConsensusPolicyProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    macro_response = client.get("/macro/overview?refresh=true")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    first_factor = macro_payload["factors"][0]
    consistency = first_factor["metadata"]["evidence_summary"]["consistency_summary"]
    confirmation = first_factor["metadata"]["evidence_summary"]["cross_confirmation_summary"]
    assert confirmation["label"] in {"strong", "moderate"}
    assert consistency["label"] == "divergent"
    assert consistency["dispersion"] > 0.35
    assert first_factor["metadata"]["consistency_warning"] is True
    assert first_factor["metadata"]["consistency_level"] == "high"
    assert macro_payload["confidence_adjustment"]["inconsistent_factor_count"] >= 1


def test_macro_exposes_reversal_warning(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"reversal_policy": ReversalPolicyProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    macro_response = client.get("/macro/overview?refresh=true")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    first_factor = macro_payload["factors"][0]
    reversal = first_factor["metadata"]["evidence_summary"]["reversal_summary"]
    assert reversal["label"] == "reversed"
    assert reversal["previous_direction"] == "positive"
    assert reversal["recent_direction"] == "negative"
    assert first_factor["metadata"]["reversal_warning"] is True
    assert first_factor["metadata"]["reversal_level"] == "high"
    assert macro_payload["confidence_adjustment"]["reversing_factor_count"] >= 1


def test_macro_exposes_department_chaos_summary(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"reversal_policy": ReversalPolicyProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    macro_response = client.get("/macro/overview?refresh=true")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    summary = macro_payload["department_chaos_summary"]
    assert summary["department_count"] >= 2
    assert summary["chaotic_department_count"] >= 1
    top_department = summary["top_departments"][0]
    assert top_department["department"] in {"ndrc", "nea"}
    assert top_department["label"] == "chaotic"
    assert top_department["policy_reversal_count"] >= 1
    assert top_department["chaos_score"] >= 0.6


def test_alt_snapshot_and_macro_include_people_policy_and_source_mode_summaries(monkeypatch, tmp_path):
    policy_provider = DummyPolicyRadarProvider()
    manager = AltDataManager(
        providers={
            "policy_radar": policy_provider,
            "people_layer": PeopleLayerProvider(),
            "policy_execution": PolicyExecutionProvider(policy_provider=policy_provider),
        },
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    snapshot_response = client.get("/alt-data/snapshot?refresh=true")
    assert snapshot_response.status_code == 200
    snapshot_payload = snapshot_response.json()
    assert "people_layer" in snapshot_payload["signals"]
    assert "policy_execution" in snapshot_payload["signals"]
    assert snapshot_payload["signals"]["people_layer"]["watchlist"]
    assert snapshot_payload["signals"]["policy_execution"]["department_board"]
    assert snapshot_payload["source_mode_summary"]["counts"]
    assert snapshot_payload["provider_health"]["people_layer"]["source_mode_summary"]["counts"]
    assert snapshot_payload["provider_health"]["policy_execution"]["source_mode_summary"]["counts"]

    macro_response = client.get("/macro/overview?refresh=false")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    factor_names = {item["name"] for item in macro_payload["factors"]}
    assert "people_fragility" in factor_names
    assert "policy_execution_disorder" in factor_names
    assert macro_payload["people_layer_summary"]["watchlist"]
    assert macro_payload["department_chaos_summary"]["top_departments"]
    assert macro_payload["source_mode_summary"]["counts"]


def test_macro_exposes_reversal_precursor_warning(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={"reversal_precursor_policy": ReversalPrecursorPolicyProvider()},
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    macro_response = client.get("/macro/overview?refresh=true")
    assert macro_response.status_code == 200
    macro_payload = macro_response.json()
    first_factor = macro_payload["factors"][0]
    precursor = first_factor["metadata"]["evidence_summary"]["reversal_precursor_summary"]
    assert precursor["label"] in {"medium", "high"}
    assert precursor["distance_to_zero"] <= 0.3
    assert first_factor["metadata"]["reversal_precursor_warning"] is True
    assert first_factor["metadata"]["reversal_precursor_level"] in {"medium", "high"}
    assert macro_payload["confidence_adjustment"]["precursor_factor_count"] >= 1


def test_macro_exposes_resonance_summary(monkeypatch, tmp_path):
    manager = AltDataManager(
        providers={
            "resonance_policy": ResonancePolicyProvider(),
            "resonance_bidding": ResonanceBiddingProvider(),
        },
        snapshot_store=AltDataSnapshotStore(tmp_path / "alt_data"),
    )
    history_store = MacroHistoryStore(tmp_path / "macro_history")
    client = _build_client(monkeypatch, manager, history_store=history_store)

    first_response = client.get("/macro/overview?refresh=true")
    assert first_response.status_code == 200
    second_response = client.get("/macro/overview?refresh=true")
    assert second_response.status_code == 200

    payload = second_response.json()
    resonance = payload["resonance_summary"]
    assert resonance["label"] in {"bullish_cluster", "mixed"}
    assert "positive_cluster" in resonance
    assert len(resonance["positive_cluster"]) >= 1
