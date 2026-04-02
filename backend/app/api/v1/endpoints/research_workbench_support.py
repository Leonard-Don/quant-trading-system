from __future__ import annotations

from fastapi import HTTPException


def success_response(data, *, total: int | None = None) -> dict:
    payload = {"success": True, "data": data, "error": None}
    if total is not None:
        payload["total"] = total
    return payload


def deleted_response(item_id: str) -> dict:
    return success_response({"id": item_id, "deleted": True})


def ensure_task(task, task_id: str):
    if not task:
        raise HTTPException(status_code=404, detail=f"Research task not found: {task_id}")
    return task


def ensure_comment_deleted(deleted: bool, comment_id: str):
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Research comment not found: {comment_id}")


def validate_reorder_items(items) -> None:
    invalid_archived = next((item for item in items if item.status == "archived"), None)
    if invalid_archived:
        raise HTTPException(status_code=400, detail="Archived tasks cannot be reordered on the active board")

    task_ids = {item.task_id for item in items}
    if len(task_ids) != len(items):
        raise HTTPException(status_code=400, detail="Duplicated task_id in reorder payload")
