"""Async task queue facade with optional Celery + Redis execution."""

from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.app.core.persistence import persistence_manager


TaskHandler = Callable[[Dict[str, Any]], Dict[str, Any]]
TASK_RECORD_TYPE = "infra_task"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKER_PID_FILE = PROJECT_ROOT / "logs" / "celery-worker.pid"
WORKER_LOG_FILE = PROJECT_ROOT / "logs" / "celery-worker.log"


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def _task_record_id(task_id: str) -> str:
    return f"{TASK_RECORD_TYPE}:{task_id}"


def _normalize_broker_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _normalize_broker_payload(item)
            for key, item in list(value.items())[:50]
        }
    if isinstance(value, (list, tuple, set)):
        return [_normalize_broker_payload(item) for item in list(value)[:50]]
    return {
        "type": type(value).__name__,
        "repr": str(value),
    }


def _read_pid_file(path: Path) -> Optional[int]:
    try:
        value = path.read_text(encoding="utf-8").strip()
        return int(value) if value else None
    except Exception:
        return None


def _process_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except Exception:
        return False
    return True


class TaskQueueManager:
    """A job manager with local fallback and optional Celery dispatch."""

    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL")
        self.celery_broker_url = os.getenv("CELERY_BROKER_URL") or self.redis_url
        self.celery_result_backend = os.getenv("CELERY_RESULT_BACKEND") or self.redis_url or self.celery_broker_url
        self.max_workers = max(1, min(int(os.getenv("QUANT_TASK_WORKERS", "2")), 8))
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="quant-task")
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._celery_app = None
        self._celery_import_error = None
        self._celery_task_name = "quant.infrastructure.execute_task"
        self._initialize_celery()

    @property
    def celery_app(self):
        return self._celery_app

    def _initialize_celery(self) -> None:
        if not self.celery_broker_url:
            return
        try:
            from celery import Celery
        except Exception as exc:  # pragma: no cover - optional dependency
            self._celery_import_error = str(exc)
            return
        app = Celery(
            "quant_task_queue",
            broker=self.celery_broker_url,
            backend=self.celery_result_backend,
        )
        app.conf.update(
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            timezone="UTC",
            enable_utc=True,
            task_track_started=True,
        )

        @app.task(name=self._celery_task_name, bind=True)
        def execute_task(celery_task, task_id: str, task_name: str, payload: Dict[str, Any]):  # pragma: no cover - worker path
            manager = task_queue_manager
            manager._attach_runtime_task(
                task_id,
                {
                    "id": task_id,
                    "broker_task_id": getattr(celery_task.request, "id", None),
                    "broker_state": "STARTED",
                    "execution_backend": "celery",
                },
            )
            return manager.run_distributed_task(task_id=task_id, task_name=task_name, payload=payload)

        self._celery_app = app

    def _empty_task_template(self, task_id: str, name: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "id": task_id,
            "name": str(name or "manual_task"),
            "payload": payload or {},
            "status": "queued",
            "created_at": _utcnow_iso(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
            "progress": 0.0,
            "stage": "queued",
            "cancel_requested": False,
            "cancelled_at": None,
            "broker_task_id": None,
            "broker_state": None,
            "execution_backend": "local",
        }

    def _persist_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(task)
        record = persistence_manager.put_record(
            record_type=TASK_RECORD_TYPE,
            record_key=task["id"],
            payload=payload,
            record_id=_task_record_id(task["id"]),
        )
        saved = dict(record.get("payload") or {})
        saved.setdefault("id", task["id"])
        saved.setdefault("created_at", record.get("created_at"))
        saved.setdefault("updated_at", record.get("updated_at"))
        return saved

    def _load_persisted_tasks(self, limit: int = 200) -> List[Dict[str, Any]]:
        records = persistence_manager.list_records(record_type=TASK_RECORD_TYPE, limit=limit)
        tasks = []
        for record in records:
            payload = dict(record.get("payload") or {})
            payload.setdefault("id", record.get("record_key"))
            payload.setdefault("created_at", record.get("created_at"))
            payload.setdefault("updated_at", record.get("updated_at"))
            tasks.append(payload)
        return tasks

    def _load_persisted_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        for task in self._load_persisted_tasks(limit=500):
            if task.get("id") == task_id:
                return task
        return None

    def _attach_runtime_task(self, task_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            base = dict(self._tasks.get(task_id) or self._load_persisted_task(task_id) or {"id": task_id})
            base.update(updates)
            self._tasks[task_id] = base
        saved = self._persist_task(base)
        with self._lock:
            self._tasks[task_id] = saved
            return dict(saved)

    def _sync_celery_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not self._celery_app or task.get("execution_backend") != "celery" or not task.get("broker_task_id"):
            return dict(task)

        checked_at = _utcnow_iso()
        try:
            async_result = self._celery_app.AsyncResult(task["broker_task_id"])
            broker_state = str(async_result.state or "UNKNOWN").upper()
            raw_info = async_result.result if broker_state == "SUCCESS" else async_result.info
        except Exception as exc:  # pragma: no cover - broker / backend variance
            merged = dict(task)
            merged["broker_checked_at"] = checked_at
            merged["broker_poll_error"] = str(exc)
            return merged

        updates: Dict[str, Any] = {"broker_state": broker_state}
        normalized_info = _normalize_broker_payload(raw_info)
        if isinstance(normalized_info, dict):
            if normalized_info.get("stage"):
                updates["stage"] = normalized_info.get("stage")
            try:
                progress = float(normalized_info.get("progress"))
                if progress >= 0:
                    updates["progress"] = min(max(progress, float(task.get("progress") or 0.0)), 1.0)
            except Exception:
                pass

        current_status = str(task.get("status") or "queued")
        if broker_state in {"PENDING", "RECEIVED"} and current_status == "queued":
            updates.setdefault("stage", "broker_pending")
        elif broker_state in {"STARTED", "RETRY"}:
            updates.update(
                {
                    "status": "running",
                    "started_at": task.get("started_at") or checked_at,
                    "stage": updates.get("stage") or ("broker_retry" if broker_state == "RETRY" else "worker_started"),
                    "progress": max(float(updates.get("progress") or task.get("progress") or 0.0), 0.1),
                    "error": None,
                }
            )
        elif broker_state == "SUCCESS":
            updates.update(
                {
                    "status": "completed",
                    "finished_at": task.get("finished_at") or checked_at,
                    "stage": "completed",
                    "progress": 1.0,
                    "error": None,
                    "result": normalized_info,
                }
            )
        elif broker_state == "FAILURE":
            updates.update(
                {
                    "status": "failed",
                    "finished_at": task.get("finished_at") or checked_at,
                    "stage": "failed",
                    "error": str(raw_info or "Broker task failed"),
                    "result": normalized_info,
                }
            )
        elif broker_state == "REVOKED":
            updates.update(
                {
                    "status": "cancelled",
                    "finished_at": task.get("finished_at") or checked_at,
                    "cancelled_at": task.get("cancelled_at") or checked_at,
                    "stage": "cancelled",
                    "result": normalized_info or {"message": "Task revoked by broker"},
                }
            )

        merged = dict(task)
        merged.update(updates)
        merged["broker_checked_at"] = checked_at
        changed_updates = {
            key: value
            for key, value in updates.items()
            if task.get(key) != value
        }
        if changed_updates:
            saved = self._attach_runtime_task(task["id"], changed_updates)
            saved["broker_checked_at"] = checked_at
            return saved
        return merged

    def _sync_visible_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        synced = [self._sync_celery_task(task) for task in tasks]
        return sorted(
            synced,
            key=lambda item: item.get("created_at") or "",
            reverse=True,
        )

    def _all_tasks(self, limit: int = 200) -> List[Dict[str, Any]]:
        persisted = {task["id"]: task for task in self._load_persisted_tasks(limit=limit)}
        with self._lock:
            for task_id, task in self._tasks.items():
                persisted[task_id] = {**persisted.get(task_id, {}), **task}
        tasks = sorted(
            persisted.values(),
            key=lambda item: item.get("created_at") or "",
            reverse=True,
        )
        return tasks[: max(1, min(int(limit or 50), 500))]

    def _select_backend(self, requested_backend: str = "auto", handler: Optional[TaskHandler] = None) -> str:
        normalized = str(requested_backend or "auto").strip().lower()
        if normalized not in {"auto", "local", "celery"}:
            normalized = "auto"
        if normalized == "local":
            return "local"
        if normalized == "celery":
            return "celery" if self._celery_app and handler is None else "local"
        return "celery" if self._celery_app and handler is None else "local"

    def health(self) -> Dict[str, Any]:
        tasks = self._sync_visible_tasks(self._all_tasks(limit=500))
        completed_tasks = [
            task for task in tasks
            if task.get("status") == "completed" and task.get("started_at") and task.get("finished_at")
        ]
        average_duration = None
        if completed_tasks:
            durations = []
            for task in completed_tasks:
                try:
                    started = datetime.fromisoformat(task["started_at"])
                    finished = datetime.fromisoformat(task["finished_at"])
                    durations.append((finished - started).total_seconds())
                except Exception:
                    continue
            if durations:
                average_duration = round(sum(durations) / len(durations), 2)
        execution_backends = sorted({task.get("execution_backend") or "local" for task in tasks})
        celery_ready = bool(self._celery_app)
        worker_pid = _read_pid_file(WORKER_PID_FILE)
        worker_running = _process_alive(worker_pid)
        return {
            "mode": "hybrid_celery" if celery_ready else "local_executor",
            "workers": self.max_workers,
            "redis_configured": bool(self.redis_url),
            "celery_configured": bool(self.celery_broker_url),
            "celery_importable": celery_ready,
            "celery_import_error": self._celery_import_error,
            "result_backend_configured": bool(self.celery_result_backend),
            "queued_or_running": sum(1 for task in tasks if task.get("status") in {"queued", "running"}),
            "completed": sum(1 for task in tasks if task.get("status") == "completed"),
            "failed": sum(1 for task in tasks if task.get("status") == "failed"),
            "cancelled": sum(1 for task in tasks if task.get("status") == "cancelled"),
            "persisted_tasks": len(tasks),
            "average_duration_seconds": average_duration,
            "execution_backends": execution_backends,
            "broker_states": sorted({task.get("broker_state") for task in tasks if task.get("broker_state")}),
            "broker_url": self.celery_broker_url,
            "result_backend": self.celery_result_backend,
            "worker_running": worker_running,
            "worker_pid": worker_pid if worker_running else None,
            "worker_pid_file": str(WORKER_PID_FILE),
            "worker_log_file": str(WORKER_LOG_FILE),
            "worker_command": (
                "./scripts/start_celery_worker.sh"
                if celery_ready
                else None
            ),
            "note": (
                "Celery + Redis dispatch is available; tasks can run on external workers."
                if celery_ready
                else "Local executor is active; install celery/redis and set CELERY_BROKER_URL to enable distributed execution."
            ),
        }

    def submit(
        self,
        name: str,
        payload: Optional[Dict[str, Any]] = None,
        handler: Optional[TaskHandler] = None,
        backend: str = "auto",
    ) -> Dict[str, Any]:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        task = self._empty_task_template(task_id=task_id, name=name, payload=payload)
        task["execution_backend"] = self._select_backend(backend, handler)
        saved = self._attach_runtime_task(task_id, task)
        if saved["execution_backend"] == "celery" and self._celery_app:
            celery_async_result = self._celery_app.send_task(
                self._celery_task_name,
                args=[task_id, saved["name"], saved["payload"]],
            )
            saved = self._attach_runtime_task(
                task_id,
                {
                    "broker_task_id": celery_async_result.id,
                    "broker_state": "PENDING",
                    "stage": "broker_dispatched",
                    "result": {
                        "message": "Task dispatched to Celery worker",
                        "broker_task_id": celery_async_result.id,
                    },
                },
            )
            return dict(saved)
        self._executor.submit(self._run_task, task_id, handler or self._default_handler)
        return dict(saved)

    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [dict(task) for task in self._sync_visible_tasks(self._all_tasks(limit=limit))]

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                return dict(self._sync_celery_task(task))
        persisted = self._load_persisted_task(task_id)
        return dict(self._sync_celery_task(persisted)) if persisted else None

    def cancel(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self.get_task(task_id)
        if not task:
            return None
        if task["status"] in {"completed", "failed", "cancelled"}:
            return dict(task)
        now = _utcnow_iso()
        updates: Dict[str, Any] = {
            "cancel_requested": True,
            "cancel_requested_at": now,
        }
        if task.get("broker_task_id") and self._celery_app:
            try:
                self._celery_app.control.revoke(task["broker_task_id"], terminate=False)
            except Exception:
                pass
        if task["status"] == "queued":
            updates.update(
                {
                    "status": "cancelled",
                    "stage": "cancelled",
                    "progress": task.get("progress") or 0.0,
                    "cancelled_at": now,
                    "finished_at": now,
                    "result": {"message": "Task cancelled before execution"},
                }
            )
        return self._attach_runtime_task(task_id, updates)

    def _update_task(self, task_id: str, **updates: Any) -> Dict[str, Any]:
        return self._attach_runtime_task(task_id, updates)

    def _is_cancel_requested(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        return bool(task and task.get("cancel_requested"))

    def _run_task(self, task_id: str, handler: TaskHandler) -> None:
        task = self.get_task(task_id)
        if not task or task.get("status") == "cancelled":
            return
        self._update_task(
            task_id,
            status="running",
            started_at=_utcnow_iso(),
            stage="initializing",
            progress=max(float(task.get("progress") or 0), 0.02),
        )
        try:
            task = self.get_task(task_id) or {}
            task_payload = dict(task.get("payload") or {})
            task_name = str(task.get("name") or "manual_task")
            handler_func = getattr(handler, "__func__", None)
            default_func = getattr(self._default_handler, "__func__", None)
            if handler_func == default_func:
                result = self._dispatch_registered_task(task_id, task_name, task_payload)
            else:
                result = handler(task_payload)
            if self._is_cancel_requested(task_id):
                self._update_task(
                    task_id,
                    status="cancelled",
                    stage="cancelled",
                    finished_at=_utcnow_iso(),
                    cancelled_at=_utcnow_iso(),
                    result={"message": "Task cancelled during execution"},
                )
                return
            self._update_task(
                task_id,
                status="completed",
                result=result,
                finished_at=_utcnow_iso(),
                progress=1.0,
                stage="completed",
            )
        except Exception as exc:  # pragma: no cover - worker safety net
            self._update_task(
                task_id,
                status="failed",
                error=str(exc),
                finished_at=_utcnow_iso(),
                stage="failed",
            )

    def _task_stages(self, task_name: str) -> List[str]:
        normalized = task_name.lower()
        if "quant" in normalized and "optimizer" in normalized:
            return ["validating_request", "loading_market_data", "searching_parameters", "publishing_results"]
        if "quant" in normalized and "risk" in normalized:
            return ["validating_request", "loading_portfolio_data", "running_risk_models", "publishing_results"]
        if "quant" in normalized and "valuation" in normalized:
            return ["validating_request", "loading_fundamentals", "building_ensemble", "publishing_results"]
        if "quant" in normalized and "industry" in normalized:
            return ["validating_request", "loading_industry_data", "running_rotation_backtest", "publishing_results"]
        if "quant" in normalized and "factor" in normalized:
            return ["validating_request", "loading_factor_inputs", "evaluating_expression", "publishing_results"]
        if "backtest" in normalized and "monte" in normalized:
            return ["validating_request", "running_base_backtest", "simulating_paths", "publishing_results"]
        if "backtest" in normalized and "significance" in normalized:
            return ["validating_request", "running_strategy_set", "computing_significance", "publishing_results"]
        if "backtest" in normalized and "multi" in normalized:
            return ["validating_request", "loading_multi_interval_data", "running_interval_backtests", "publishing_results"]
        if "backtest" in normalized and "impact" in normalized:
            return ["validating_request", "building_impact_scenarios", "running_cost_backtests", "publishing_results"]
        if "backtest" in normalized:
            return ["loading_market_data", "running_backtest_shards", "aggregating_metrics", "persisting_snapshot"]
        if "optim" in normalized:
            return ["sampling_parameters", "running_candidates", "checking_stability", "publishing_leaderboard"]
        if "research" in normalized:
            return ["building_context", "executing_research_job", "assembling_outputs", "publishing_results"]
        return ["preparing_payload", "executing_worker", "collecting_results", "publishing_output"]

    def _resolve_registered_handler(self, task_name: str) -> Optional[TaskHandler]:
        normalized = str(task_name or "").strip().lower().replace(" ", "_")
        aliases = {
            "quant.strategy_optimizer": "quant_strategy_optimizer",
            "strategy_optimizer": "quant_strategy_optimizer",
            "quant.risk_center": "quant_risk_center",
            "risk_center": "quant_risk_center",
            "quant.valuation_lab": "quant_valuation_lab",
            "valuation_lab": "quant_valuation_lab",
            "quant.industry_rotation": "quant_industry_rotation",
            "industry_rotation": "quant_industry_rotation",
            "quant.factor_expression": "quant_factor_expression",
            "factor_expression": "quant_factor_expression",
            "backtest.monte_carlo": "backtest_monte_carlo",
            "backtest.compare_significance": "backtest_significance",
            "backtest.multi_period": "backtest_multi_period",
            "backtest.impact_analysis": "backtest_impact_analysis",
        }
        normalized = aliases.get(normalized, normalized)
        if not normalized.startswith("quant_") and not normalized.startswith("backtest_"):
            return None

        from backend.app.services.quant_lab import quant_lab_service
        from backend.app.api.v1.endpoints.backtest import (
            compare_strategy_significance_sync,
            run_backtest_monte_carlo_sync,
            run_market_impact_analysis_sync,
            run_multi_period_backtest_sync,
        )

        registry: Dict[str, TaskHandler] = {
            "quant_strategy_optimizer": quant_lab_service.optimize_strategy,
            "quant_risk_center": quant_lab_service.analyze_risk_center,
            "quant_valuation_lab": quant_lab_service.analyze_valuation_lab,
            "quant_industry_rotation": quant_lab_service.run_industry_rotation_lab,
            "quant_factor_expression": quant_lab_service.evaluate_factor_expression,
            "backtest_monte_carlo": run_backtest_monte_carlo_sync,
            "backtest_significance": compare_strategy_significance_sync,
            "backtest_multi_period": run_multi_period_backtest_sync,
            "backtest_impact_analysis": run_market_impact_analysis_sync,
        }
        return registry.get(normalized)

    def _dispatch_registered_task(self, task_id: str, task_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        handler = self._resolve_registered_handler(task_name)
        if handler is None:
            return self._run_default_handler(task_id, task_name, payload)

        self._update_task(
            task_id,
            stage="validating_request",
            progress=max(float((self.get_task(task_id) or {}).get("progress") or 0.0), 0.08),
        )
        time.sleep(0.02)
        self._update_task(
            task_id,
            stage="executing_quant_job",
            progress=max(float((self.get_task(task_id) or {}).get("progress") or 0.0), 0.32),
        )
        result = handler(payload)
        self._update_task(
            task_id,
            stage="publishing_results",
            progress=max(float((self.get_task(task_id) or {}).get("progress") or 0.0), 0.92),
        )
        return result

    def _run_default_handler(self, task_id: str, task_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        total_sleep = min(float(payload.get("sleep_seconds", 0.8) or 0.8), 8.0)
        configured_steps = int(payload.get("steps") or 0)
        stages = self._task_stages(task_name)
        if configured_steps > 0:
            if configured_steps <= len(stages):
                stages = stages[:configured_steps]
            else:
                stages = stages + [f"step_{index + 1}" for index in range(len(stages), configured_steps)]
        per_stage_sleep = total_sleep / max(len(stages), 1)
        for index, stage in enumerate(stages, start=1):
            if self._is_cancel_requested(task_id):
                break
            self._update_task(
                task_id,
                stage=stage,
                progress=round(index / (len(stages) + 1), 4),
            )
            time.sleep(per_stage_sleep)
        if self._is_cancel_requested(task_id):
            return {"message": "Task cancellation acknowledged", "echo": payload}
        return {
            "message": "Task executed by queue runtime",
            "echo": payload,
            "stages": stages,
        }

    def _default_handler(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        time.sleep(min(float(payload.get("sleep_seconds", 0.2) or 0.2), 5.0))
        return {
            "message": "Task executed by queue runtime",
            "echo": payload,
        }

    def run_distributed_task(self, task_id: str, task_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        task = self.get_task(task_id)
        if not task:
            self._attach_runtime_task(
                task_id,
                self._empty_task_template(task_id=task_id, name=task_name, payload=payload),
            )
        self._update_task(
            task_id,
            status="running",
            started_at=(self.get_task(task_id) or {}).get("started_at") or _utcnow_iso(),
            stage="worker_started",
            execution_backend="celery",
            broker_state="STARTED",
            progress=max(float((self.get_task(task_id) or {}).get("progress") or 0), 0.05),
        )
        result = self._dispatch_registered_task(task_id=task_id, task_name=task_name, payload=payload)
        if self._is_cancel_requested(task_id):
            self._update_task(
                task_id,
                status="cancelled",
                stage="cancelled",
                finished_at=_utcnow_iso(),
                cancelled_at=_utcnow_iso(),
                result={"message": "Task cancelled on distributed worker"},
            )
            return {"cancelled": True}
        self._update_task(
            task_id,
            status="completed",
            finished_at=_utcnow_iso(),
            progress=1.0,
            stage="completed",
            broker_state="SUCCESS",
            result=result,
        )
        return result


task_queue_manager = TaskQueueManager()
celery_app = task_queue_manager.celery_app
