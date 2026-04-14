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
MAX_SUBSCRIBED_SYMBOLS = 200
MAX_WATCH_GROUPS = 20
MAX_SYMBOLS_PER_WATCH_GROUP = 200
DEFAULT_PREFERENCES = {
    "symbols": DEFAULT_SYMBOLS,
    "active_tab": "index",
    "symbol_categories": {},
    "watch_groups": [],
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
        warnings: List[str] = []
        raw_symbols = payload.get("symbols") or DEFAULT_PREFERENCES["symbols"]
        symbols = self._normalize_symbols(raw_symbols)
        if len(symbols) > MAX_SUBSCRIBED_SYMBOLS:
            warnings.append(
                f"symbols truncated from {len(symbols)} to {MAX_SUBSCRIBED_SYMBOLS}"
            )
            symbols = symbols[:MAX_SUBSCRIBED_SYMBOLS]
        active_tab = payload.get("active_tab") or DEFAULT_PREFERENCES["active_tab"]
        raw_categories = payload.get("symbol_categories") or {}
        raw_watch_groups = payload.get("watch_groups") or []
        if active_tab not in VALID_TABS:
            warnings.append(
                f"invalid active_tab '{active_tab}', reset to '{DEFAULT_PREFERENCES['active_tab']}'"
            )
            active_tab = DEFAULT_PREFERENCES["active_tab"]

        symbol_categories: Dict[str, str] = {}
        if isinstance(raw_categories, dict):
            for raw_symbol, raw_category in raw_categories.items():
                if not isinstance(raw_symbol, str) or not isinstance(raw_category, str):
                    continue
                symbol = raw_symbol.strip().upper()
                category = raw_category.strip()
                if symbol and category in VALID_TABS:
                    symbol_categories[symbol] = category
                elif symbol:
                    warnings.append(
                        f"symbol_categories['{symbol}']: skipped (invalid category '{category}')"
                    )

        watch_groups: List[Dict[str, Any]] = []
        if isinstance(raw_watch_groups, list):
            if len(raw_watch_groups) > MAX_WATCH_GROUPS:
                warnings.append(
                    f"watch_groups truncated from {len(raw_watch_groups)} to {MAX_WATCH_GROUPS}"
                )
            for raw_group in raw_watch_groups[:MAX_WATCH_GROUPS]:
                if not isinstance(raw_group, dict):
                    continue
                name = str(raw_group.get("name") or "").strip()
                if not name:
                    warnings.append("watch_groups: skipped a group with empty name")
                    continue
                group_symbols = self._normalize_symbols(raw_group.get("symbols") or [])
                if len(group_symbols) > MAX_SYMBOLS_PER_WATCH_GROUP:
                    warnings.append(
                        f"watch_groups['{name}']: symbols truncated from {len(group_symbols)} to {MAX_SYMBOLS_PER_WATCH_GROUP}"
                    )
                    group_symbols = group_symbols[:MAX_SYMBOLS_PER_WATCH_GROUP]
                raw_weights = raw_group.get("weights") or {}
                weights: Dict[str, float] = {}
                if isinstance(raw_weights, dict):
                    for raw_symbol, raw_weight in raw_weights.items():
                        symbol = str(raw_symbol or "").strip().upper()
                        if symbol not in group_symbols:
                            continue
                        try:
                            numeric_weight = float(raw_weight)
                        except (TypeError, ValueError):
                            continue
                        if numeric_weight == numeric_weight:
                            weights[symbol] = numeric_weight
                try:
                    capital = float(raw_group.get("capital") or 0.0)
                except (TypeError, ValueError):
                    capital = 0.0
                watch_groups.append({
                    "id": str(raw_group.get("id") or f"group-{len(watch_groups)+1}"),
                    "name": name,
                    "symbols": group_symbols,
                    "notes": str(raw_group.get("notes") or "").strip(),
                    "capital": max(capital, 0.0),
                    "weights": weights,
                })

        return {
            "symbols": symbols or list(DEFAULT_PREFERENCES["symbols"]),
            "active_tab": active_tab,
            "symbol_categories": symbol_categories,
            "watch_groups": watch_groups,
            "_warnings": warnings,
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
                "symbol_categories": dict(preferences.get("symbol_categories") or {}),
                "watch_groups": list(preferences.get("watch_groups") or []),
            }

    def update_preferences(self, payload: Dict[str, Any], profile_id: str | None = None) -> Dict[str, Any]:
        with self._lock:
            preferences = self._normalize_preferences(payload)
            warnings = preferences.pop("_warnings", [])
            self._persist(profile_id, preferences)
            result = self.get_preferences(profile_id)
            if warnings:
                result["_warnings"] = warnings
            return result


realtime_preferences_store = RealtimePreferencesStore()
