from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ContentFeedbackCreate(BaseModel):
    project_id: UUID
    draft_id: Optional[UUID] = None
    feedback_type: str = Field(..., max_length=50)
    rating: Optional[str] = Field(None, max_length=50)
    comment: Optional[str] = None
    rule_text: Optional[str] = None
    rule_category: Optional[str] = Field(None, max_length=100)
    diff_summary: Optional[str] = None
    source: str = Field(default="manual", max_length=50)


class ContentFeedbackUpdate(BaseModel):
    rating: Optional[str] = Field(None, max_length=50)
    comment: Optional[str] = None
    rule_text: Optional[str] = None
    rule_category: Optional[str] = Field(None, max_length=100)
    diff_summary: Optional[str] = None
    is_folded: Optional[bool] = None


class ContentFeedbackOut(BaseModel):
    id: UUID
    project_id: UUID
    draft_id: Optional[UUID] = None
    feedback_type: str
    rating: Optional[str] = None
    comment: Optional[str] = None
    rule_text: Optional[str] = None
    rule_category: Optional[str] = None
    diff_summary: Optional[str] = None
    source: str
    is_folded: bool
    created_at: datetime

    class Config:
        from_attributes = True


class WritingProfileUpdate(BaseModel):
    style_preferences: Optional[Dict[str, Any]] = None
    title_preferences: Optional[Dict[str, Any]] = None
    constraints: Optional[Dict[str, Any]] = None
    platform_habits: Optional[Dict[str, Any]] = None
    feedback_count: Optional[int] = None
    version: Optional[int] = None


class FoldProfileRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_id: Optional[str] = None
    include_folded: bool = False
