"""Realtime journal persistence for review snapshots and timeline events."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List

from src.utils.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_JOURNAL_PAYLOAD = {
    "review_snapshots": [],
    "timeline_events": [],
}
MAX_REVIEW_SNAPSHOTS = 48
MAX_TIMELINE_EVENTS = 120


class RealtimeJournalStore:
    """File-backed journal store keyed by realtime profile."""

    def __init__(self, storage_path: str | Path | None = None):
        if storage_path is None:
            storage_path = PROJECT_ROOT / "data" / "realtime_journal"

        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _normalize_profile_id(self, profile_id: str | None) -> str:
        raw_value = str(profile_id or "default").strip().lower()
        sanitized = "".join(
            character if character.isalnum() or character in {"-", "_"} else "-"
            for character in raw_value
        ).strip("-_")
        return sanitized or "default"

    def _get_journal_file(self, profile_id: str | None) -> Path:
        normalized_profile = self._normalize_profile_id(profile_id)
        return self.storage_path / f"{normalized_profile}.json"

    def _normalize_entries(self, entries: Any, *, max_items: int) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for raw_entry in entries or []:
            if not isinstance(raw_entry, dict):
                continue
            normalized.append(dict(raw_entry))
        return normalized[:max_items]

    def _normalize_payload(self, payload: Dict[str, Any] | None) -> Dict[str, Any]:
        payload = dict(payload or {})
        warnings: List[str] = []
        raw_snapshots = payload.get("review_snapshots") or []
        raw_events = payload.get("timeline_events") or []
        snapshots = self._normalize_entries(raw_snapshots, max_items=MAX_REVIEW_SNAPSHOTS)
        events = self._normalize_entries(raw_events, max_items=MAX_TIMELINE_EVENTS)
        if isinstance(raw_snapshots, list) and len(raw_snapshots) > MAX_REVIEW_SNAPSHOTS:
            warnings.append(
                f"review_snapshots truncated from {len(raw_snapshots)} to {MAX_REVIEW_SNAPSHOTS}"
            )
        if isinstance(raw_events, list) and len(raw_events) > MAX_TIMELINE_EVENTS:
            warnings.append(
                f"timeline_events truncated from {len(raw_events)} to {MAX_TIMELINE_EVENTS}"
            )
        return {
            "review_snapshots": snapshots,
            "timeline_events": events,
            "_warnings": warnings,
        }

    def _load_journal(self, profile_id: str | None) -> Dict[str, Any]:
        journal_file = self._get_journal_file(profile_id)
        try:
            if journal_file.exists():
                with open(journal_file, "r", encoding="utf-8") as file:
                    return self._normalize_payload(json.load(file))
        except Exception as exc:
            logger.warning("Failed to load realtime journal for %s: %s", profile_id, exc)

        return dict(DEFAULT_JOURNAL_PAYLOAD)

    def _persist(self, profile_id: str | None, payload: Dict[str, Any]) -> None:
        journal_file = self._get_journal_file(profile_id)
        try:
            with open(journal_file, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error("Failed to persist realtime journal for %s: %s", profile_id, exc)

    def get_journal(self, profile_id: str | None = None) -> Dict[str, Any]:
        with self._lock:
            payload = self._load_journal(profile_id)
            return {
                "review_snapshots": list(payload["review_snapshots"]),
                "timeline_events": list(payload["timeline_events"]),
            }

    def update_journal(self, payload: Dict[str, Any], profile_id: str | None = None) -> Dict[str, Any]:
        with self._lock:
            normalized = self._normalize_payload(payload)
            warnings = normalized.pop("_warnings", [])
            self._persist(profile_id, normalized)
            result = self.get_journal(profile_id)
            if warnings:
                result["_warnings"] = warnings
            return result


realtime_journal_store = RealtimeJournalStore()
