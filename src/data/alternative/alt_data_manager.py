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
from .policy_radar import PolicySignalProvider
from .supply_chain import SupplyChainSignalProvider

logger = logging.getLogger(__name__)


DEFAULT_PROVIDER_CONFIG: Dict[str, Dict[str, Any]] = {
    "policy_radar": {
        "sources": ["ndrc", "nea"],
        "limit": 5,
        "days_back": 14,
    },
    "supply_chain": {
        "industries": ["ai_compute", "grid", "nuclear"],
        "days_back": 30,
    },
    "macro_hf": {
        "metals": ["copper", "aluminium"],
        "categories": ["semiconductors", "copper_ore", "ev_battery"],
    },
}


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
        return {
            "policy_radar": PolicySignalProvider(
                provider_config.get("policy_radar", self.config)
            ),
            "supply_chain": SupplyChainSignalProvider(
                provider_config.get("supply_chain", self.config)
            ),
            "macro_hf": MacroHFSignalProvider(
                provider_config.get("macro_hf", self.config)
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

        envelope = AltDataSnapshotEnvelope(
            snapshot_timestamp=datetime.now().isoformat(),
            providers=provider_status,
            signals=self.latest_signals,
            category_summary=category_summary,
            recent_records=[record.to_dict() for record in records[:20]],
            refresh_status=self.get_refresh_status_dict(),
            staleness=self._build_staleness(),
            provider_health=self._build_provider_health(),
        )
        return envelope.to_dict()

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
        for status in self.refresh_status.values():
            counts.setdefault(status.status, 0)
            counts[status.status] += 1
        return {
            "counts": counts,
            "healthy_providers": counts.get("success", 0),
            "degraded_providers": counts.get("degraded", 0),
            "error_providers": counts.get("error", 0),
        }

    def _merge_provider_kwargs(self, name: str, runtime_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(DEFAULT_PROVIDER_CONFIG.get(name, {}))
        merged.update(self.config.get("defaults", {}).get(name, {}))
        merged.update(runtime_kwargs)
        return merged

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
