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
        normalized["snapshot"] = normalized.get("snapshot") or {}
        normalized["created_at"] = normalized.get("created_at") or datetime.now().isoformat()
        normalized["updated_at"] = normalized.get("updated_at") or normalized["created_at"]
        return normalized

    def create_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            task = self._normalize_record(payload)
            task["id"] = self._generate_id(payload)
            timestamp = datetime.now().isoformat()
            task["created_at"] = timestamp
            task["updated_at"] = timestamp

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
                for field in ["status", "title", "note", "context", "snapshot"]:
                    if field in updates and updates[field] is not None:
                        merged[field] = updates[field]

                merged["updated_at"] = datetime.now().isoformat()
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
            }


research_workbench_store = ResearchWorkbenchStore()
