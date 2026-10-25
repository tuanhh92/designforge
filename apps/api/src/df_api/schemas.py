"""HTTP response/request models (they define the OpenAPI the web client is typed from)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

DesignStatus = Literal["uploaded", "analyzing", "spec_ready", "building", "model_ready", "failed", "unsupported"]


class DesignSummary(BaseModel):
    id: UUID
    name: str
    status: DesignStatus
    category: str | None
    created_at: datetime
    updated_at: datetime
    cover_url: str | None


class ImageOut(BaseModel):
    id: UUID
    url: str
    width_px: int
    height_px: int


class SpecOut(BaseModel):
    id: UUID
    version: int
    origin: Literal["ai", "user_edit"]
    spec: dict[str, Any]
    spec_hash: str
    field_confidence: dict[str, Any]
    issues: list[dict[str, Any]]
    observation: dict[str, Any] | None
    notes_detail: list[dict[str, Any]]
    provider: str | None
    model: str | None
    created_at: datetime


class SpecVersionOut(BaseModel):
    id: UUID
    version: int
    origin: str
    created_at: datetime


class JobOut(BaseModel):
    id: UUID
    kind: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    step: str | None
    progress: float
    attempts: int
    max_attempts: int
    error: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobEventOut(BaseModel):
    id: int
    ts: datetime
    level: str
    step: str | None
    message: str
    code: str | None
    params: dict[str, Any]


class ArtifactOut(BaseModel):
    id: UUID
    kind: str
    name: str
    bytes: int
    mime: str
    producer: str
    url: str
    created_at: datetime


class DesignDetail(BaseModel):
    id: UUID
    name: str
    status: DesignStatus
    status_message: str | None
    status_code: str | None
    status_params: dict[str, Any]
    category: str | None
    hints: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    images: list[ImageOut]
    spec: SpecOut | None
    versions: list[SpecVersionOut]
    jobs: list[JobOut]
    events: list[JobEventOut]
    artifacts: list[ArtifactOut]
    busy: bool


class CreatedDesign(BaseModel):
    id: UUID


class SpecSaved(BaseModel):
    spec_id: UUID | None
    issues: list[dict[str, Any]]
    job_id: UUID | None


class SpecValidation(BaseModel):
    issues: list[dict[str, Any]]
    spec_hash: str


class JobQueued(BaseModel):
    job_id: UUID
