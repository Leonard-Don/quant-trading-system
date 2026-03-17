"""Research workbench task persistence."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

VALID_STATUSES = {"new", "in_progress", "blocked", "complete", "archived"}
VALID_TYPES = {"pricing", "cross_market"}


class ResearchWorkbenchStore:
    """File-backed storage for research tasks."""

    def __init__(self, storage_path: str | Path | None = None, max_records: int = 200):
        if storage_path is None:
            storage_path = PROJECT_ROOT / "data" / "research_workbench"

        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.tasks_file = self.storage_path / "tasks.json"
        self.max_records = max_records
        self.tasks: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        self._load_tasks()

        logger.info("ResearchWorkbenchStore initialized with %s tasks", len(self.tasks))

    def _load_tasks(self) -> None:
        try:
            if self.tasks_file.exists():
                with open(self.tasks_file, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    self.tasks = data if isinstance(data, list) else []
        except Exception as exc:
            logger.warning("Failed to load research workbench tasks: %s", exc)
            self.tasks = []

    def _persist(self) -> None:
        try:
            with open(self.tasks_file, "w", encoding="utf-8") as file:
                json.dump(self.tasks, file, ensure_ascii=False, indent=2, default=str)
        except Exception as exc:
            logger.error("Failed to persist research workbench tasks: %s", exc)

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

    def _normalize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(record)
        normalized["status"] = normalized.get("status", "new")
        normalized["type"] = normalized.get("type", "pricing")
        normalized["title"] = normalized.get("title", "Untitled Research Task")
        normalized["source"] = normalized.get("source", "")
        normalized["symbol"] = normalized.get("symbol", "")
        normalized["template"] = normalized.get("template", "")
        normalized["note"] = normalized.get("note", "")
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

    def create_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            task = self._normalize_record(payload)
            task["id"] = self._generate_id(payload)
            timestamp = self._now()
            task["created_at"] = timestamp
            task["updated_at"] = timestamp
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
                        snapshot.get("headline") or "研究快照已加入任务。",
                        {"saved_at": snapshot.get("saved_at")},
                        created_at=timestamp,
                    ),
                )

            self.tasks.insert(0, task)
            if len(self.tasks) > self.max_records:
                self.tasks = self.tasks[: self.max_records]
            self._persist()
            return dict(task)

    def list_tasks(
        self,
        limit: int = 50,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            filtered = list(self.tasks)

            if task_type:
                filtered = [task for task in filtered if task.get("type") == task_type]
            if status:
                filtered = [task for task in filtered if task.get("status") == status]
            if source:
                filtered = [task for task in filtered if task.get("source") == source]

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

                for field in ["status", "title", "note", "context", "snapshot"]:
                    if field in updates and updates[field] is not None:
                        merged[field] = updates[field]

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
                            snapshot.get("headline") or "新的研究快照已保存。",
                            {"saved_at": snapshot.get("saved_at")},
                            created_at=now,
                        )
                    )

                merged["timeline"] = timeline_events + list(task.get("timeline") or [])
                merged["updated_at"] = now
                merged = self._normalize_record(merged)
                self.tasks[index] = merged
                self.tasks.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
                self._persist()
                return dict(merged)

            return None

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            original_length = len(self.tasks)
            self.tasks = [task for task in self.tasks if task.get("id") != task_id]
            deleted = len(self.tasks) < original_length
            if deleted:
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
                self._persist()
                return True

            return False

    def add_snapshot(self, task_id: str, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            for index, task in enumerate(self.tasks):
                if task.get("id") != task_id:
                    continue

                updated = dict(task)
                timestamp = self._now()
                normalized_snapshot = self._append_snapshot_history(updated, snapshot, timestamp)
                updated["timeline"] = [
                    self._build_event(
                        "snapshot_saved",
                        "研究快照已更新",
                        normalized_snapshot.get("headline") or "新的研究快照已保存。",
                        {"saved_at": normalized_snapshot.get("saved_at")},
                        created_at=timestamp,
                    )
                ] + list(task.get("timeline") or [])
                updated["updated_at"] = timestamp
                updated = self._normalize_record(updated)
                self.tasks[index] = updated
                self.tasks.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
                self._persist()
                return dict(updated)

            return None

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
            }


research_workbench_store = ResearchWorkbenchStore()
