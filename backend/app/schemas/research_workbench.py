"""Schemas for research workbench tasks."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ResearchTaskStatus = Literal["new", "in_progress", "blocked", "complete", "archived"]
ResearchTaskType = Literal["pricing", "cross_market"]


class ResearchTaskSnapshot(BaseModel):
    headline: str = ""
    summary: str = ""
    highlights: List[str] = Field(default_factory=list)
    payload: Dict[str, Any] = Field(default_factory=dict)


class ResearchTask(BaseModel):
    id: str
    created_at: str
    updated_at: str
    status: ResearchTaskStatus
    type: ResearchTaskType
    title: str
    source: str = ""
    symbol: str = ""
    template: str = ""
    note: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)
    snapshot: ResearchTaskSnapshot = Field(default_factory=ResearchTaskSnapshot)


class ResearchTaskCreateRequest(BaseModel):
    type: ResearchTaskType
    title: str
    status: ResearchTaskStatus = "new"
    source: str = ""
    symbol: str = ""
    template: str = ""
    note: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)
    snapshot: Optional[ResearchTaskSnapshot] = None


class ResearchTaskUpdateRequest(BaseModel):
    status: Optional[ResearchTaskStatus] = None
    title: Optional[str] = None
    note: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    snapshot: Optional[ResearchTaskSnapshot] = None


class ResearchTaskListResponse(BaseModel):
    success: bool
    data: List[ResearchTask] = Field(default_factory=list)
    total: int = 0
    error: Optional[str] = None
