from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas.research_workbench import (
    ResearchTaskBulkUpdateRequest,
    ResearchTaskCommentCreateRequest,
    ResearchTaskCreateRequest,
    ResearchWorkbenchReorderRequest,
    ResearchTaskSnapshotCreateRequest,
    ResearchTaskUpdateRequest,
)
from src.research.workbench import research_workbench_store
from .research_workbench_support import (
    deleted_response,
    ensure_comment_deleted,
    ensure_task,
    success_response,
    validate_reorder_items,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_research_workbench():
    return research_workbench_store


def _run_workbench_action(label: str, action):
    try:
        return action()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to %s: %s", label, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/tasks", summary="获取研究工作台任务")
async def list_research_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
    view: str | None = Query(default=None),
):
    def _list_action():
        tasks = _get_research_workbench().list_tasks(limit=limit, task_type=type, status=status, source=source, view=view)
        return success_response(tasks, total=len(tasks))

    return _run_workbench_action("list research tasks", _list_action)


@router.post("/tasks", summary="创建研究工作台任务")
async def create_research_task(request: ResearchTaskCreateRequest):
    return _run_workbench_action(
        "create research task",
        lambda: success_response(_get_research_workbench().create_task(request.model_dump())),
    )


@router.post("/tasks/bulk-update", summary="批量更新研究工作台任务")
async def bulk_update_research_tasks(request: ResearchTaskBulkUpdateRequest):
    def _bulk_update_action():
        tasks = _get_research_workbench().bulk_update_tasks(
            request.task_ids,
            status=request.status,
            comment=request.comment,
            author=request.author,
        )
        return success_response(tasks, total=len(tasks))

    return _run_workbench_action("bulk update research tasks", _bulk_update_action)


@router.get("/tasks/{task_id}", summary="获取研究工作台任务详情")
async def get_research_task(task_id: str):
    task = ensure_task(_get_research_workbench().get_task(task_id), task_id)
    return success_response(task)


@router.get("/tasks/{task_id}/timeline", summary="获取研究任务时间线")
async def get_research_task_timeline(task_id: str):
    timeline = _get_research_workbench().get_timeline(task_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail=f"Research task not found: {task_id}")
    return success_response(timeline)


@router.put("/tasks/{task_id}", summary="更新研究工作台任务")
async def update_research_task(task_id: str, request: ResearchTaskUpdateRequest):
    task = ensure_task(
        _get_research_workbench().update_task(task_id, request.model_dump(exclude_unset=True)),
        task_id,
    )
    return success_response(task)


@router.post("/tasks/{task_id}/comments", summary="为研究任务添加评论")
async def add_research_task_comment(task_id: str, request: ResearchTaskCommentCreateRequest):
    comment = ensure_task(
        _get_research_workbench().add_comment(task_id, body=request.body, author=request.author),
        task_id,
    )
    return success_response(comment)


@router.delete("/tasks/{task_id}/comments/{comment_id}", summary="删除研究任务评论")
async def delete_research_task_comment(task_id: str, comment_id: str):
    ensure_task(_get_research_workbench().get_task(task_id), task_id)

    deleted = _get_research_workbench().delete_comment(task_id, comment_id)
    ensure_comment_deleted(deleted, comment_id)
    return deleted_response(comment_id)


@router.post("/tasks/{task_id}/snapshot", summary="追加研究任务快照")
async def add_research_task_snapshot(task_id: str, request: ResearchTaskSnapshotCreateRequest):
    refresh_priority_event = (
        request.refresh_priority_event.model_dump()
        if request.refresh_priority_event
        else None
    )
    task = ensure_task(
        _get_research_workbench().add_snapshot(
            task_id,
            request.snapshot.model_dump(),
            refresh_priority_event=refresh_priority_event,
        ),
        task_id,
    )
    return success_response(task)


@router.post("/board/reorder", summary="批量更新研究工作台看板顺序")
async def reorder_research_board(request: ResearchWorkbenchReorderRequest):
    validate_reorder_items(request.items)

    tasks = _get_research_workbench().reorder_board([item.model_dump() for item in request.items])
    return success_response(tasks)


@router.delete("/tasks/{task_id}", summary="删除研究工作台任务")
async def delete_research_task(task_id: str):
    deleted = _get_research_workbench().delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Research task not found: {task_id}")
    return deleted_response(task_id)


@router.get("/stats", summary="获取研究工作台统计")
async def get_research_task_stats():
    return _run_workbench_action(
        "load research task stats",
        lambda: success_response(_get_research_workbench().get_stats()),
    )
