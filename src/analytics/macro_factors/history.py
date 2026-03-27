"""
宏观概览历史持久化。
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.config import PROJECT_ROOT

logger = logging.getLogger(__name__)


class MacroHistoryStore:
    """File-backed macro overview history."""

    def __init__(self, storage_path: str | Path | None = None, max_records: int = 400):
        base_dir = Path(storage_path) if storage_path else PROJECT_ROOT / "data" / "macro_history"
        self.storage_path = base_dir
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.history_file = self.storage_path / "history.json"
        self.max_records = max_records
        self._lock = threading.RLock()
        self.snapshots: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        try:
            if self.history_file.exists():
                with open(self.history_file, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                    self.snapshots = payload if isinstance(payload, list) else []
        except Exception as exc:
            logger.warning("Failed to load macro history: %s", exc)
            self.snapshots = []

    def _persist(self) -> None:
        try:
            with open(self.history_file, "w", encoding="utf-8") as handle:
                json.dump(self.snapshots, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error("Failed to persist macro history: %s", exc)

    def _normalize_factor(self, factor: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": factor.get("name", ""),
            "value": round(float(factor.get("value", 0) or 0), 4),
            "z_score": round(float(factor.get("z_score", 0) or 0), 4),
            "signal": int(factor.get("signal", 0) or 0),
            "confidence": round(float(factor.get("confidence", 0) or 0), 4),
            "metadata": factor.get("metadata") or {},
        }

    def _normalize_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "snapshot_timestamp": snapshot.get("snapshot_timestamp") or "",
            "macro_score": round(float(snapshot.get("macro_score", 0) or 0), 4),
            "macro_signal": int(snapshot.get("macro_signal", 0) or 0),
            "confidence": round(float(snapshot.get("confidence", 0) or 0), 4),
            "factors": [self._normalize_factor(factor) for factor in (snapshot.get("factors") or [])],
            "provider_health": snapshot.get("provider_health") or {},
            "data_freshness": snapshot.get("data_freshness") or {},
        }

    def append_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_snapshot(snapshot)
        timestamp = normalized.get("snapshot_timestamp")
        with self._lock:
            self.snapshots = [
                existing for existing in self.snapshots if existing.get("snapshot_timestamp") != timestamp
            ]
            self.snapshots.insert(0, normalized)
            self.snapshots = self.snapshots[: self.max_records]
            self._persist()
        return dict(normalized)

    def list_snapshots(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self.snapshots[:limit]]

    def get_previous_snapshot(self, snapshot_timestamp: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self.snapshots:
                return None
            if not snapshot_timestamp:
                return dict(self.snapshots[1]) if len(self.snapshots) > 1 else None

            for snapshot in self.snapshots:
                if snapshot.get("snapshot_timestamp") != snapshot_timestamp:
                    return dict(snapshot)
            return None
