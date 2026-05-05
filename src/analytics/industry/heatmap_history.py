"""Heatmap history file readers (trend aliases + last-N-snapshots lookup).

Lifted out of ``industry_analyzer`` — these are pure file-IO helpers with
their own module-level caches. They do not need ``self``.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from src.utils.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

_TREND_ALIAS_CACHE: Optional[Dict[str, str]] = None
_HEATMAP_HISTORY_TREND_CACHE: Optional[
    Dict[tuple[int | None, int], Dict[str, List[float]]]
] = None
_HEATMAP_HISTORY_TREND_CACHE_MTIME: float = 0.0


def load_trend_aliases() -> Dict[str, str]:
    """Read & cache the canonical industry-name alias map."""
    global _TREND_ALIAS_CACHE
    if _TREND_ALIAS_CACHE is not None:
        return _TREND_ALIAS_CACHE

    alias_file = PROJECT_ROOT / "data" / "industry" / "trend_aliases.json"
    try:
        with open(alias_file, "r", encoding="utf-8") as file:
            payload = json.load(file)
            if isinstance(payload, dict):
                _TREND_ALIAS_CACHE = {
                    str(key).strip(): str(value).strip()
                    for key, value in payload.items()
                    if key and value
                }
                return _TREND_ALIAS_CACHE
    except FileNotFoundError:
        logger.warning("Industry trend alias file not found: %s", alias_file)
    except Exception as exc:
        logger.warning("Failed to load industry trend aliases: %s", exc)

    _TREND_ALIAS_CACHE = {}
    return _TREND_ALIAS_CACHE


def load_heatmap_history_trend_lookup(
    max_points: int = 5,
    preferred_days: Optional[int] = None,
) -> Dict[str, List[float]]:
    """Read recent heatmap snapshots and return ``industry → [score, …]`` series."""
    global _HEATMAP_HISTORY_TREND_CACHE, _HEATMAP_HISTORY_TREND_CACHE_MTIME

    history_file = PROJECT_ROOT / "data" / "industry" / "heatmap_history.json"
    if not history_file.exists():
        return {}

    try:
        current_mtime = history_file.stat().st_mtime
    except OSError:
        return {}

    cache_key = (preferred_days, max_points)
    if (
        _HEATMAP_HISTORY_TREND_CACHE is not None
        and _HEATMAP_HISTORY_TREND_CACHE_MTIME == current_mtime
        and cache_key in _HEATMAP_HISTORY_TREND_CACHE
    ):
        return _HEATMAP_HISTORY_TREND_CACHE[cache_key]

    try:
        payload = json.loads(history_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read heatmap history trend cache: %s", exc)
        return {}

    if not isinstance(payload, list) or not payload:
        return {}

    selected_snapshots = payload
    if preferred_days is not None:
        preferred_matches = [
            item
            for item in payload
            if int(item.get("days") or 0) == int(preferred_days)
        ]
        if len(preferred_matches) >= 2:
            selected_snapshots = preferred_matches

    selected_snapshots = selected_snapshots[-max(max_points, 2):]
    trend_lookup: Dict[str, List[float]] = {}
    for snapshot in selected_snapshots:
        for industry in snapshot.get("industries") or []:
            industry_name = str(industry.get("name") or "").strip()
            if not industry_name:
                continue
            point = industry.get("total_score")
            if point is None:
                point = industry.get("value")
            try:
                numeric_point = float(point)
            except (TypeError, ValueError):
                continue
            trend_lookup.setdefault(industry_name, []).append(round(numeric_point, 3))

    filtered_lookup = {
        industry_name: values
        for industry_name, values in trend_lookup.items()
        if len(values) >= 2
    }

    if (
        _HEATMAP_HISTORY_TREND_CACHE is None
        or _HEATMAP_HISTORY_TREND_CACHE_MTIME != current_mtime
    ):
        _HEATMAP_HISTORY_TREND_CACHE = {}
        _HEATMAP_HISTORY_TREND_CACHE_MTIME = current_mtime
    _HEATMAP_HISTORY_TREND_CACHE[cache_key] = filtered_lookup
    return filtered_lookup


__all__ = ["load_trend_aliases", "load_heatmap_history_trend_lookup"]
