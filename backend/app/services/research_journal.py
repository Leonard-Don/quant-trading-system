"""Unified research journal persistence for the public quant workflow."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.utils.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

MAX_RESEARCH_JOURNAL_ENTRIES = 180
MAX_RESEARCH_JOURNAL_TAGS = 8
MAX_RESEARCH_JOURNAL_NOTE_CHARS = 1200
MAX_RESEARCH_JOURNAL_SOURCE_BYTES = 512 * 1024

ENTRY_TYPES = {
    "backtest",
    "realtime_review",
    "realtime_alert",
    "realtime_event",
    "industry_watch",
    "industry_alert",
    "manual",
    "trade_plan",
}
ENTRY_STATUSES = {"open", "watching", "done", "archived"}
ENTRY_PRIORITIES = {"high", "medium", "low"}
PRIORITY_SCORE = {"high": 0, "medium": 1, "low": 2}
STATUS_SCORE = {"open": 0, "watching": 1, "done": 2, "archived": 3}

DEFAULT_RESEARCH_JOURNAL = {
    "entries": [],
    "source_state": {},
    "generated_at": None,
    "updated_at": None,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_text(value: Any, max_chars: int = 240) -> str:
    text = str(value or "").strip()
    return text[:max_chars]


def _safe_iso(value: Any, fallback: str) -> str:
    text = _safe_text(value, 80)
    if not text:
        return fallback
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
        return text
    except ValueError:
        return fallback


def _stable_entry_id(entry: dict[str, Any], index: int = 0) -> str:
    raw_id = _safe_text(entry.get("id"), 180)
    if raw_id:
        return raw_id
    seed = "|".join(
        [
            _safe_text(entry.get("type"), 40),
            _safe_text(entry.get("source"), 80),
            _safe_text(entry.get("symbol"), 40),
            _safe_text(entry.get("industry"), 80),
            _safe_text(entry.get("title"), 120),
            _safe_text(entry.get("created_at") or entry.get("createdAt"), 80),
            str(index),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"research_{digest}"


def _coerce_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _coerce_tags(value: Any) -> list[str]:
    tags: list[str] = []
    seen = set()
    if not isinstance(value, list):
        return tags
    for item in value:
        tag = _safe_text(item, 40)
        if not tag or tag in seen:
            continue
        tags.append(tag)
        seen.add(tag)
        if len(tags) >= MAX_RESEARCH_JOURNAL_TAGS:
            break
    return tags


class ResearchJournalStore:
    """File-backed research journal store keyed by browser/profile id."""

    def __init__(self, storage_path: str | Path | None = None):
        if storage_path is None:
            storage_path = PROJECT_ROOT / "data" / "research_journal"
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
        return self.storage_path / f"{self._normalize_profile_id(profile_id)}.json"

    def _normalize_entry(self, raw_entry: dict[str, Any], index: int = 0) -> dict[str, Any] | None:
        if not isinstance(raw_entry, dict):
            return None
        now = _utc_now()
        entry_type = _safe_text(raw_entry.get("type"), 40) or "manual"
        if entry_type not in ENTRY_TYPES:
            entry_type = "manual"
        status = _safe_text(raw_entry.get("status"), 40) or "open"
        if status not in ENTRY_STATUSES:
            status = "open"
        priority = _safe_text(raw_entry.get("priority"), 40) or "medium"
        if priority not in ENTRY_PRIORITIES:
            priority = "medium"

        symbol = _safe_text(raw_entry.get("symbol"), 40).upper()
        industry = _safe_text(raw_entry.get("industry") or raw_entry.get("industry_name"), 120)
        title = _safe_text(raw_entry.get("title"), 180)
        if not title:
            title = symbol or industry or "研究记录"

        created_at = _safe_iso(raw_entry.get("created_at") or raw_entry.get("createdAt"), now)
        updated_at = _safe_iso(raw_entry.get("updated_at") or raw_entry.get("updatedAt"), created_at)

        entry = {
            "id": _stable_entry_id(raw_entry, index),
            "type": entry_type,
            "status": status,
            "priority": priority,
            "title": title,
            "summary": _safe_text(raw_entry.get("summary"), 360),
            "note": _safe_text(raw_entry.get("note"), MAX_RESEARCH_JOURNAL_NOTE_CHARS),
            "symbol": symbol,
            "industry": industry,
            "source": _safe_text(raw_entry.get("source"), 80) or entry_type,
            "source_label": _safe_text(raw_entry.get("source_label") or raw_entry.get("sourceLabel"), 80),
            "created_at": created_at,
            "updated_at": updated_at,
            "tags": _coerce_tags(raw_entry.get("tags")),
            "metrics": _coerce_mapping(raw_entry.get("metrics")),
            "action": _coerce_mapping(raw_entry.get("action")),
            "raw": _coerce_mapping(raw_entry.get("raw")),
        }
        return entry

    def _normalize_entries(self, entries: Any) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        raw_entries = entries if isinstance(entries, list) else []
        for index, raw_entry in enumerate(raw_entries):
            normalized = self._normalize_entry(raw_entry, index=index)
            if not normalized:
                continue
            existing = deduped.get(normalized["id"])
            if not existing or normalized["updated_at"] >= existing["updated_at"]:
                deduped[normalized["id"]] = normalized
        return sorted(
            deduped.values(),
            key=lambda entry: (
                STATUS_SCORE.get(entry["status"], 9),
                PRIORITY_SCORE.get(entry["priority"], 9),
                entry.get("updated_at") or "",
            ),
            reverse=False,
        )[:MAX_RESEARCH_JOURNAL_ENTRIES]

    def _normalize_source_state(self, source_state: Any) -> dict[str, Any]:
        if not isinstance(source_state, dict):
            return {}
        normalized = deepcopy(source_state)
        serialized = json.dumps(normalized, ensure_ascii=False, default=str)
        encoded = serialized.encode("utf-8")
        if len(encoded) <= MAX_RESEARCH_JOURNAL_SOURCE_BYTES:
            return normalized
        return {
            "truncated": True,
            "original_size_bytes": len(encoded),
            "message": "source_state too large; compacted by research journal store",
        }

    def _normalize_payload(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict(payload or {})
        updated_at = _utc_now()
        generated_at = _safe_iso(payload.get("generated_at") or payload.get("generatedAt"), updated_at)
        return {
            "entries": self._normalize_entries(payload.get("entries")),
            "source_state": self._normalize_source_state(payload.get("source_state")),
            "generated_at": generated_at,
            "updated_at": updated_at,
        }

    def _load_journal(self, profile_id: str | None) -> dict[str, Any]:
        journal_file = self._get_journal_file(profile_id)
        try:
            if journal_file.exists():
                with open(journal_file, encoding="utf-8") as file:
                    return self._normalize_payload(json.load(file))
        except Exception as exc:
            logger.warning("Failed to load research journal for %s: %s", profile_id, exc)
        return deepcopy(DEFAULT_RESEARCH_JOURNAL)

    def _persist(self, profile_id: str | None, payload: dict[str, Any]) -> None:
        journal_file = self._get_journal_file(profile_id)
        try:
            with open(journal_file, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error("Failed to persist research journal for %s: %s", profile_id, exc)

    def _build_summary(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        type_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        symbol_counts: dict[str, int] = {}
        industry_counts: dict[str, int] = {}

        for entry in entries:
            type_counts[entry["type"]] = type_counts.get(entry["type"], 0) + 1
            status_counts[entry["status"]] = status_counts.get(entry["status"], 0) + 1
            if entry.get("symbol"):
                symbol_counts[entry["symbol"]] = symbol_counts.get(entry["symbol"], 0) + 1
            if entry.get("industry"):
                industry_counts[entry["industry"]] = industry_counts.get(entry["industry"], 0) + 1

        actionable = [
            entry for entry in entries
            if entry.get("status") in {"open", "watching"} and entry.get("type") != "manual"
        ]
        actionable = sorted(
            actionable,
            key=lambda entry: (
                PRIORITY_SCORE.get(entry.get("priority"), 9),
                entry.get("updated_at") or "",
            ),
            reverse=False,
        )

        symbol_timeline = []
        for symbol, count in sorted(symbol_counts.items(), key=lambda item: (-item[1], item[0]))[:8]:
            symbol_entries = [
                entry for entry in entries if entry.get("symbol") == symbol
            ][:6]
            symbol_timeline.append({
                "symbol": symbol,
                "count": count,
                "entries": symbol_entries,
            })

        next_actions = []
        high_alerts = [
            entry for entry in actionable
            if entry.get("priority") == "high" and entry.get("type") in {"realtime_alert", "industry_alert"}
        ]
        if high_alerts:
            next_actions.append({
                "key": "review_high_alerts",
                "title": "先处理高优先级提醒",
                "description": f"当前有 {len(high_alerts)} 条高优先级提醒，适合优先确认是否需要升级为回测或交易计划。",
                "entry_ids": [entry["id"] for entry in high_alerts[:5]],
            })

        backtest_open = [entry for entry in actionable if entry.get("type") == "backtest"]
        if backtest_open:
            next_actions.append({
                "key": "review_backtests",
                "title": "复核最新回测结论",
                "description": f"已有 {len(backtest_open)} 条回测快照等待沉淀，可以先检查收益、回撤和交易次数是否支持继续跟踪。",
                "entry_ids": [entry["id"] for entry in backtest_open[:5]],
            })

        industry_watch = [entry for entry in actionable if entry.get("type") == "industry_watch"]
        if industry_watch:
            next_actions.append({
                "key": "follow_industries",
                "title": "跟进行业观察名单",
                "description": f"观察列表里有 {len(industry_watch)} 个行业，可以从最近异动或龙头股继续筛选标的。",
                "entry_ids": [entry["id"] for entry in industry_watch[:5]],
            })

        if not next_actions:
            next_actions.append({
                "key": "collect_first_signal",
                "title": "先收集一条可复核线索",
                "description": "当前没有强制处理项，可以先从行业热度或实时行情里挑一条线索保存到研究档案。",
                "entry_ids": [],
            })

        return {
            "total_entries": len(entries),
            "open_entries": status_counts.get("open", 0) + status_counts.get("watching", 0),
            "type_counts": type_counts,
            "status_counts": status_counts,
            "top_symbols": [
                {"symbol": symbol, "count": count}
                for symbol, count in sorted(symbol_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
            ],
            "top_industries": [
                {"industry": industry, "count": count}
                for industry, count in sorted(industry_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
            ],
            "action_queue": actionable[:12],
            "symbol_timeline": symbol_timeline,
            "next_actions": next_actions[:4],
        }

    def _with_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        entries = list(payload.get("entries") or [])
        result = {
            "entries": entries,
            "source_state": deepcopy(payload.get("source_state") or {}),
            "generated_at": payload.get("generated_at"),
            "updated_at": payload.get("updated_at"),
            "summary": self._build_summary(entries),
        }
        return result

    def get_snapshot(self, profile_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            return self._with_summary(self._load_journal(profile_id))

    def update_snapshot(self, payload: dict[str, Any], profile_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            normalized = self._normalize_payload(payload)
            self._persist(profile_id, normalized)
            return self._with_summary(normalized)

    def add_entry(self, entry: dict[str, Any], profile_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            current = self._load_journal(profile_id)
            normalized_entry = self._normalize_entry(entry, index=len(current.get("entries") or []))
            if normalized_entry is None:
                raise ValueError("entry must be an object")
            entries = [normalized_entry, *(current.get("entries") or [])]
            updated = {
                **current,
                "entries": self._normalize_entries(entries),
                "updated_at": _utc_now(),
            }
            self._persist(profile_id, updated)
            return self._with_summary(updated)

    def update_entry_status(self, entry_id: str, status: str, profile_id: str | None = None) -> dict[str, Any]:
        normalized_status = _safe_text(status, 40)
        if normalized_status not in ENTRY_STATUSES:
            raise ValueError(f"invalid status '{status}'")
        with self._lock:
            current = self._load_journal(profile_id)
            matched = False
            updated_entries = []
            for entry in current.get("entries") or []:
                if entry.get("id") == entry_id:
                    entry = {**entry, "status": normalized_status, "updated_at": _utc_now()}
                    matched = True
                updated_entries.append(entry)
            if not matched:
                raise KeyError(entry_id)
            updated = {
                **current,
                "entries": self._normalize_entries(updated_entries),
                "updated_at": _utc_now(),
            }
            self._persist(profile_id, updated)
            return self._with_summary(updated)


research_journal_store = ResearchJournalStore()
