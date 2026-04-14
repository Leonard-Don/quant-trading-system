"""
另类数据统一管理器

串联三条另类数据主线：
- 政经语义雷达
- 产业链信号
- 全球宏观高频信号
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .base_alt_provider import AltDataCategory, AltDataRecord, BaseAltDataProvider
from .governance import (
    AltDataRefreshService,
    AltDataSnapshotEnvelope,
    AltDataSnapshotStore,
    ProviderRefreshStatus,
)
from .macro_hf import MacroHFSignalProvider
from .people import PeopleLayerProvider
from .policy_radar import PolicySignalProvider
from .policy_radar.policy_execution import PolicyExecutionProvider
from .supply_chain import SupplyChainSignalProvider
from .entity_resolution import aggregate_entities, resolve_entity

logger = logging.getLogger(__name__)


DEFAULT_PROVIDER_CONFIG: Dict[str, Dict[str, Any]] = {
    "policy_radar": {
        "sources": ["ndrc", "nea", "fed", "ecb", "boe"],
        "limit": 5,
        "days_back": 14,
        "detail_limit": 4,
    },
    "supply_chain": {
        "industries": ["ai_compute", "grid", "nuclear"],
        "days_back": 30,
    },
    "macro_hf": {
        "metals": ["copper", "aluminium"],
        "categories": ["semiconductors", "copper_ore", "ev_battery"],
    },
    "people_layer": {
        "symbols": [],
    },
    "policy_execution": {
        "sources": ["ndrc", "nea", "fed", "ecb", "boe"],
        "limit": 5,
        "days_back": 14,
        "detail_limit": 4,
    },
}

SOURCE_TIER_RULES = [
    ("policy_radar:ndrc", ("official", 1.0)),
    ("policy_radar:nea", ("official", 0.95)),
    ("policy_execution:ndrc", ("official", 0.98)),
    ("policy_execution:nea", ("official", 0.94)),
    ("people_layer:executive_governance", ("corporate_governance", 0.78)),
    ("people_layer:insider_flow", ("market_disclosure", 0.74)),
    ("people_layer:hiring_structure", ("corporate_signal", 0.72)),
    ("macro_hf", ("market", 0.88)),
    ("supply_chain:bidding", ("public_procurement", 0.84)),
    ("supply_chain:env_assessment", ("regulatory_filing", 0.86)),
    ("supply_chain:hiring", ("corporate_signal", 0.72)),
]


class AltDataManager:
    """统一调度和查询另类数据提供器。"""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        providers: Optional[Dict[str, BaseAltDataProvider]] = None,
        snapshot_store: Optional[AltDataSnapshotStore] = None,
    ):
        self.config = config or {}
        self.providers = providers or self._build_default_providers()
        snapshot_dir = self.config.get("snapshot_dir")
        self.snapshot_store = snapshot_store or AltDataSnapshotStore(
            base_dir=Path(snapshot_dir) if snapshot_dir else None
        )
        self.refresh_service = AltDataRefreshService(self, self.snapshot_store)
        self.latest_signals: Dict[str, Dict[str, Any]] = {}
        self.refresh_status: Dict[str, ProviderRefreshStatus] = {}
        self.last_refresh: Optional[datetime] = None
        self._bootstrap_from_snapshots()

    def _build_default_providers(self) -> Dict[str, BaseAltDataProvider]:
        provider_config = self.config.get("providers", {})
        policy_provider = PolicySignalProvider(
            provider_config.get("policy_radar", self.config)
        )
        return {
            "policy_radar": policy_provider,
            "supply_chain": SupplyChainSignalProvider(
                provider_config.get("supply_chain", self.config)
            ),
            "macro_hf": MacroHFSignalProvider(
                provider_config.get("macro_hf", self.config)
            ),
            "people_layer": PeopleLayerProvider(
                provider_config.get("people_layer", self.config)
            ),
            "policy_execution": PolicyExecutionProvider(
                provider_config.get("policy_execution", self.config),
                policy_provider=policy_provider,
            ),
        }

    def register_provider(self, name: str, provider: BaseAltDataProvider) -> None:
        self.providers[name] = provider

    def get_provider(self, name: str) -> BaseAltDataProvider:
        if name not in self.providers:
            raise KeyError(f"Unknown alternative data provider: {name}")
        return self.providers[name]

    def refresh_provider(
        self,
        name: str,
        force: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        run_kwargs = self._merge_provider_kwargs(name, kwargs)
        return self.refresh_service.refresh_provider(name, force=force, **run_kwargs)

    def refresh_all(
        self,
        force: bool = False,
        provider_params: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return self.refresh_service.refresh_all(
            force=force,
            provider_params=provider_params,
        ).to_dict()

    def get_alt_signals(
        self,
        category: Optional[str] = None,
        timeframe: str = "7d",
        refresh_if_empty: bool = False,
    ) -> Dict[str, Any]:
        if refresh_if_empty and not self.latest_signals:
            self.refresh_all()

        category_value = category.lower() if category else None
        signals = []
        for name, signal in self.latest_signals.items():
            provider = self.providers.get(name)
            provider_category = provider.category.value if provider else None
            if category_value and provider_category != category_value:
                continue
            signals.append(signal)

        records = self.get_records(category=category_value, timeframe=timeframe)
        return {
            "signals": signals,
            "records": [record.to_dict() for record in records],
            "timeframe": timeframe,
            "category": category,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "refresh_status": self.get_refresh_status_dict(category=category_value),
            "provider_health": self._build_provider_health(),
        }

    def get_records(
        self,
        category: Optional[str] = None,
        timeframe: str = "7d",
        limit: int = 200,
    ) -> List[AltDataRecord]:
        start = datetime.now() - self._parse_timeframe(timeframe)
        category_value = category.lower() if category else None
        records: List[AltDataRecord] = []
        for provider in self.providers.values():
            provider_records = provider.get_history(start=start, limit=limit)
            records.extend(provider_records)

        filtered = []
        for record in records:
            if category_value and record.category.value != category_value:
                continue
            filtered.append(record)

        filtered.sort(key=lambda record: record.timestamp, reverse=True)
        return filtered[:limit]

    def analyze_history(self, records: List[AltDataRecord]) -> Dict[str, Any]:
        if not records:
            return {
                "category_series": {},
                "category_trends": {},
                "overall_trend": {
                    "recent_avg_score": 0.0,
                    "previous_avg_score": 0.0,
                    "delta_score": 0.0,
                    "momentum": "stable",
                },
            }

        ordered = sorted(records, key=lambda record: record.timestamp)
        category_series: Dict[str, List[Dict[str, Any]]] = {}
        category_trends: Dict[str, Dict[str, Any]] = {}

        for category_name in sorted({record.category.value for record in ordered}):
            category_records = [record for record in ordered if record.category.value == category_name]
            category_series[category_name] = self._build_category_series(category_records)
            category_trends[category_name] = self._build_category_trend(category_records)

        overall_trend = self._build_category_trend(ordered)
        return {
            "category_series": category_series,
            "category_trends": category_trends,
            "overall_trend": {
                "recent_avg_score": overall_trend["recent_avg_score"],
                "previous_avg_score": overall_trend["previous_avg_score"],
                "delta_score": overall_trend["delta_score"],
                "momentum": overall_trend["momentum"],
            },
        }

    def build_evidence_summary(
        self,
        records: List[AltDataRecord],
        limit: int = 6,
    ) -> Dict[str, Any]:
        if not records:
            return {
                "record_count": 0,
                "source_count": 0,
                "sources": [],
                "categories": [],
                "latest_timestamp": "",
                "latest_record": None,
                "recent_evidence": [],
                "conflict_count": 0,
                "conflict_level": "none",
                "conflicts": [],
            }

        ordered = sorted(records, key=lambda record: record.timestamp, reverse=True)
        source_counts: Dict[str, int] = {}
        category_counts: Dict[str, int] = {}
        for record in ordered:
            source_counts[record.source] = source_counts.get(record.source, 0) + 1
            category_counts[record.category.value] = category_counts.get(record.category.value, 0) + 1
        evidence_rows = [self._record_to_evidence(record) for record in ordered]
        weighted_score = round(
            sum(
                float(item.get("trust_score", 0.0))
                * float(item.get("freshness_weight", 0.0))
                * float(item.get("confidence", 0.0))
                for item in evidence_rows[: max(limit * 3, 1)]
            ),
            4,
        )
        official_count = len([item for item in evidence_rows if item.get("source_tier") == "official"])
        conflict_summary = self._build_conflict_summary(evidence_rows[: max(limit * 4, 1)])
        conflict_trend = self._build_conflict_trend(evidence_rows[: max(limit * 6, 2)])

        return {
            "record_count": len(ordered),
            "source_count": len(source_counts),
            "sources": [
                {
                    "source": source,
                    "count": count,
                    "source_tier": self._infer_source_tier(source)["tier"],
                    "trust_score": self._infer_source_tier(source)["trust_score"],
                }
                for source, count in sorted(source_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "categories": [
                {"category": category, "count": count}
                for category, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "latest_timestamp": ordered[0].timestamp.isoformat(),
            "latest_record": evidence_rows[0],
            "recent_evidence": evidence_rows[:limit],
            "top_entities": aggregate_entities(
                evidence_rows[:limit * 3],
                limit=6,
            ),
            "official_source_count": official_count,
            "weighted_evidence_score": weighted_score,
            "freshness_label": evidence_rows[0].get("freshness_label", "stale"),
            "conflict_count": conflict_summary["conflict_count"],
            "conflict_level": conflict_summary["conflict_level"],
            "conflicts": conflict_summary["conflicts"],
            "conflict_trend": conflict_trend["trend"],
            "conflict_trend_reason": conflict_trend["reason"],
            "recent_conflict_count": conflict_trend["recent_conflict_count"],
            "previous_conflict_count": conflict_trend["previous_conflict_count"],
        }

    def get_dashboard_snapshot(self, refresh: bool = False) -> Dict[str, Any]:
        if refresh:
            self.refresh_all(force=True)

        if not self.latest_signals:
            cached = self.snapshot_store.load_dashboard_snapshot()
            if cached:
                return cached

        snapshot = self.build_dashboard_snapshot()
        self.snapshot_store.save_dashboard_snapshot(snapshot)
        return snapshot

    def build_dashboard_snapshot(self) -> Dict[str, Any]:
        records = self.get_records(timeframe="30d", limit=120)
        provider_status = self.get_provider_status()

        category_buckets: Dict[str, List[float]] = {}
        for record in records:
            category_buckets.setdefault(record.category.value, []).append(record.normalized_score)

        category_summary = {
            category_name: {
                "count": len(scores),
                "avg_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
            }
            for category_name, scores in category_buckets.items()
        }
        history_analysis = self.analyze_history(records)

        envelope = AltDataSnapshotEnvelope(
            snapshot_timestamp=datetime.now().isoformat(),
            providers=provider_status,
            signals=self.latest_signals,
            category_summary={
                category_name: {
                    **summary,
                    "delta_score": history_analysis["category_trends"].get(category_name, {}).get("delta_score", 0.0),
                    "momentum": history_analysis["category_trends"].get(category_name, {}).get("momentum", "stable"),
                }
                for category_name, summary in category_summary.items()
            },
            recent_records=[record.to_dict() for record in records[:20]],
            evidence_summary=self.build_evidence_summary(records, limit=8),
            refresh_status=self.get_refresh_status_dict(),
            staleness=self._build_staleness(),
            provider_health=self._build_provider_health(),
        )
        payload = envelope.to_dict()
        payload["source_mode_summary"] = self._build_source_mode_summary(records)
        return payload

    def get_provider_status(self) -> Dict[str, Dict[str, Any]]:
        payload: Dict[str, Dict[str, Any]] = {}
        for name, provider in self.providers.items():
            provider_info = provider.get_provider_info()
            refresh_status = self.refresh_status.get(name, ProviderRefreshStatus(provider=name)).to_dict()
            payload[name] = {
                **provider_info,
                "refresh_status": refresh_status,
                "snapshot_age_seconds": refresh_status.get("snapshot_age_seconds"),
            }
        return payload

    def get_refresh_status_dict(self, category: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        payload: Dict[str, Dict[str, Any]] = {}
        for name, status in self.refresh_status.items():
            provider = self.providers.get(name)
            provider_category = provider.category.value if provider else None
            if category and provider_category != category:
                continue
            payload[name] = status.to_dict()
        return payload

    def get_status(self, scheduler_status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        snapshot = self.get_dashboard_snapshot(refresh=False)
        return {
            "snapshot_timestamp": snapshot.get("snapshot_timestamp"),
            "staleness": snapshot.get("staleness", {}),
            "provider_health": snapshot.get("provider_health", {}),
            "source_mode_summary": snapshot.get("source_mode_summary", {}),
            "refresh_status": snapshot.get("refresh_status", {}),
            "providers": snapshot.get("providers", {}),
            "scheduler": scheduler_status or {},
            "paths": self.snapshot_store.get_paths_summary(),
        }

    def _bootstrap_from_snapshots(self) -> None:
        raw_status = self.snapshot_store.load_refresh_status()
        for name, status_payload in raw_status.items():
            self.refresh_status[name] = ProviderRefreshStatus.from_dict(status_payload)

        for name, snapshot in self.snapshot_store.load_all_provider_snapshots().items():
            provider = self.providers.get(name)
            if provider is None:
                continue
            records = [
                AltDataRecord.from_dict(record_payload)
                for record_payload in snapshot.get("records", [])
            ]
            provider._history = records[-500:]
            last_update = snapshot.get("provider_info", {}).get("last_update")
            if last_update:
                provider._last_update = datetime.fromisoformat(last_update)
            self.latest_signals[name] = snapshot.get("signal", {})
            snapshot_status = snapshot.get("refresh_status")
            if snapshot_status and name not in self.refresh_status:
                self.refresh_status[name] = ProviderRefreshStatus.from_dict(snapshot_status)

        cached_dashboard = self.snapshot_store.load_dashboard_snapshot()
        if cached_dashboard:
            snapshot_time = cached_dashboard.get("snapshot_timestamp")
            if snapshot_time:
                self.last_refresh = datetime.fromisoformat(snapshot_time)

    def _persist_refresh_status(self) -> None:
        self.snapshot_store.save_refresh_status(
            {name: status.to_dict() for name, status in self.refresh_status.items()}
        )

    def _compute_snapshot_age_seconds(self, timestamp: Optional[str]) -> Optional[float]:
        if not timestamp:
            return None
        try:
            age = (datetime.now() - datetime.fromisoformat(timestamp)).total_seconds()
            return round(max(age, 0.0), 2)
        except ValueError:
            return None

    def _build_staleness(self) -> Dict[str, Any]:
        ages = [
            status.snapshot_age_seconds
            for status in self.refresh_status.values()
            if status.snapshot_age_seconds is not None
        ]
        max_age = round(max(ages), 2) if ages else None
        is_stale = any((age or 0.0) > 6 * 3600 for age in ages)
        return {
            "max_snapshot_age_seconds": max_age,
            "is_stale": is_stale,
            "label": "stale" if is_stale else "fresh",
            "provider_count": len(self.providers),
        }

    def _build_provider_health(self) -> Dict[str, Any]:
        counts = {"success": 0, "degraded": 0, "error": 0, "running": 0, "idle": 0}
        per_provider: Dict[str, Any] = {}
        for status in self.refresh_status.values():
            counts.setdefault(status.status, 0)
            counts[status.status] += 1
        for name, status in self.refresh_status.items():
            signal = self.latest_signals.get(name, {})
            per_provider[name] = {
                "status": status.status,
                "confidence": round(float(signal.get("confidence", 0.0) or 0.0), 4),
                "record_count": int(signal.get("record_count", 0) or 0),
                "source_mode_summary": signal.get("source_mode_summary", {}),
                "snapshot_age_seconds": status.snapshot_age_seconds,
                "error": status.error,
            }
        payload = {
            "counts": counts,
            "healthy_providers": counts.get("success", 0),
            "degraded_providers": counts.get("degraded", 0),
            "error_providers": counts.get("error", 0),
            "providers": per_provider,
        }
        payload.update(per_provider)
        return payload

    def _build_source_mode_summary(self, records: List[AltDataRecord]) -> Dict[str, Any]:
        source_mode_counts: Dict[str, int] = {}
        category_modes: Dict[str, Dict[str, int]] = {}
        for record in records:
            mode = str((record.metadata or {}).get("source_mode") or "derived")
            source_mode_counts[mode] = source_mode_counts.get(mode, 0) + 1
            bucket = category_modes.setdefault(record.category.value, {})
            bucket[mode] = bucket.get(mode, 0) + 1

        provider_modes = {
            name: signal.get("source_mode_summary", {})
            for name, signal in self.latest_signals.items()
            if isinstance(signal, dict)
        }
        dominant = max(source_mode_counts.items(), key=lambda item: item[1])[0] if source_mode_counts else "derived"
        return {
            "counts": source_mode_counts,
            "dominant": dominant,
            "category_modes": category_modes,
            "provider_modes": provider_modes,
        }

    def _merge_provider_kwargs(self, name: str, runtime_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(DEFAULT_PROVIDER_CONFIG.get(name, {}))
        merged.update(self.config.get("defaults", {}).get(name, {}))
        merged.update(runtime_kwargs)
        return merged

    @staticmethod
    def _build_category_series(records: List[AltDataRecord]) -> List[Dict[str, Any]]:
        daily_buckets: Dict[str, Dict[str, Any]] = {}
        for record in records:
            day_key = record.timestamp.strftime("%Y-%m-%d")
            bucket = daily_buckets.setdefault(
                day_key,
                {"date": day_key, "count": 0, "score_total": 0.0, "confidence_total": 0.0},
            )
            bucket["count"] += 1
            bucket["score_total"] += float(record.normalized_score)
            bucket["confidence_total"] += float(record.confidence)

        series = []
        for bucket in sorted(daily_buckets.values(), key=lambda item: item["date"]):
            count = max(int(bucket["count"]), 1)
            series.append(
                {
                    "date": bucket["date"],
                    "count": count,
                    "avg_score": round(bucket["score_total"] / count, 4),
                    "avg_confidence": round(bucket["confidence_total"] / count, 4),
                }
            )
        return series

    @staticmethod
    def _build_category_trend(records: List[AltDataRecord]) -> Dict[str, Any]:
        ordered = sorted(records, key=lambda record: record.timestamp, reverse=True)
        recent = ordered[: min(7, len(ordered))]
        previous = ordered[min(7, len(ordered)): min(14, len(ordered))]

        recent_avg = (
            sum(float(record.normalized_score) for record in recent) / len(recent)
            if recent
            else 0.0
        )
        previous_avg = (
            sum(float(record.normalized_score) for record in previous) / len(previous)
            if previous
            else 0.0
        )
        delta_score = recent_avg - previous_avg
        if delta_score >= 0.12:
            momentum = "strengthening"
        elif delta_score <= -0.12:
            momentum = "weakening"
        else:
            momentum = "stable"

        tag_counts: Dict[str, int] = {}
        for record in ordered:
            for tag in record.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        return {
            "count": len(ordered),
            "avg_score": round(
                sum(float(record.normalized_score) for record in ordered) / len(ordered),
                4,
            ) if ordered else 0.0,
            "recent_avg_score": round(recent_avg, 4),
            "previous_avg_score": round(previous_avg, 4),
            "delta_score": round(delta_score, 4),
            "momentum": momentum,
            "high_confidence_count": len([record for record in ordered if float(record.confidence) >= 0.7]),
            "top_tags": [tag for tag, _ in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:3]],
        }

    @staticmethod
    def _parse_timeframe(timeframe: str) -> timedelta:
        value = (timeframe or "7d").strip().lower()
        if value.endswith("h"):
            return timedelta(hours=max(1, int(value[:-1] or 1)))
        if value.endswith("w"):
            return timedelta(weeks=max(1, int(value[:-1] or 1)))
        if value.endswith("d"):
            return timedelta(days=max(1, int(value[:-1] or 1)))
        return timedelta(days=7)

    @staticmethod
    def _extract_record_headline(record: AltDataRecord) -> str:
        raw = record.raw_value if isinstance(record.raw_value, dict) else {}
        return (
            raw.get("title")
            or raw.get("company")
            or raw.get("ticker")
            or raw.get("source_name")
            or record.source
        )

    def _record_to_evidence(self, record: AltDataRecord) -> Dict[str, Any]:
        entity = resolve_entity(record.raw_value, record.tags, self._extract_record_headline(record))
        source_meta = self._infer_source_tier(record.source)
        freshness = self._build_freshness_meta(record.timestamp)
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        return {
            "record_id": record.record_id,
            "timestamp": record.timestamp.isoformat(),
            "source": record.source,
            "category": record.category.value,
            "headline": self._extract_record_headline(record),
            "excerpt": self._extract_record_excerpt(record),
            "facts": self._extract_record_facts(record),
            "canonical_entity": entity.get("canonical", ""),
            "entity_type": entity.get("entity_type", ""),
            "entity_aliases": entity.get("aliases", [])[:6],
            "source_tier": source_meta["tier"],
            "trust_score": source_meta["trust_score"],
            "age_hours": freshness["age_hours"],
            "freshness_label": freshness["label"],
            "freshness_weight": freshness["weight"],
            "normalized_score": round(float(record.normalized_score), 4),
            "confidence": round(float(record.confidence), 4),
            "source_mode": metadata.get("source_mode", "derived"),
            "lag_days": metadata.get("lag_days"),
            "coverage": metadata.get("coverage"),
            "tags": record.tags[:4],
        }

    @staticmethod
    def _extract_record_excerpt(record: AltDataRecord) -> str:
        raw = record.raw_value if isinstance(record.raw_value, dict) else {}
        category = record.category.value

        if category == "policy":
            excerpt = str(raw.get("excerpt") or raw.get("summary") or "").strip()
            if excerpt:
                return excerpt[:160]
            return (
                f"policy_shift={float(raw.get('policy_shift', 0.0)):.2f}; "
                f"will_intensity={float(raw.get('will_intensity', 0.0)):.2f}"
            )
        if category == "hiring":
            company = raw.get("company") or raw.get("ticker") or ""
            return (
                f"{company} dilution_ratio={float(raw.get('dilution_ratio', 0.0)):.2f}; "
                f"signal={raw.get('signal', 'neutral')}"
            ).strip()
        if category == "executive_governance":
            company = raw.get("company") or raw.get("symbol") or ""
            return (
                f"{company} governance_risk={float(raw.get('governance_risk', 0.0)):.2f}; "
                f"technical_authority={float(raw.get('technical_authority_score', 0.0)):.2f}"
            ).strip()
        if category == "insider_flow":
            company = raw.get("company") or raw.get("symbol") or ""
            return (
                f"{company} net_action={raw.get('net_action', 'neutral')}; "
                f"conviction={float(raw.get('conviction_score', 0.0)):.2f}"
            ).strip()
        if category == "policy_execution":
            department = raw.get("department_label") or raw.get("department") or ""
            return (
                f"{department} execution={raw.get('execution_status', 'unknown')}; "
                f"reversal_count={int(raw.get('reversal_count', 0) or 0)}"
            ).strip()
        if category == "bidding":
            industry = raw.get("industry") or raw.get("industry_id") or ""
            amount = raw.get("amount", 0)
            return f"{industry} amount={amount}"
        if category == "env_assessment":
            return f"status={raw.get('status', '') or 'unknown'}"
        if category in {"commodity_inventory", "customs", "port_congestion"}:
            for key in ("score", "inventory", "throughput", "congestion", "value"):
                if key in raw:
                    return f"{key}={raw.get(key)}"
        return str(raw.get("summary") or raw.get("title") or raw.get("message") or "")[:160]

    @staticmethod
    def _extract_record_facts(record: AltDataRecord) -> Dict[str, Any]:
        raw = record.raw_value if isinstance(record.raw_value, dict) else {}
        category = record.category.value

        if category == "policy":
            return {
                "policy_shift": round(float(raw.get("policy_shift", 0.0) or 0.0), 4),
                "will_intensity": round(float(raw.get("will_intensity", 0.0) or 0.0), 4),
                "impact_count": len(raw.get("industry_impact", {}) or {}),
                "text_length": int(raw.get("text_length", 0) or 0),
            }
        if category == "hiring":
            return {
                "company": raw.get("company", ""),
                "ticker": raw.get("ticker", ""),
                "dilution_ratio": round(float(raw.get("dilution_ratio", 0.0) or 0.0), 4),
                "signal": raw.get("signal", ""),
            }
        if category == "executive_governance":
            return {
                "company": raw.get("company", ""),
                "technical_authority_score": round(float(raw.get("technical_authority_score", 0.0) or 0.0), 4),
                "capital_markets_pressure": round(float(raw.get("capital_markets_pressure", 0.0) or 0.0), 4),
                "governance_risk": round(float(raw.get("governance_risk", 0.0) or 0.0), 4),
            }
        if category == "insider_flow":
            return {
                "company": raw.get("company", ""),
                "net_action": raw.get("net_action", ""),
                "net_value_musd": round(float(raw.get("net_value_musd", 0.0) or 0.0), 4),
                "conviction_score": round(float(raw.get("conviction_score", 0.0) or 0.0), 4),
            }
        if category == "policy_execution":
            return {
                "department": raw.get("department", ""),
                "policy_id": raw.get("policy_id", ""),
                "execution_status": raw.get("execution_status", ""),
                "reversal_count": int(raw.get("reversal_count", 0) or 0),
            }
        if category == "bidding":
            return {
                "industry": raw.get("industry", "") or raw.get("industry_id", ""),
                "amount": raw.get("amount", 0),
                "source": raw.get("source", ""),
            }
        if category == "env_assessment":
            return {
                "status": raw.get("status", ""),
                "source": raw.get("source", ""),
            }
        return {
            key: raw.get(key)
            for key in list(raw.keys())[:4]
        }

    @staticmethod
    def _build_freshness_meta(timestamp: datetime) -> Dict[str, Any]:
        age_hours = max((datetime.now() - timestamp).total_seconds() / 3600, 0.0)
        if age_hours <= 24:
            label = "fresh"
            weight = 1.0
        elif age_hours <= 24 * 3:
            label = "recent"
            weight = 0.75
        elif age_hours <= 24 * 7:
            label = "aging"
            weight = 0.5
        else:
            label = "stale"
            weight = 0.25
        return {
            "age_hours": round(age_hours, 2),
            "label": label,
            "weight": weight,
        }

    @staticmethod
    def _infer_source_tier(source: str) -> Dict[str, Any]:
        normalized = str(source or "").lower()
        for prefix, (tier, trust_score) in SOURCE_TIER_RULES:
            if normalized.startswith(prefix):
                return {"tier": tier, "trust_score": trust_score}
        return {"tier": "derived", "trust_score": 0.65}

    @staticmethod
    def _build_conflict_summary(evidence_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in evidence_rows:
            target = item.get("canonical_entity") or item.get("category") or "unknown"
            grouped.setdefault(target, []).append(item)

        conflicts: List[Dict[str, Any]] = []
        for target, items in grouped.items():
            positive = [
                item for item in items
                if float(item.get("normalized_score", 0.0) or 0.0) >= 0.18
                and float(item.get("confidence", 0.0) or 0.0) >= 0.55
            ]
            negative = [
                item for item in items
                if float(item.get("normalized_score", 0.0) or 0.0) <= -0.18
                and float(item.get("confidence", 0.0) or 0.0) >= 0.55
            ]
            if not positive or not negative:
                continue

            strongest_positive = max(positive, key=lambda item: float(item.get("normalized_score", 0.0) or 0.0))
            strongest_negative = min(negative, key=lambda item: float(item.get("normalized_score", 0.0) or 0.0))
            score_gap = round(
                float(strongest_positive.get("normalized_score", 0.0) or 0.0)
                - float(strongest_negative.get("normalized_score", 0.0) or 0.0),
                4,
            )
            positive_sources = sorted({item.get("source", "") for item in positive if item.get("source")})
            negative_sources = sorted({item.get("source", "") for item in negative if item.get("source")})
            positive_official = [
                item for item in positive
                if item.get("source_tier") == "official"
            ]
            negative_official = [
                item for item in negative
                if item.get("source_tier") == "official"
            ]
            if positive_official and negative_official:
                source_pattern = "official_split"
                source_pattern_label = "官方源内部冲突"
            elif (positive_official and negative) or (negative_official and positive):
                source_pattern = "official_vs_derived"
                source_pattern_label = "官方源与派生源冲突"
            else:
                source_pattern = "derived_split"
                source_pattern_label = "派生源内部冲突"
            conflicts.append(
                {
                    "target": target,
                    "target_type": strongest_positive.get("entity_type") or "category",
                    "positive_sources": positive_sources,
                    "negative_sources": negative_sources,
                    "positive_official_count": len(positive_official),
                    "negative_official_count": len(negative_official),
                    "source_pattern": source_pattern,
                    "source_pattern_label": source_pattern_label,
                    "positive_headline": strongest_positive.get("headline", ""),
                    "negative_headline": strongest_negative.get("headline", ""),
                    "score_gap": score_gap,
                    "evidence_count": len(items),
                    "summary": (
                        f"{target} 同时存在正负信号，"
                        f"正向 {len(positive_sources)} 源 / 负向 {len(negative_sources)} 源"
                    ),
                }
            )

        conflicts.sort(key=lambda item: (-float(item["score_gap"]), -int(item["evidence_count"]), item["target"]))
        if not conflicts:
            level = "none"
        elif any(float(item["score_gap"]) >= 0.9 for item in conflicts):
            level = "high"
        elif any(float(item["score_gap"]) >= 0.55 for item in conflicts):
            level = "medium"
        else:
            level = "low"
        return {
            "conflict_count": len(conflicts),
            "conflict_level": level,
            "conflicts": conflicts[:6],
        }

    @classmethod
    def _build_conflict_trend(cls, evidence_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if len(evidence_rows) < 2:
            return {
                "trend": "stable",
                "reason": "样本不足，默认稳定",
                "recent_conflict_count": 0,
                "previous_conflict_count": 0,
            }

        midpoint = max(len(evidence_rows) // 2, 1)
        recent = evidence_rows[:midpoint]
        previous = evidence_rows[midpoint:]
        recent_summary = cls._build_conflict_summary(recent)
        previous_summary = cls._build_conflict_summary(previous)
        recent_gap = max([float(item.get("score_gap", 0.0) or 0.0) for item in recent_summary["conflicts"]] or [0.0])
        previous_gap = max([float(item.get("score_gap", 0.0) or 0.0) for item in previous_summary["conflicts"]] or [0.0])

        if recent_summary["conflict_count"] > previous_summary["conflict_count"] or recent_gap >= previous_gap + 0.15:
            trend = "rising"
            reason = "近期证据分裂比前期更强"
        elif recent_summary["conflict_count"] < previous_summary["conflict_count"] or recent_gap + 0.15 < previous_gap:
            trend = "easing"
            reason = "近期证据分裂较前期缓和"
        elif recent_summary["conflict_count"] == 0 and previous_summary["conflict_count"] == 0:
            trend = "stable"
            reason = "近期未检测到明显证据分裂"
        else:
            trend = "stable"
            reason = "近期证据分裂程度基本持平"

        return {
            "trend": trend,
            "reason": reason,
            "recent_conflict_count": recent_summary["conflict_count"],
            "previous_conflict_count": previous_summary["conflict_count"],
        }
