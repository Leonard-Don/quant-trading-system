"""Realtime module preference persistence."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List

from src.utils.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_SYMBOLS = [
    '^GSPC', '^DJI', '^IXIC', '^RUT', '000001.SS', '^HSI',
    'AAPL', 'NVDA', 'TSLA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'BABA',
    '600519.SS', '601398.SS', '300750.SZ', '000858.SZ',
    'BTC-USD', 'ETH-USD', 'SOL-USD', 'BNB-USD', 'DOGE-USD',
    '^TNX', '^TYX', 'TLT',
    'GC=F', 'CL=F', 'SI=F',
    'SPY', 'QQQ', 'UVXY',
]
VALID_TABS = {'index', 'us', 'cn', 'crypto', 'bond', 'future', 'option', 'other'}
DEFAULT_PREFERENCES = {
    "symbols": DEFAULT_SYMBOLS,
    "active_tab": "index",
}


class RealtimePreferencesStore:
    """File-backed preference store for realtime watchlist settings."""

    def __init__(self, storage_path: str | Path | None = None):
        if storage_path is None:
            storage_path = PROJECT_ROOT / "data" / "realtime"

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
        normalized_profile = self._normalize_profile_id(profile_id)
        return self.storage_path / f"{normalized_profile}.json"

    def _normalize_symbols(self, symbols: List[str]) -> List[str]:
        normalized: List[str] = []
        seen = set()
        for symbol in symbols:
            if not isinstance(symbol, str):
                continue
            canonical = symbol.strip().upper()
            if canonical and canonical not in seen:
                normalized.append(canonical)
                seen.add(canonical)
        return normalized

    def _normalize_preferences(self, payload: Dict[str, Any] | None) -> Dict[str, Any]:
        payload = dict(payload or {})
        symbols = self._normalize_symbols(payload.get("symbols") or DEFAULT_PREFERENCES["symbols"])
        active_tab = payload.get("active_tab") or DEFAULT_PREFERENCES["active_tab"]
        if active_tab not in VALID_TABS:
            active_tab = DEFAULT_PREFERENCES["active_tab"]

        return {
            "symbols": symbols or list(DEFAULT_PREFERENCES["symbols"]),
            "active_tab": active_tab,
        }

    def _load_preferences(self, profile_id: str | None) -> Dict[str, Any]:
        preferences_file = self._get_preferences_file(profile_id)
        try:
            if preferences_file.exists():
                with open(preferences_file, "r", encoding="utf-8") as file:
                    return self._normalize_preferences(json.load(file))
        except Exception as exc:
            logger.warning("Failed to load realtime preferences for %s: %s", profile_id, exc)

        return dict(DEFAULT_PREFERENCES)

    def _persist(self, profile_id: str | None, preferences: Dict[str, Any]) -> None:
        preferences_file = self._get_preferences_file(profile_id)
        try:
            with open(preferences_file, "w", encoding="utf-8") as file:
                json.dump(preferences, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error("Failed to persist realtime preferences for %s: %s", profile_id, exc)

    def get_preferences(self, profile_id: str | None = None) -> Dict[str, Any]:
        with self._lock:
            preferences = self._load_preferences(profile_id)
            return {
                "symbols": list(preferences["symbols"]),
                "active_tab": preferences["active_tab"],
            }

    def update_preferences(self, payload: Dict[str, Any], profile_id: str | None = None) -> Dict[str, Any]:
        with self._lock:
            preferences = self._normalize_preferences(payload)
            self._persist(profile_id, preferences)
            return self.get_preferences(profile_id)


realtime_preferences_store = RealtimePreferencesStore()
