"""Research workbench task persistence."""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

VALID_STATUSES = {"new", "in_progress", "blocked", "complete", "archived"}
VALID_TYPES = {"pricing", "cross_market", "macro_mispricing", "trade_thesis"}
REFRESH_PRIORITY_CHANGE_LABELS = {
    "new": "首次记录",
    "escalated": "升级",
    "relaxed": "缓和",
    "updated": "更新",
}


class ResearchWorkbenchStore:
    """File-backed storage for research tasks."""

    def __init__(
        self,
        storage_path: str | Path | None = None,
        max_records: int = 200,
        persist_immediately: bool = True,
        persist_debounce_ms: int = 200,
    ):
        if storage_path is None:
            storage_path = PROJECT_ROOT / "data" / "research_workbench"

        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.tasks_file = self.storage_path / "tasks.json"
        self.db_file = self.storage_path / "tasks.sqlite3"
        self.max_records = max_records
        self.persist_immediately = persist_immediately
        self._persist_debounce_seconds = max(persist_debounce_ms, 0) / 1000
        self.tasks: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        self._persist_dirty = False
        self._persist_timer: Optional[threading.Timer] = None
        self._dirty_task_ids: set[str] = set()
        self._deleted_task_ids: set[str] = set()
        self._load_tasks()
        self._backfill_board_orders()
        atexit.register(self.flush)

        logger.info("ResearchWorkbenchStore initialized with %s tasks", len(self.tasks))

    def _connect_db(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_file, check_same_thread=False)

    def _init_db(self) -> None:
        with self._connect_db() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_tasks (
                    id TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    board_order INTEGER NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_research_tasks_updated_at ON research_tasks(updated_at DESC)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_research_tasks_status ON research_tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_research_tasks_type ON research_tasks(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_research_tasks_source ON research_tasks(source)")
            conn.commit()

    def _load_tasks(self) -> None:
        self._init_db()
        try:
            with self._connect_db() as conn:
                rows = conn.execute(
                    "SELECT payload FROM research_tasks ORDER BY updated_at DESC"
                ).fetchall()
            if rows:
                self.tasks = [self._normalize_record(json.loads(row[0])) for row in rows]
                return
        except Exception as exc:
            logger.warning("Failed to load research workbench tasks from sqlite: %s", exc)
            self.tasks = []

        try:
            if self.tasks_file.exists():
                with open(self.tasks_file, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    self.tasks = data if isinstance(data, list) else []
                    self.tasks = [self._normalize_record(task) for task in self.tasks]
                    self._dirty_task_ids = {task["id"] for task in self.tasks if task.get("id")}
                    self._persist(force=True)
                    return
        except Exception as exc:
            logger.warning("Failed to load research workbench tasks from legacy json: %s", exc)
            self.tasks = []

    def _persist_to_disk(self) -> None:
        try:
            task_lookup = {task.get("id"): task for task in self.tasks if task.get("id")}
            with self._connect_db() as conn:
                if self._deleted_task_ids:
                    conn.executemany(
                        "DELETE FROM research_tasks WHERE id = ?",
                        [(task_id,) for task_id in self._deleted_task_ids],
                    )
                for task_id in self._dirty_task_ids:
                    task = task_lookup.get(task_id)
                    if not task:
                        continue
                    conn.execute(
                        """
                        INSERT INTO research_tasks (
                            id,
                            updated_at,
                            created_at,
                            status,
                            type,
                            source,
                            board_order,
                            payload
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            updated_at = excluded.updated_at,
                            created_at = excluded.created_at,
                            status = excluded.status,
                            type = excluded.type,
                            source = excluded.source,
                            board_order = excluded.board_order,
                            payload = excluded.payload
                        """,
                        (
                            task["id"],
                            task.get("updated_at") or "",
                            task.get("created_at") or "",
                            task.get("status") or "new",
                            task.get("type") or "pricing",
                            task.get("source") or "",
                            int(task.get("board_order") or 0),
                            json.dumps(task, ensure_ascii=False, default=str),
                        ),
                    )
                conn.commit()
            self._dirty_task_ids.clear()
            self._deleted_task_ids.clear()
        except Exception as exc:
            logger.error("Failed to persist research workbench tasks: %s", exc)

    def _cancel_persist_timer_locked(self) -> None:
        if self._persist_timer:
            self._persist_timer.cancel()
            self._persist_timer = None

    def _flush_locked(self) -> None:
        self._cancel_persist_timer_locked()
        if not self._persist_dirty:
            return
        self._persist_to_disk()
        self._persist_dirty = False

    def _persist(self, force: bool = False) -> None:
        with self._lock:
            self._persist_dirty = True
            if force or self.persist_immediately or self._persist_debounce_seconds <= 0:
                self._flush_locked()
                return

            self._cancel_persist_timer_locked()
            timer = threading.Timer(self._persist_debounce_seconds, self.flush)
            timer.daemon = True
            self._persist_timer = timer
            timer.start()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def close(self) -> None:
        self.flush()

    def _generate_id(self, payload: Dict[str, Any]) -> str:
        seed = f"{payload.get('type', '')}_{payload.get('symbol', '')}_{payload.get('template', '')}_{datetime.now().isoformat()}"
        return f"rw_{hashlib.md5(seed.encode()).hexdigest()[:12]}"

    def _generate_entity_id(self, prefix: str, seed: str) -> str:
        digest = hashlib.md5(f"{prefix}_{seed}_{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        return f"{prefix}_{digest}"

    def _now(self) -> str:
        return datetime.now().isoformat()

    def _normalize_snapshot(self, snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        snapshot = dict(snapshot or {})
        snapshot["headline"] = snapshot.get("headline", "")
        snapshot["summary"] = snapshot.get("summary", "")
        snapshot["highlights"] = snapshot.get("highlights") or []
        snapshot["payload"] = snapshot.get("payload") or {}
        snapshot["saved_at"] = snapshot.get("saved_at") or ""
        return snapshot

    def _normalize_comment(self, comment: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(comment or {})
        normalized["id"] = normalized.get("id") or self._generate_entity_id("comment", normalized.get("body", ""))
        normalized["created_at"] = normalized.get("created_at") or self._now()
        normalized["author"] = normalized.get("author") or "local"
        normalized["body"] = normalized.get("body", "")
        return normalized

    def _normalize_timeline_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(event or {})
        normalized["id"] = normalized.get("id") or self._generate_entity_id("event", normalized.get("label", ""))
        normalized["created_at"] = normalized.get("created_at") or self._now()
        normalized["type"] = normalized.get("type", "metadata_updated")
        normalized["label"] = normalized.get("label", "任务更新")
        normalized["detail"] = normalized.get("detail", "")
        normalized["meta"] = normalized.get("meta") or {}
        return normalized

    def _build_event(
        self,
        event_type: str,
        label: str,
        detail: str = "",
        meta: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._normalize_timeline_event(
            {
                "id": self._generate_entity_id("event", f"{event_type}_{label}"),
                "created_at": created_at or self._now(),
                "type": event_type,
                "label": label,
                "detail": detail,
                "meta": meta or {},
            }
        )

    def _build_refresh_priority_event(
        self,
        task: Optional[Dict[str, Any]],
        priority_event: Optional[Dict[str, Any]],
        created_at: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not priority_event:
            return None

        payload = dict(priority_event or {})
        reason_label = str(payload.get("reason_label") or "").strip() or "自动排序"
        lead = str(payload.get("lead") or "").strip()
        detail = str(payload.get("detail") or "").strip()
        event_detail = "；".join(part for part in [lead, detail] if part)
        meta = {
            "priority_reason": payload.get("reason_key") or "",
            "reason_label": reason_label,
            "severity": payload.get("severity") or "",
            "lead": lead,
            "detail": detail,
            "urgency_score": payload.get("urgency_score"),
            "priority_weight": payload.get("priority_weight"),
            "recommendation": payload.get("recommendation") or "",
            "summary": payload.get("summary") or "",
            "synthetic": False,
        }
        compact_meta = {
            key: value
            for key, value in meta.items()
            if value not in ("", None, [], {})
        }
        change_meta = self._build_refresh_priority_change_meta(task, payload)
        compact_meta.update(change_meta)
        change_type = compact_meta.get("change_type") or "new"
        label_prefix = "系统自动重排"
        if change_type == "escalated":
            label_prefix = "系统自动重排升级"
        elif change_type == "relaxed":
            label_prefix = "系统自动重排缓和"
        elif change_type == "updated":
            label_prefix = "系统自动重排更新"
        compact_meta = {
            key: value
            for key, value in compact_meta.items()
            if value not in ("", None, [], {})
        }
        return self._build_event(
            "refresh_priority",
            f"{label_prefix}：{reason_label}",
            event_detail,
            compact_meta,
            created_at=created_at,
        )

    def _refresh_priority_signature_from_payload(
        self,
        priority_event: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not priority_event:
            return None

        payload = dict(priority_event or {})
        return {
            "priority_reason": str(payload.get("reason_key") or "").strip(),
            "reason_label": str(payload.get("reason_label") or "").strip() or "自动排序",
            "severity": str(payload.get("severity") or "").strip(),
            "lead": str(payload.get("lead") or "").strip(),
            "detail": str(payload.get("detail") or "").strip(),
            "urgency_score": payload.get("urgency_score"),
            "priority_weight": payload.get("priority_weight"),
            "recommendation": str(payload.get("recommendation") or "").strip(),
            "summary": str(payload.get("summary") or "").strip(),
        }

    def _refresh_priority_signature_from_event(
        self,
        event: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not event or event.get("type") != "refresh_priority":
            return None

        meta = event.get("meta") or {}
        return {
            "priority_reason": str(meta.get("priority_reason") or "").strip(),
            "reason_label": str(meta.get("reason_label") or "").strip() or "自动排序",
            "severity": str(meta.get("severity") or "").strip(),
            "lead": str(meta.get("lead") or "").strip(),
            "detail": str(meta.get("detail") or "").strip(),
            "urgency_score": meta.get("urgency_score"),
            "priority_weight": meta.get("priority_weight"),
            "recommendation": str(meta.get("recommendation") or "").strip(),
            "summary": str(meta.get("summary") or "").strip(),
        }

    def _has_duplicate_refresh_priority_event(
        self,
        task: Optional[Dict[str, Any]],
        priority_event: Optional[Dict[str, Any]],
    ) -> bool:
        next_signature = self._refresh_priority_signature_from_payload(priority_event)
        if not next_signature or not task:
            return False

        latest_refresh_priority_event = next(
            (event for event in (task.get("timeline") or []) if event.get("type") == "refresh_priority"),
            None,
        )
        latest_signature = self._refresh_priority_signature_from_event(latest_refresh_priority_event)
        return bool(latest_signature and latest_signature == next_signature)

    def _severity_rank(self, value: Any) -> int:
        return {
            "low": 1,
            "medium": 2,
            "high": 3,
        }.get(str(value or "").strip(), 0)

    def _build_refresh_priority_change_meta(
        self,
        task: Optional[Dict[str, Any]],
        priority_event: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        current_signature = self._refresh_priority_signature_from_payload(priority_event)
        if not current_signature:
            return {}

        latest_refresh_priority_event = next(
            (event for event in (task or {}).get("timeline", []) if event.get("type") == "refresh_priority"),
            None,
        )
        previous_signature = self._refresh_priority_signature_from_event(latest_refresh_priority_event)
        if not previous_signature:
            return {
                "change_type": "new",
                "change_label": REFRESH_PRIORITY_CHANGE_LABELS["new"],
            }

        urgency_score = current_signature.get("urgency_score")
        previous_urgency_score = previous_signature.get("urgency_score")
        urgency_delta = None
        if urgency_score is not None and previous_urgency_score is not None:
            urgency_delta = float(urgency_score) - float(previous_urgency_score)

        priority_weight = current_signature.get("priority_weight")
        previous_priority_weight = previous_signature.get("priority_weight")
        priority_weight_delta = None
        if priority_weight is not None and previous_priority_weight is not None:
            priority_weight_delta = float(priority_weight) - float(previous_priority_weight)

        severity_delta = (
            self._severity_rank(current_signature.get("severity"))
            - self._severity_rank(previous_signature.get("severity"))
        )
        reason_changed = current_signature.get("priority_reason") != previous_signature.get("priority_reason")

        if severity_delta > 0 or (urgency_delta is not None and urgency_delta > 0.25) or (
            priority_weight_delta is not None and priority_weight_delta > 0.25
        ):
            change_type = "escalated"
        elif severity_delta < 0 or (urgency_delta is not None and urgency_delta < -0.25) or (
            priority_weight_delta is not None and priority_weight_delta < -0.25
        ):
            change_type = "relaxed"
        else:
            change_type = "updated"

        return {
            "change_type": change_type,
            "change_label": REFRESH_PRIORITY_CHANGE_LABELS[change_type],
            "reason_changed": reason_changed,
            "previous_priority_reason": previous_signature.get("priority_reason") or "",
            "previous_reason_label": previous_signature.get("reason_label") or "",
            "previous_severity": previous_signature.get("severity") or "",
            "urgency_delta": urgency_delta,
            "priority_weight_delta": priority_weight_delta,
            "severity_delta": severity_delta,
        }

    def _normalize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(record)
        normalized["status"] = normalized.get("status", "new")
        normalized["type"] = normalized.get("type", "pricing")
        normalized["title"] = normalized.get("title", "Untitled Research Task")
        normalized["source"] = normalized.get("source", "")
        normalized["symbol"] = normalized.get("symbol", "")
        normalized["template"] = normalized.get("template", "")
        normalized["note"] = normalized.get("note", "")
        normalized["board_order"] = (
            int(normalized.get("board_order"))
            if normalized.get("board_order") is not None
            else None
        )
        normalized["context"] = normalized.get("context") or {}
        normalized["snapshot"] = self._normalize_snapshot(normalized.get("snapshot"))
        normalized["comments"] = [
            self._normalize_comment(comment) for comment in (normalized.get("comments") or [])
        ]
        normalized["timeline"] = [
            self._normalize_timeline_event(event) for event in (normalized.get("timeline") or [])
        ]
        normalized["snapshot_history"] = [
            self._normalize_snapshot(snapshot) for snapshot in (normalized.get("snapshot_history") or [])
        ]
        normalized["created_at"] = normalized.get("created_at") or datetime.now().isoformat()
        normalized["updated_at"] = normalized.get("updated_at") or normalized["created_at"]
        return normalized

    def _next_board_order(self, status: str) -> int:
        same_status = [int(task.get("board_order") or 0) for task in self.tasks if task.get("status") == status]
        return max(same_status, default=-1) + 1

    def _resequence_status(self, status: str) -> None:
        status_tasks = sorted(
            [task for task in self.tasks if task.get("status") == status],
            key=lambda item: (int(item.get("board_order") or 0), item.get("updated_at", "")),
        )
        for index, task in enumerate(status_tasks):
            task["board_order"] = index

    def _backfill_board_orders(self) -> None:
        changed = False
        for status in VALID_STATUSES:
            status_tasks = sorted(
                [task for task in self.tasks if task.get("status") == status],
                key=lambda item: item.get("updated_at", ""),
                reverse=True,
            )
            for index, task in enumerate(status_tasks):
                if "board_order" not in task or task.get("board_order") is None:
                    task["board_order"] = index
                    changed = True
        if changed:
            self._dirty_task_ids.update(task["id"] for task in self.tasks if task.get("id"))
            self._persist(force=True)

    def _append_snapshot_history(
        self,
        task: Dict[str, Any],
        snapshot: Dict[str, Any],
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        saved_at = timestamp or self._now()
        normalized_snapshot = self._normalize_snapshot({**snapshot, "saved_at": snapshot.get("saved_at") or saved_at})
        history = [normalized_snapshot] + [
            existing
            for existing in (task.get("snapshot_history") or [])
            if existing.get("saved_at") != normalized_snapshot.get("saved_at")
            or existing.get("headline") != normalized_snapshot.get("headline")
        ]
        task["snapshot"] = normalized_snapshot
        task["snapshot_history"] = history
        return normalized_snapshot

    def _extract_snapshot_view_context(self, snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = (snapshot or {}).get("payload") or {}
        view_context = payload.get("view_context") or payload.get("workbench_view_context") or {}
        return view_context if isinstance(view_context, dict) else {}

    def _build_snapshot_saved_detail(self, snapshot: Optional[Dict[str, Any]], fallback: str) -> str:
        detail = str((snapshot or {}).get("headline") or fallback or "").strip() or fallback
        view_context = self._extract_snapshot_view_context(snapshot)
        summary = str(view_context.get("summary") or "").strip()
        if summary:
            return f"{detail} · 视图 {summary}"
        return detail

    def _build_snapshot_saved_meta(self, snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        view_context = self._extract_snapshot_view_context(snapshot)
        return {
            "saved_at": (snapshot or {}).get("saved_at"),
            "view_context_summary": str(view_context.get("summary") or "").strip(),
            "view_context_fingerprint": str(view_context.get("view_fingerprint") or "").strip(),
            "view_context_scoped_task_label": str(view_context.get("scoped_task_label") or "").strip(),
            "view_context_note": str(view_context.get("note") or "").strip(),
        }

    def _build_snapshot_view_queue_stats(self, limit: int = 8) -> List[Dict[str, Any]]:
        buckets: Dict[str, Dict[str, Any]] = {}

        for task in self.tasks:
            view_context = self._extract_snapshot_view_context(task.get("snapshot"))
            summary = str(view_context.get("summary") or "").strip()
            fingerprint = str(view_context.get("view_fingerprint") or "").strip()
            bucket_key = fingerprint or summary
            if not bucket_key:
                continue

            current = buckets.get(bucket_key)
            if current is None:
                current = {
                    "value": summary or fingerprint,
                    "label": summary or fingerprint,
                    "fingerprint": fingerprint,
                    "count": 0,
                    "scoped_count": 0,
                    "latest_at": "",
                    "type_counts": {},
                }
                buckets[bucket_key] = current

            current["count"] += 1
            if str(view_context.get("scoped_task_label") or "").strip():
                current["scoped_count"] += 1

            task_type = str(task.get("type") or "").strip() or "unknown"
            type_counts = current["type_counts"]
            type_counts[task_type] = int(type_counts.get(task_type) or 0) + 1

            latest_at = str(
                task.get("snapshot", {}).get("saved_at")
                or task.get("updated_at")
                or task.get("created_at")
                or ""
            )
            if latest_at and latest_at > str(current.get("latest_at") or ""):
                current["latest_at"] = latest_at

        ranked = sorted(
            buckets.values(),
            key=lambda item: (
                int(item.get("count") or 0),
                int(item.get("scoped_count") or 0),
                str(item.get("latest_at") or ""),
            ),
            reverse=True,
        )
        return ranked[:limit]

    def create_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            priority_event = (payload or {}).get("refresh_priority_event")
            base_payload = dict(payload or {})
            base_payload.pop("refresh_priority_event", None)
            task = self._normalize_record(base_payload)
            task["id"] = self._generate_id(payload)
            timestamp = self._now()
            task["created_at"] = timestamp
            task["updated_at"] = timestamp
            task["board_order"] = (
                int(base_payload.get("board_order"))
                if base_payload.get("board_order") is not None
                else self._next_board_order(task["status"])
            )
            task["timeline"] = [
                self._build_event(
                    "created",
                    "任务已创建",
                    f"{task['title']} 已进入研究工作台。",
                    {"status": task["status"], "type": task["type"]},
                    created_at=timestamp,
                )
            ]

            if task["snapshot"].get("headline") or task["snapshot"].get("summary") or task["snapshot"].get("payload"):
                snapshot = self._append_snapshot_history(task, task["snapshot"], timestamp)
                task["timeline"].insert(
                    0,
                    self._build_event(
                        "snapshot_saved",
                        "首个研究快照已保存",
                        self._build_snapshot_saved_detail(snapshot, "研究快照已加入任务。"),
                        self._build_snapshot_saved_meta(snapshot),
                        created_at=timestamp,
                    ),
                )

            refresh_priority_event = self._build_refresh_priority_event(task, priority_event, created_at=timestamp)
            if refresh_priority_event:
                task["timeline"].insert(0, refresh_priority_event)

            self.tasks.insert(0, task)
            if len(self.tasks) > self.max_records:
                dropped = self.tasks[self.max_records :]
                self.tasks = self.tasks[: self.max_records]
                self._deleted_task_ids.update(item["id"] for item in dropped if item.get("id"))
            self._dirty_task_ids.add(task["id"])
            self._persist()
            return dict(task)

    def list_tasks(
        self,
        limit: int = 50,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        view: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            filtered = list(self.tasks)

            if task_type:
                filtered = [task for task in filtered if task.get("type") == task_type]
            if status:
                filtered = [task for task in filtered if task.get("status") == status]
            if source:
                filtered = [task for task in filtered if task.get("source") == source]

            if view == "board":
                filtered.sort(
                    key=lambda item: (
                        item.get("status", ""),
                        int(item.get("board_order") or 0),
                        item.get("updated_at", ""),
                    )
                )
            else:
                filtered.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
            return [dict(task) for task in filtered[:limit]]

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for task in self.tasks:
                if task.get("id") == task_id:
                    return dict(task)
            return None

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            for index, task in enumerate(self.tasks):
                if task.get("id") != task_id:
                    continue

                merged = dict(task)
                timeline_events: List[Dict[str, Any]] = []
                now = self._now()
                refresh_priority_event = None
                if not self._has_duplicate_refresh_priority_event(task, updates.get("refresh_priority_event")):
                    refresh_priority_event = self._build_refresh_priority_event(
                        task,
                        updates.get("refresh_priority_event"),
                        created_at=now,
                    )
                if refresh_priority_event:
                    timeline_events.append(refresh_priority_event)

                if "status" in updates and updates["status"] is not None and updates["status"] != task.get("status"):
                    timeline_events.append(
                        self._build_event(
                            "status_changed",
                            "任务状态已更新",
                            f"{task.get('status', 'new')} -> {updates['status']}",
                            {"from": task.get("status"), "to": updates["status"]},
                            created_at=now,
                        )
                    )

                metadata_changes: List[str] = []
                if "title" in updates and updates["title"] is not None and updates["title"] != task.get("title"):
                    metadata_changes.append("标题")
                if "note" in updates and updates["note"] is not None and updates["note"] != task.get("note"):
                    metadata_changes.append("备注")
                if "context" in updates and updates["context"] is not None and updates["context"] != task.get("context"):
                    metadata_changes.append("上下文")

                same_status_reordered = False
                if (
                    "board_order" in updates
                    and updates["board_order"] is not None
                    and int(updates["board_order"]) != int(task.get("board_order") or 0)
                    and ("status" not in updates or updates.get("status") == task.get("status"))
                ):
                    same_status_reordered = True

                for field in ["status", "title", "note", "context", "snapshot", "board_order"]:
                    if field in updates and updates[field] is not None:
                        merged[field] = updates[field]

                if "status" in updates and updates["status"] is not None and updates["status"] != task.get("status"):
                    destination_status = updates["status"]
                    if destination_status == "archived":
                        merged["board_order"] = int(task.get("board_order") or 0)
                    elif updates.get("board_order") is None:
                        merged["board_order"] = self._next_board_order(destination_status)
                elif "board_order" not in updates or updates["board_order"] is None:
                    merged["board_order"] = int(task.get("board_order") or 0)

                if metadata_changes:
                    timeline_events.append(
                        self._build_event(
                            "metadata_updated",
                            "任务元信息已更新",
                            f"已更新：{'、'.join(metadata_changes)}",
                            {"fields": metadata_changes},
                            created_at=now,
                        )
                    )

                if "snapshot" in updates and updates["snapshot"] is not None:
                    snapshot = self._append_snapshot_history(merged, updates["snapshot"], now)
                    timeline_events.append(
                        self._build_event(
                            "snapshot_saved",
                            "研究快照已更新",
                            self._build_snapshot_saved_detail(snapshot, "新的研究快照已保存。"),
                            self._build_snapshot_saved_meta(snapshot),
                            created_at=now,
                        )
                    )

                if same_status_reordered:
                    timeline_events.append(
                        self._build_event(
                            "board_reordered",
                            "任务顺序已调整",
                            f"当前列内顺序调整为 {int(merged.get('board_order') or 0)}",
                            {"board_order": int(merged.get("board_order") or 0)},
                            created_at=now,
                        )
                    )

                merged["timeline"] = timeline_events + list(task.get("timeline") or [])
                merged["updated_at"] = now
                merged = self._normalize_record(merged)
                self.tasks[index] = merged
                if task.get("status") != merged.get("status"):
                    self._resequence_status(task.get("status", "new"))
                    if merged.get("status") != "archived":
                        self._resequence_status(merged.get("status", "new"))
                else:
                    self._resequence_status(merged.get("status", "new"))
                self.tasks.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
                self._dirty_task_ids.add(merged["id"])
                self._persist()
                return dict(merged)

            return None

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            original_length = len(self.tasks)
            deleted_ids = {task.get("id") for task in self.tasks if task.get("id") == task_id}
            self.tasks = [task for task in self.tasks if task.get("id") != task_id]
            deleted = len(self.tasks) < original_length
            if deleted:
                self._deleted_task_ids.update(task_id for task_id in deleted_ids if task_id)
                self._persist()
            return deleted

    def add_comment(
        self,
        task_id: str,
        body: str,
        author: str = "local",
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            for index, task in enumerate(self.tasks):
                if task.get("id") != task_id:
                    continue

                timestamp = self._now()
                comment = self._normalize_comment(
                    {
                        "id": self._generate_entity_id("comment", body),
                        "created_at": timestamp,
                        "author": author or "local",
                        "body": body,
                    }
                )
                task_comments = [comment] + list(task.get("comments") or [])
                task_timeline = [
                    self._build_event(
                        "comment_added",
                        "新增评论",
                        body,
                        {"comment_id": comment["id"], "author": comment["author"]},
                        created_at=timestamp,
                    )
                ] + list(task.get("timeline") or [])
                updated = dict(task)
                updated["comments"] = task_comments
                updated["timeline"] = task_timeline
                updated["updated_at"] = timestamp
                updated = self._normalize_record(updated)
                self.tasks[index] = updated
                self.tasks.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
                self._dirty_task_ids.add(updated["id"])
                self._persist()
                return dict(comment)

            return None

    def delete_comment(self, task_id: str, comment_id: str) -> bool:
        with self._lock:
            for index, task in enumerate(self.tasks):
                if task.get("id") != task_id:
                    continue

                comments = list(task.get("comments") or [])
                target = next((comment for comment in comments if comment.get("id") == comment_id), None)
                if not target:
                    return False

                updated = dict(task)
                updated["comments"] = [comment for comment in comments if comment.get("id") != comment_id]
                updated["timeline"] = [
                    self._build_event(
                        "comment_deleted",
                        "评论已删除",
                        target.get("body", ""),
                        {"comment_id": comment_id},
                    )
                ] + list(task.get("timeline") or [])
                updated["updated_at"] = self._now()
                updated = self._normalize_record(updated)
                self.tasks[index] = updated
                self.tasks.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
                self._dirty_task_ids.add(updated["id"])
                self._persist()
                return True

            return False

    def add_snapshot(
        self,
        task_id: str,
        snapshot: Dict[str, Any],
        refresh_priority_event: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            for index, task in enumerate(self.tasks):
                if task.get("id") != task_id:
                    continue

                updated = dict(task)
                timestamp = self._now()
                normalized_snapshot = self._append_snapshot_history(updated, snapshot, timestamp)
                timeline_events: List[Dict[str, Any]] = []
                priority_timeline_event = None
                if not self._has_duplicate_refresh_priority_event(task, refresh_priority_event):
                    priority_timeline_event = self._build_refresh_priority_event(
                        task,
                        refresh_priority_event,
                        created_at=timestamp,
                    )
                if priority_timeline_event:
                    timeline_events.append(priority_timeline_event)
                timeline_events.append(
                    self._build_event(
                        "snapshot_saved",
                        "研究快照已更新",
                        self._build_snapshot_saved_detail(normalized_snapshot, "新的研究快照已保存。"),
                        self._build_snapshot_saved_meta(normalized_snapshot),
                        created_at=timestamp,
                    )
                )
                updated["timeline"] = timeline_events + list(task.get("timeline") or [])
                updated["updated_at"] = timestamp
                updated = self._normalize_record(updated)
                self.tasks[index] = updated
                self.tasks.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
                self._dirty_task_ids.add(updated["id"])
                self._persist()
                return dict(updated)

            return None

    def bulk_update_tasks(
        self,
        task_ids: List[str],
        status: Optional[str] = None,
        comment: str = "",
        author: str = "local",
    ) -> List[Dict[str, Any]]:
        with self._lock:
            requested_ids = []
            seen_ids = set()
            for task_id in task_ids or []:
                normalized_id = str(task_id or "").strip()
                if not normalized_id or normalized_id in seen_ids:
                    continue
                requested_ids.append(normalized_id)
                seen_ids.add(normalized_id)

            if not requested_ids:
                return []

            comment_body = str(comment or "").strip()
            next_board_orders = {task_status: self._next_board_order(task_status) for task_status in VALID_STATUSES}
            updated_records: List[Dict[str, Any]] = []

            for index, task in enumerate(self.tasks):
                if task.get("id") not in seen_ids:
                    continue

                updated = dict(task)
                timeline_events: List[Dict[str, Any]] = []
                timestamp = self._now()
                changed = False

                if status and status != task.get("status"):
                    previous_status = task.get("status", "new")
                    updated["status"] = status
                    if status == "archived":
                        updated["board_order"] = int(task.get("board_order") or 0)
                    else:
                        updated["board_order"] = next_board_orders[status]
                        next_board_orders[status] += 1
                    timeline_events.append(
                        self._build_event(
                            "status_changed",
                            "任务状态已更新",
                            f"{previous_status} -> {status}",
                            {"from": previous_status, "to": status},
                            created_at=timestamp,
                        )
                    )
                    changed = True

                if comment_body:
                    task_comment = self._normalize_comment(
                        {
                            "id": self._generate_entity_id("comment", f"{task.get('id', '')}_{comment_body}"),
                            "created_at": timestamp,
                            "author": author or "local",
                            "body": comment_body,
                        }
                    )
                    updated["comments"] = [task_comment] + list(task.get("comments") or [])
                    timeline_events.append(
                        self._build_event(
                            "comment_added",
                            "新增评论",
                            comment_body,
                            {"comment_id": task_comment["id"], "author": task_comment["author"]},
                            created_at=timestamp,
                        )
                    )
                    changed = True

                if not changed:
                    continue

                updated["timeline"] = timeline_events + list(task.get("timeline") or [])
                updated["updated_at"] = timestamp
                updated = self._normalize_record(updated)
                self.tasks[index] = updated
                updated_records.append(dict(updated))

            if not updated_records:
                return []

            for task_status in VALID_STATUSES:
                self._resequence_status(task_status)
            self.tasks.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
            self._dirty_task_ids.update(task["id"] for task in self.tasks if task.get("id"))
            self._persist()
            return updated_records

    def reorder_board(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        with self._lock:
            by_id = {task.get("id"): task for task in self.tasks}
            timestamp = self._now()

            for item in items:
                task = by_id.get(item.get("task_id"))
                if not task:
                    continue
                next_status = item.get("status", task.get("status"))
                next_order = int(item.get("board_order") or 0)
                current_status = task.get("status")
                current_order = int(task.get("board_order") or 0)
                status_changed = next_status != current_status
                order_changed = next_order != current_order
                refresh_priority_event = None
                if not self._has_duplicate_refresh_priority_event(task, item.get("refresh_priority_event")):
                    refresh_priority_event = self._build_refresh_priority_event(
                        task,
                        item.get("refresh_priority_event"),
                        created_at=timestamp,
                    )

                if status_changed:
                    task_timeline = []
                    if refresh_priority_event:
                        task_timeline.append(refresh_priority_event)
                    task_timeline.append(
                        self._build_event(
                            "status_changed",
                            "任务状态已更新",
                            f"{current_status} -> {next_status}",
                            {"from": current_status, "to": next_status},
                            created_at=timestamp,
                        )
                    )
                    task["timeline"] = task_timeline + list(task.get("timeline") or [])
                elif order_changed:
                    task_timeline = []
                    if refresh_priority_event:
                        task_timeline.append(refresh_priority_event)
                    task_timeline.append(
                        self._build_event(
                            "board_reordered",
                            "任务顺序已调整",
                            f"当前列内顺序调整为 {next_order}",
                            {"board_order": next_order},
                            created_at=timestamp,
                        )
                    )
                    task["timeline"] = task_timeline + list(task.get("timeline") or [])

                task["status"] = next_status
                task["board_order"] = next_order
                task["updated_at"] = timestamp

            for status in VALID_STATUSES:
                self._resequence_status(status)
            self.tasks.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
            self._dirty_task_ids.update(task["id"] for task in self.tasks if task.get("id"))
            self._persist()
            return [dict(task) for task in self.tasks]

    def get_timeline(self, task_id: str) -> Optional[List[Dict[str, Any]]]:
        with self._lock:
            task = next((item for item in self.tasks if item.get("id") == task_id), None)
            if not task:
                return None
            timeline = sorted(
                [self._normalize_timeline_event(event) for event in (task.get("timeline") or [])],
                key=lambda item: item.get("created_at", ""),
                reverse=True,
            )
            return [dict(item) for item in timeline]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            status_counts = {status: 0 for status in VALID_STATUSES}
            type_counts = {task_type: 0 for task_type in VALID_TYPES}

            for task in self.tasks:
                status = task.get("status", "new")
                task_type = task.get("type", "pricing")
                status_counts[status] = status_counts.get(status, 0) + 1
                type_counts[task_type] = type_counts.get(task_type, 0) + 1

            return {
                "total": len(self.tasks),
                "status_counts": status_counts,
                "type_counts": type_counts,
                "latest_updated_at": self.tasks[0].get("updated_at") if self.tasks else None,
                "with_timeline": sum(1 for task in self.tasks if task.get("timeline")),
                "snapshot_view_queues": self._build_snapshot_view_queue_stats(),
            }

research_workbench_store = ResearchWorkbenchStore(persist_immediately=False, persist_debounce_ms=200)
