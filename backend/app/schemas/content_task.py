from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ContentTaskBase(BaseModel):
    content_type: str = Field(..., max_length=100)
    layer: str = Field(default="verification_layer", max_length=50)
    priority: str = Field(default="medium", max_length=20)
    status: str = Field(default="draft", max_length=50)
    due_date: Optional[datetime] = None
    estimated_token_cost: Optional[float] = None
    estimated_api_cost: Optional[float] = None
    estimated_labor_minutes: Optional[float] = None


class ContentTaskCreate(ContentTaskBase):
    project_id: UUID
    group_id: Optional[UUID] = None
    question_id: Optional[UUID] = None
    knowledge_asset_ids: List[UUID] = Field(default_factory=list)


class ContentTaskUpdate(BaseModel):
    group_id: Optional[UUID] = None
    question_id: Optional[UUID] = None
    knowledge_asset_ids: Optional[List[UUID]] = None
    content_type: Optional[str] = Field(None, max_length=100)
    layer: Optional[str] = Field(None, max_length=50)
    priority: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = Field(None, max_length=50)
    assignee: Optional[UUID] = None
    due_date: Optional[datetime] = None
    estimated_token_cost: Optional[float] = None
    estimated_api_cost: Optional[float] = None
    estimated_labor_minutes: Optional[float] = None


class ContentTaskTransition(BaseModel):
    target_status: str = Field(..., max_length=50)
    context: Dict[str, Any] = Field(default_factory=dict)
    skip_block_check: bool = False


class ContentTaskOut(ContentTaskBase):
    id: UUID
    project_id: UUID
    group_id: Optional[UUID] = None
    question_id: Optional[UUID] = None
    knowledge_asset_ids: List[UUID] = Field(default_factory=list)
    assignee: Optional[UUID] = None
    actual_token_cost: Optional[float] = None
    actual_api_cost: Optional[float] = None
    actual_labor_minutes: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
