from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.research_workbench import (
    ResearchTaskCreateRequest,
    ResearchTaskUpdateRequest,
)
from src.research.workbench import research_workbench_store

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_research_workbench():
    return research_workbench_store


@router.get("/tasks", summary="获取研究工作台任务")
async def list_research_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
):
    try:
        workbench = _get_research_workbench()
        tasks = workbench.list_tasks(limit=limit, task_type=type, status=status, source=source)
        return {"success": True, "data": tasks, "total": len(tasks), "error": None}
    except Exception as exc:
        logger.error("Failed to list research tasks: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/tasks", summary="创建研究工作台任务")
async def create_research_task(request: ResearchTaskCreateRequest):
    try:
        workbench = _get_research_workbench()
        task = workbench.create_task(request.model_dump())
        return {"success": True, "data": task, "error": None}
    except Exception as exc:
        logger.error("Failed to create research task: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/tasks/{task_id}", summary="获取研究工作台任务详情")
async def get_research_task(task_id: str):
    task = _get_research_workbench().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Research task not found: {task_id}")
    return {"success": True, "data": task, "error": None}


@router.put("/tasks/{task_id}", summary="更新研究工作台任务")
async def update_research_task(task_id: str, request: ResearchTaskUpdateRequest):
    task = _get_research_workbench().update_task(task_id, request.model_dump(exclude_unset=True))
    if not task:
        raise HTTPException(status_code=404, detail=f"Research task not found: {task_id}")
    return {"success": True, "data": task, "error": None}


@router.delete("/tasks/{task_id}", summary="删除研究工作台任务")
async def delete_research_task(task_id: str):
    deleted = _get_research_workbench().delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Research task not found: {task_id}")
    return {"success": True, "data": {"id": task_id, "deleted": True}, "error": None}


@router.get("/stats", summary="获取研究工作台统计")
async def get_research_task_stats():
    try:
        stats = _get_research_workbench().get_stats()
        return {"success": True, "data": stats, "error": None}
    except Exception as exc:
        logger.error("Failed to load research task stats: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
