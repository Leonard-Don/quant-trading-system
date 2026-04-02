"""Industry module preference persistence."""

from __future__ import annotations

import json
import logging
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from src.utils.config import PROJECT_ROOT

logger = logging.getLogger(__name__)
_PREFERENCES_MAX_SAVED_VIEWS = 24
_PREFERENCES_MAX_FILE_BYTES = 512 * 1024

DEFAULT_ALERT_THRESHOLDS = {
    "resonance_score": 80,
    "resonance_change_pct": 2.0,
    "resonance_money_flow_yi": 0.0,
    "capital_inflow_yi": 8.0,
    "capital_inflow_change_pct": 0.5,
    "risk_release_outflow_yi": 8.0,
    "risk_release_change_pct": -1.0,
    "high_volatility_threshold": 4.5,
    "high_volatility_change_pct": 2.0,
    "rotation_turnover_threshold": 3.5,
    "rotation_change_pct": 1.0,
}

DEFAULT_PREFERENCES = {
    "watchlist_industries": [],
    "saved_views": [],
    "alert_thresholds": DEFAULT_ALERT_THRESHOLDS,
}


class IndustryPreferencesStore:
    """File-backed preference store for industry heat module."""

    def __init__(self, storage_path: str | Path | None = None):
        if storage_path is None:
            storage_path = PROJECT_ROOT / "data" / "industry_preferences"
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

    def _get_preferences_file(self, profile_id: str | None) -> Path:
        return self.storage_path / f"{self._normalize_profile_id(profile_id)}.json"

    @staticmethod
    def _format_size(num_bytes: int) -> str:
        if num_bytes < 1024:
            return f"{num_bytes} B"
        if num_bytes < 1024 * 1024:
            return f"{num_bytes / 1024:.1f} KB"
        return f"{num_bytes / (1024 * 1024):.2f} MB"

    def _normalize_preferences(self, payload: Dict[str, Any] | None) -> Dict[str, Any]:
        payload = dict(payload or {})
        raw_watchlist = payload.get("watchlist_industries") or []
        watchlist = []
        seen = set()
        for item in raw_watchlist:
            if not isinstance(item, str):
                continue
            value = item.strip()
            if value and value not in seen:
                watchlist.append(value)
                seen.add(value)

        raw_views = payload.get("saved_views") or []
        saved_views = []
        if isinstance(raw_views, list):
            for view in raw_views:
                if not isinstance(view, dict):
                    continue
                view_id = str(view.get("id") or "").strip()
                if not view_id:
                    continue
                saved_views.append(view)
        saved_views = saved_views[:_PREFERENCES_MAX_SAVED_VIEWS]

        raw_thresholds = payload.get("alert_thresholds") or {}
        thresholds = deepcopy(DEFAULT_ALERT_THRESHOLDS)
        if isinstance(raw_thresholds, dict):
            for key, default_value in DEFAULT_ALERT_THRESHOLDS.items():
                try:
                    thresholds[key] = float(raw_thresholds.get(key, default_value))
                except (TypeError, ValueError):
                    thresholds[key] = float(default_value)

        return {
            "watchlist_industries": watchlist,
            "saved_views": saved_views,
            "alert_thresholds": thresholds,
        }

    def _load_preferences(self, profile_id: str | None) -> Dict[str, Any]:
        preferences_file = self._get_preferences_file(profile_id)
        try:
            if preferences_file.exists():
                file_size = preferences_file.stat().st_size
                with open(preferences_file, "r", encoding="utf-8") as file:
                    normalized = self._normalize_preferences(json.load(file))
                logger.info(
                    "Loaded industry preferences for %s (%s)",
                    self._normalize_profile_id(profile_id),
                    self._format_size(file_size),
                )
                return normalized
        except Exception as exc:
            logger.warning("Failed to load industry preferences for %s: %s", profile_id, exc)
        return deepcopy(DEFAULT_PREFERENCES)

    def _persist(self, profile_id: str | None, preferences: Dict[str, Any]) -> None:
        preferences_file = self._get_preferences_file(profile_id)
        try:
            normalized = self._normalize_preferences(preferences)
            serialized = json.dumps(normalized, ensure_ascii=False, indent=2)
            encoded = serialized.encode("utf-8")
            while len(encoded) > _PREFERENCES_MAX_FILE_BYTES and normalized["saved_views"]:
                normalized["saved_views"] = normalized["saved_views"][:-1]
                serialized = json.dumps(normalized, ensure_ascii=False, indent=2)
                encoded = serialized.encode("utf-8")
            with open(preferences_file, "w", encoding="utf-8") as file:
                file.write(serialized)
            logger.info(
                "Persisted industry preferences for %s (%s, saved_views=%s)",
                self._normalize_profile_id(profile_id),
                self._format_size(len(encoded)),
                len(normalized["saved_views"]),
            )
        except Exception as exc:
            logger.error("Failed to persist industry preferences for %s: %s", profile_id, exc)

    def get_preferences(self, profile_id: str | None = None) -> Dict[str, Any]:
        with self._lock:
            return self._load_preferences(profile_id)

    def update_preferences(self, payload: Dict[str, Any], profile_id: str | None = None) -> Dict[str, Any]:
        with self._lock:
            preferences = self._normalize_preferences(payload)
            self._persist(profile_id, preferences)
            return self._load_preferences(profile_id)


industry_preferences_store = IndustryPreferencesStore()
