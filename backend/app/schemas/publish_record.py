from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PublishRecordBase(BaseModel):
    platform: str = Field(..., max_length=200)
    url: Optional[str] = Field(None, max_length=1000)
    title: Optional[str] = Field(None, max_length=500)
    content_type: Optional[str] = Field(None, max_length=100)
    published_at: Optional[datetime] = None
    status: str = Field(default="published", max_length=50)
    is_indexed: bool = False
    first_indexed_at: Optional[datetime] = None
    related_question_group_id: Optional[UUID] = None


class PublishRecordCreate(PublishRecordBase):
    task_id: UUID
    draft_id: Optional[UUID] = None
    channel_account_id: Optional[UUID] = None
    publisher_id: Optional[UUID] = None
    force_save: bool = False


class PublishRecordUpdate(BaseModel):
    draft_id: Optional[UUID] = None
    channel_account_id: Optional[UUID] = None
    platform: Optional[str] = Field(None, max_length=200)
    url: Optional[str] = Field(None, max_length=1000)
    title: Optional[str] = Field(None, max_length=500)
    content_type: Optional[str] = Field(None, max_length=100)
    published_at: Optional[datetime] = None
    publisher_id: Optional[UUID] = None
    status: Optional[str] = Field(None, max_length=50)
    is_indexed: Optional[bool] = None
    first_indexed_at: Optional[datetime] = None
    related_question_group_id: Optional[UUID] = None


class PublishWebBridgeAssistRequest(BaseModel):
    draft_id: UUID
    channel_account_id: Optional[UUID] = None
    platform: Optional[str] = Field(default=None, max_length=200)
    publisher_url: Optional[str] = Field(default=None, max_length=1000)
    title_selector: Optional[str] = Field(default=None, max_length=500)
    body_selector: Optional[str] = Field(default=None, max_length=500)


class PublishRecordOut(PublishRecordBase):
    id: UUID
    task_id: UUID
    draft_id: Optional[UUID] = None
    draft_version: Optional[str] = None
    channel_account_id: Optional[UUID] = None
    publisher_id: Optional[UUID] = None
    related_content_task_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
