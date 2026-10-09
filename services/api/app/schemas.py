from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Source(str, Enum):
    FOUNDRY = "foundry"
    FABRIC = "fabric"
    WORK = "work"
    WEB = "web"


class Owner(BaseModel):
    id: str
    display: str
    role: str


class Evidence(BaseModel):
    refId: str
    source: Source
    title: str
    snippet: str
    url: str | None
    sourceType: str


class NextAction(BaseModel):
    text: str
    steps: list[str] = Field(default_factory=list)
    owner: Owner
    taskType: str
    taskId: str = ""
    taskStatus: str = "Drafted (not submitted)"
    due: str = ""


class HumanReview(BaseModel):
    owner: Owner
    reason: str


class Reviewer(BaseModel):
    role: str
    owner: Owner
    status: Literal["assigned", "pending", "complete"]


SourceState = Literal["queued", "searching", "retrieved", "needs_review", "complete", "failed"]


class SourceMapItem(BaseModel):
    source: Source
    label: str
    status: SourceState
    queries: list[str]
    citations: list[str]
    durationMs: int
    retrieving: str = ""
    evidenceCount: int = 0
    evidenceNoun: str = "sources"


class TraceStep(BaseModel):
    step: str
    source: Source | None = None
    detail: str
    ts: int
    status: Literal["completed", "in_progress", "pending", "queued"] = "completed"


class PlanEventPayload(BaseModel):
    steps: list[str]


class SourceQueryEventPayload(BaseModel):
    source: Source
    label: str
    query: str
    retrieving: str = ""
    status: Literal["searching"] = "searching"


class SourceResultEventPayload(BaseModel):
    source: Source
    status: SourceState
    summary: str
    citations: list[str]
    durationMs: int
    retrieving: str = ""
    evidenceCount: int = 0
    evidenceNoun: str = "sources"


class ErrorEventPayload(BaseModel):
    message: str
