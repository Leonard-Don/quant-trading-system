"""
另类数据治理层：快照持久化、刷新服务与调度器。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_alt_provider import AltDataRecord

logger = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
except ImportError:  # pragma: no cover - graceful fallback when dependency is unavailable
    BackgroundScheduler = None
    IntervalTrigger = None


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ALT_DATA_CACHE_DIR = PROJECT_ROOT / "cache" / "alt_data"


@dataclass
class ProviderRefreshStatus:
    provider: str
    last_success_at: Optional[str] = None
    last_attempt_at: Optional[str] = None
    status: str = "idle"
    record_count: int = 0
    signal_strength: float = 0.0
    confidence: float = 0.0
    error: Optional[str] = None
    duration_ms: float = 0.0
    snapshot_age_seconds: Optional[float] = None

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ProviderRefreshStatus":
        return cls(
            provider=payload.get("provider", "unknown"),
            last_success_at=payload.get("last_success_at"),
            last_attempt_at=payload.get("last_attempt_at"),
            status=payload.get("status", "idle"),
            record_count=int(payload.get("record_count", 0) or 0),
            signal_strength=float(payload.get("signal_strength", 0.0) or 0.0),
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            error=payload.get("error"),
            duration_ms=float(payload.get("duration_ms", 0.0) or 0.0),
            snapshot_age_seconds=payload.get("snapshot_age_seconds"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AltDataRefreshReport:
    requested_provider: str = "all"
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    status: str = "idle"
    ok: bool = True
    signals: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    refresh_status: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
    snapshot_timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass
class AltDataSnapshotEnvelope:
    snapshot_timestamp: Optional[str]
    providers: Dict[str, Dict[str, Any]]
    signals: Dict[str, Dict[str, Any]]
    category_summary: Dict[str, Dict[str, Any]]
    recent_records: List[Dict[str, Any]]
    evidence_summary: Dict[str, Any]
    refresh_status: Dict[str, Dict[str, Any]]
    staleness: Dict[str, Any]
    provider_health: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AltDataSnapshotStore:
    """文件快照存储。"""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir or DEFAULT_ALT_DATA_CACHE_DIR)
        self.providers_dir = self.base_dir / "providers"
        self.dashboard_snapshot_path = self.base_dir / "dashboard_snapshot.json"
        self.refresh_status_path = self.base_dir / "refresh_status.json"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.providers_dir.mkdir(parents=True, exist_ok=True)

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        temp_path.replace(path)

    def _read_json(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read alt-data snapshot %s: %s", path, exc)
            return None

    def provider_snapshot_path(self, provider: str) -> Path:
        return self.providers_dir / f"{provider}.json"

    def save_provider_snapshot(self, provider: str, payload: Dict[str, Any]) -> None:
        self._write_json(self.provider_snapshot_path(provider), payload)

    def load_provider_snapshot(self, provider: str) -> Optional[Dict[str, Any]]:
        return self._read_json(self.provider_snapshot_path(provider))

    def load_all_provider_snapshots(self) -> Dict[str, Dict[str, Any]]:
        snapshots: Dict[str, Dict[str, Any]] = {}
        if not self.providers_dir.exists():
            return snapshots
        for file_path in sorted(self.providers_dir.glob("*.json")):
            payload = self._read_json(file_path)
            if payload is not None:
                snapshots[file_path.stem] = payload
        return snapshots

    def save_dashboard_snapshot(self, payload: Dict[str, Any]) -> None:
        self._write_json(self.dashboard_snapshot_path, payload)

    def load_dashboard_snapshot(self) -> Optional[Dict[str, Any]]:
        return self._read_json(self.dashboard_snapshot_path)

    def save_refresh_status(self, payload: Dict[str, Any]) -> None:
        self._write_json(self.refresh_status_path, payload)

    def load_refresh_status(self) -> Dict[str, Any]:
        return self._read_json(self.refresh_status_path) or {}

    def get_paths_summary(self) -> Dict[str, str]:
        return {
            "base_dir": str(self.base_dir),
            "providers_dir": str(self.providers_dir),
            "dashboard_snapshot": str(self.dashboard_snapshot_path),
            "refresh_status": str(self.refresh_status_path),
        }


class AltDataRefreshService:
    """刷新 provider 并维护快照和元数据。"""

    def __init__(self, manager: "AltDataManager", snapshot_store: AltDataSnapshotStore):
        self.manager = manager
        self.snapshot_store = snapshot_store

    def refresh_provider(
        self,
        name: str,
        force: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        provider = self.manager.get_provider(name)
        started_at = datetime.now()
        previous_status = self.manager.refresh_status.get(
            name, ProviderRefreshStatus(provider=name)
        )
        running_status = ProviderRefreshStatus.from_dict(previous_status.to_dict())
        running_status.status = "running"
        running_status.last_attempt_at = started_at.isoformat()
        running_status.error = None
        self.manager.refresh_status[name] = running_status
        self.manager._persist_refresh_status()

        if not force and not provider.needs_update() and name in self.manager.latest_signals:
            current_signal = self.manager.latest_signals[name]
            snapshot_age_seconds = self.manager._compute_snapshot_age_seconds(current_signal.get("timestamp"))
            cached_status = ProviderRefreshStatus(
                provider=name,
                last_success_at=previous_status.last_success_at or provider.get_provider_info().get("last_update"),
                last_attempt_at=started_at.isoformat(),
                status=previous_status.status if previous_status.status != "idle" else "success",
                record_count=int(current_signal.get("record_count", len(provider.get_history(limit=500)))),
                signal_strength=float(current_signal.get("strength", 0.0) or 0.0),
                confidence=float(current_signal.get("confidence", 0.0) or 0.0),
                error=None,
                duration_ms=0.0,
                snapshot_age_seconds=snapshot_age_seconds,
            )
            self.manager.refresh_status[name] = cached_status
            self.manager._persist_refresh_status()
            return current_signal

        try:
            signal = provider.run_pipeline(**kwargs)
            snapshot_timestamp = datetime.now().isoformat()
            signal["provider"] = name
            records = provider.get_history(limit=500)
            provider_info = provider.get_provider_info()
            status = ProviderRefreshStatus(
                provider=name,
                last_success_at=snapshot_timestamp,
                last_attempt_at=snapshot_timestamp,
                status="success",
                record_count=len(records),
                signal_strength=float(signal.get("strength", 0.0) or 0.0),
                confidence=float(signal.get("confidence", 0.0) or 0.0),
                error=None,
                duration_ms=round((datetime.now() - started_at).total_seconds() * 1000, 2),
                snapshot_age_seconds=0.0,
            )
            snapshot_payload = {
                "provider": name,
                "signal": signal,
                "records": [record.to_dict() for record in records],
                "provider_info": provider_info,
                "snapshot_timestamp": snapshot_timestamp,
                "refresh_status": status.to_dict(),
            }
            self.snapshot_store.save_provider_snapshot(name, snapshot_payload)
            self.manager.latest_signals[name] = signal
            self.manager.refresh_status[name] = status
            self.manager.last_refresh = datetime.now()
            self.manager._persist_refresh_status()
            return signal
        except Exception as exc:
            fallback_snapshot = self.snapshot_store.load_provider_snapshot(name)
            fallback_signal = (fallback_snapshot or {}).get("signal") or {
                "provider": name,
                "source": name,
                "category": getattr(provider.category, "value", "unknown"),
                "signal": 0,
                "strength": 0.0,
                "confidence": 0.0,
                "record_count": 0,
                "timestamp": datetime.now().isoformat(),
                "error": str(exc),
            }
            fallback_status = ProviderRefreshStatus(
                provider=name,
                last_success_at=previous_status.last_success_at,
                last_attempt_at=datetime.now().isoformat(),
                status="degraded" if fallback_snapshot else "error",
                record_count=int(fallback_signal.get("record_count", 0) or 0),
                signal_strength=float(fallback_signal.get("strength", 0.0) or 0.0),
                confidence=float(fallback_signal.get("confidence", 0.0) or 0.0),
                error=str(exc),
                duration_ms=round((datetime.now() - started_at).total_seconds() * 1000, 2),
                snapshot_age_seconds=self.manager._compute_snapshot_age_seconds(
                    fallback_signal.get("timestamp")
                ),
            )
            fallback_signal["provider"] = name
            fallback_signal["error"] = str(exc)
            self.manager.latest_signals[name] = fallback_signal
            self.manager.refresh_status[name] = fallback_status
            self.manager._persist_refresh_status()
            logger.error("Failed to refresh alt-data provider %s: %s", name, exc, exc_info=True)
            return fallback_signal

    def refresh_all(
        self,
        force: bool = False,
        provider_params: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> AltDataRefreshReport:
        provider_params = provider_params or {}
        report = AltDataRefreshReport(requested_provider="all", status="running")
        for name in self.manager.providers:
            signal = self.refresh_provider(
                name, force=force, **provider_params.get(name, {})
            )
            report.signals[name] = signal
            report.refresh_status[name] = self.manager.refresh_status[name].to_dict()
            if self.manager.refresh_status[name].status in {"degraded", "error"}:
                report.ok = False
                if self.manager.refresh_status[name].error:
                    report.errors[name] = self.manager.refresh_status[name].error or ""

        dashboard_snapshot = self.manager.build_dashboard_snapshot()
        self.snapshot_store.save_dashboard_snapshot(dashboard_snapshot)
        report.snapshot_timestamp = dashboard_snapshot.get("snapshot_timestamp")
        report.completed_at = datetime.now().isoformat()
        report.status = "success" if report.ok else "partial"
        return report


class AltDataScheduler:
    """后台调度器。"""

    DEFAULT_INTERVALS_MINUTES = {
        "policy_radar": 60,
        "supply_chain": 360,
        "macro_hf": 180,
        "people_layer": 360,
        "policy_execution": 120,
    }

    def __init__(self, manager: "AltDataManager"):
        self.manager = manager
        self._scheduler = None
        self._jobs_registered = False
        self._available = BackgroundScheduler is not None and IntervalTrigger is not None
        self._started_at: Optional[str] = None
        self._stopped_at: Optional[str] = None
        self._last_error: Optional[str] = None

        if self._available:
            self._scheduler = BackgroundScheduler()

    def start(self) -> None:
        if not self._available:
            self._last_error = "APScheduler not installed"
            logger.warning("AltDataScheduler unavailable: %s", self._last_error)
            return
        if self._scheduler.running:
            return
        if not self._jobs_registered:
            for provider, minutes in self.DEFAULT_INTERVALS_MINUTES.items():
                self._scheduler.add_job(
                    self._refresh_job,
                    IntervalTrigger(minutes=minutes),
                    args=[provider],
                    id=f"alt-data-{provider}",
                    replace_existing=True,
                )
            self._jobs_registered = True
        self._scheduler.start()
        self._started_at = datetime.now().isoformat()
        self._stopped_at = None

    def _refresh_job(self, provider: str) -> None:
        try:
            self.manager.refresh_provider(provider, force=True)
            dashboard_snapshot = self.manager.build_dashboard_snapshot()
            self.manager.snapshot_store.save_dashboard_snapshot(dashboard_snapshot)
        except Exception as exc:  # pragma: no cover - scheduler callback path
            self._last_error = str(exc)
            logger.error("Scheduled alt-data refresh failed for %s: %s", provider, exc, exc_info=True)

    def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._stopped_at = datetime.now().isoformat()

    def get_status(self) -> Dict[str, Any]:
        jobs: List[Dict[str, Any]] = []
        if self._scheduler and self._scheduler.running:
            for job in self._scheduler.get_jobs():
                jobs.append(
                    {
                        "id": job.id,
                        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    }
                )
        return {
            "available": self._available,
            "running": bool(self._scheduler and self._scheduler.running),
            "started_at": self._started_at,
            "stopped_at": self._stopped_at,
            "last_error": self._last_error,
            "jobs": jobs,
            "intervals_minutes": self.DEFAULT_INTERVALS_MINUTES,
        }
