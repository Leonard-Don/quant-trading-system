"""Unified research journal endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.services.research_journal import research_journal_store

router = APIRouter()


class ResearchJournalSnapshotRequest(BaseModel):
    entries: List[dict] = Field(default_factory=list)
    source_state: Dict[str, Any] = Field(default_factory=dict)
    generated_at: str | None = None


class ResearchJournalEntryRequest(BaseModel):
    entry: Dict[str, Any] = Field(default_factory=dict)


class ResearchJournalStatusRequest(BaseModel):
    status: str


def _resolve_research_profile(request: Request) -> str:
    header_profile = request.headers.get("X-Research-Profile")
    if header_profile:
        return header_profile

    realtime_profile = request.headers.get("X-Realtime-Profile")
    if realtime_profile:
        return realtime_profile

    query_profile = request.query_params.get("profile_id")
    if query_profile:
        return query_profile

    return "default"


@router.get("/snapshot", summary="获取统一研究档案快照")
async def get_research_journal_snapshot(request: Request):
    profile_id = _resolve_research_profile(request)
    return {
        "success": True,
        "data": research_journal_store.get_snapshot(profile_id=profile_id),
    }


@router.put("/snapshot", summary="同步统一研究档案快照")
async def update_research_journal_snapshot(payload: ResearchJournalSnapshotRequest, request: Request):
    profile_id = _resolve_research_profile(request)
    data = research_journal_store.update_snapshot(payload.model_dump(), profile_id=profile_id)
    return {"success": True, "data": data}


@router.post("/entries", summary="新增一条研究档案记录")
async def add_research_journal_entry(payload: ResearchJournalEntryRequest, request: Request):
    profile_id = _resolve_research_profile(request)
    try:
        data = research_journal_store.add_entry(payload.entry, profile_id=profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": data}


@router.patch("/entries/{entry_id}/status", summary="更新研究档案记录状态")
async def update_research_journal_entry_status(
    entry_id: str,
    payload: ResearchJournalStatusRequest,
    request: Request,
):
    profile_id = _resolve_research_profile(request)
    try:
        data = research_journal_store.update_entry_status(entry_id, payload.status, profile_id=profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="entry not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "data": data}
