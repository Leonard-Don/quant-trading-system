"""Realtime alert persistence for the realtime workstation."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src.utils.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_ALERTS_PAYLOAD = {
    "alerts": [],
    "alert_hit_history": [],
}
MAX_ALERT_HIT_HISTORY = 80

VALID_CONDITIONS = {
    "price_above",
    "price_below",
    "change_pct_above",
    "change_pct_below",
    "intraday_range_above",
    "relative_volume_above",
    "touch_high",
    "touch_low",
}


class RealtimeAlertsStore:
    """File-backed alert store keyed by realtime profile."""

    def __init__(self, storage_path: str | Path | None = None):
        if storage_path is None:
            storage_path = PROJECT_ROOT / "data" / "realtime_alerts"

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

    def _get_alerts_file(self, profile_id: str | None) -> Path:
        normalized_profile = self._normalize_profile_id(profile_id)
        return self.storage_path / f"{normalized_profile}.json"

    def _normalize_alerts(self, payload: Dict[str, Any] | None) -> Dict[str, Any]:
        alerts = payload.get("alerts") if isinstance(payload, dict) else []
        alert_hit_history = payload.get("alert_hit_history") if isinstance(payload, dict) else []
        normalized_alerts: List[Dict[str, Any]] = []
        normalized_history: List[Dict[str, Any]] = []
        warnings: List[str] = []

        for index, raw_alert in enumerate(alerts or []):
            if not isinstance(raw_alert, dict):
                warnings.append(f"alerts[{index}]: skipped (not a dict)")
                continue

            symbol = str(raw_alert.get("symbol") or "").strip().upper()
            condition = str(raw_alert.get("condition") or "price_above").strip()
            if not symbol:
                warnings.append(f"alerts[{index}]: skipped (missing symbol)")
                continue
            if condition not in VALID_CONDITIONS:
                warnings.append(f"alerts[{index}]: skipped (invalid condition '{condition}')")
                continue

            threshold = raw_alert.get("threshold")
            try:
                threshold_value = float(threshold) if threshold is not None else None
            except (TypeError, ValueError):
                threshold_value = None

            tolerance = raw_alert.get("tolerancePercent")
            try:
                tolerance_value = float(tolerance) if tolerance is not None else 0.1
            except (TypeError, ValueError):
                tolerance_value = 0.1

            cooldown_minutes = raw_alert.get("cooldownMinutes")
            try:
                cooldown_value = max(0, int(cooldown_minutes)) if cooldown_minutes is not None else 15
            except (TypeError, ValueError):
                cooldown_value = 15

            normalized_alerts.append({
                **raw_alert,
                "symbol": symbol,
                "condition": condition,
                "threshold": threshold_value,
                "tolerancePercent": tolerance_value,
                "cooldownMinutes": cooldown_value,
            })

        for raw_entry in alert_hit_history or []:
            if not isinstance(raw_entry, dict):
                continue
            normalized_history.append(dict(raw_entry))

        history_count = len(normalized_history)
        if history_count > MAX_ALERT_HIT_HISTORY:
            warnings.append(
                f"alert_hit_history truncated from {history_count} to {MAX_ALERT_HIT_HISTORY}"
            )

        return {
            "alerts": normalized_alerts,
            "alert_hit_history": normalized_history[:MAX_ALERT_HIT_HISTORY],
            "_warnings": warnings,
        }

    def _normalize_history_entry(self, entry: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if not isinstance(entry, dict):
            return None
        symbol = str(entry.get("symbol") or "").strip().upper()
        trigger_time = str(entry.get("triggerTime") or entry.get("trigger_time") or datetime.utcnow().isoformat()).strip()
        entry_id = str(entry.get("id") or "").strip() or f"alert_hit_{symbol or 'unknown'}_{trigger_time}"
        return {
            **entry,
            "id": entry_id,
            "symbol": symbol,
            "triggerTime": trigger_time,
            "condition": str(entry.get("condition") or "").strip() or None,
            "message": str(entry.get("message") or "").strip() or None,
        }

    def record_alert_hit(self, entry: Dict[str, Any], profile_id: str | None = None) -> Dict[str, Any]:
        normalized_entry = self._normalize_history_entry(entry)
        if not normalized_entry:
            raise ValueError("invalid alert history entry")
        with self._lock:
            current = self._load_alerts(profile_id)
            history = list(current.get("alert_hit_history") or [])
            deduped = [item for item in history if str(item.get("id") or "").strip() != normalized_entry["id"]]
            current["alert_hit_history"] = [normalized_entry, *deduped][:MAX_ALERT_HIT_HISTORY]
            self._persist(profile_id, current)
            return {
                "entry": normalized_entry,
                "alert_hit_history": list(current["alert_hit_history"]),
            }

    def _load_alerts(self, profile_id: str | None) -> Dict[str, Any]:
        alerts_file = self._get_alerts_file(profile_id)
        try:
            if alerts_file.exists():
                with open(alerts_file, "r", encoding="utf-8") as file:
                    return self._normalize_alerts(json.load(file))
        except Exception as exc:
            logger.warning("Failed to load realtime alerts for %s: %s", profile_id, exc)

        return dict(DEFAULT_ALERTS_PAYLOAD)

    def _persist(self, profile_id: str | None, payload: Dict[str, Any]) -> None:
        alerts_file = self._get_alerts_file(profile_id)
        try:
            with open(alerts_file, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error("Failed to persist realtime alerts for %s: %s", profile_id, exc)

    def get_alerts(self, profile_id: str | None = None) -> Dict[str, Any]:
        with self._lock:
            payload = self._load_alerts(profile_id)
            return {
                "alerts": list(payload["alerts"]),
                "alert_hit_history": list(payload["alert_hit_history"]),
            }

    def update_alerts(self, payload: Dict[str, Any], profile_id: str | None = None) -> Dict[str, Any]:
        with self._lock:
            normalized = self._normalize_alerts(payload)
            warnings = normalized.pop("_warnings", [])
            self._persist(profile_id, normalized)
            result = self.get_alerts(profile_id)
            if warnings:
                result["_warnings"] = warnings
            return result


realtime_alerts_store = RealtimeAlertsStore()
