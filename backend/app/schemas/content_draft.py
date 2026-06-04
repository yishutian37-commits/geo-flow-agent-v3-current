from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class ContentDraftBase(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    body: Optional[str] = None
    version: str = Field(default="1.0", max_length=20)
    platform: str = Field(default="media", max_length=200)
    status: str = Field(default="draft", max_length=50)
    risk_level: str = Field(default="low", max_length=20)
    fact_refs: Optional[str] = None


class ContentDraftCreate(ContentDraftBase):
    task_id: UUID


class ContentDraftUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    body: Optional[str] = None
    version: Optional[str] = Field(None, max_length=20)
    platform: Optional[str] = Field(None, max_length=200)
    status: Optional[str] = Field(None, max_length=50)
    risk_level: Optional[str] = Field(None, max_length=20)
    fact_refs: Optional[str] = None


class ContentDraftOut(ContentDraftBase):
    id: UUID
    task_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DraftGenerateRequest(BaseModel):
    content_type: str = Field(..., max_length=100)
    platform: str = Field(default="media", max_length=50)
    brand_id: Optional[UUID] = None
    source_draft_id: Optional[UUID] = None
    feedback_context: Optional[str] = None
