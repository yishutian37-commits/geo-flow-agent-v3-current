from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ReportArchiveGenerateRequest(BaseModel):
    project_id: UUID
    report_type: str = Field(default="client", pattern="^(client|internal)$")
    run_id: Optional[UUID] = None
    run_ids: Optional[list[UUID]] = None
    baseline_run_id: Optional[UUID] = None
    time_window_days: int = Field(default=30, ge=1, le=365)
    title: Optional[str] = Field(default=None, max_length=300)


class ReportArchiveSummary(BaseModel):
    id: UUID
    project_id: UUID
    report_type: str
    title: str
    run_id: Optional[UUID] = None
    baseline_run_id: Optional[UUID] = None
    time_window_days: int
    acceptance_ready: bool
    confidence_level: Optional[str] = None
    sample_count: int
    generated_at: datetime
    created_at: datetime


class ReportArchiveDetail(ReportArchiveSummary):
    markdown: str
    payload: dict
