from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class QuestionBase(BaseModel):
    question_text: str
    question_type: str = Field(default="brand_reputation", max_length=100)
    tags: Optional[str] = None
    priority: int = Field(default=50, ge=1, le=100)
    sample_policy: str = Field(default="mvp", max_length=50)
    enabled: bool = True
    focus: bool = False


class QuestionCreate(QuestionBase):
    group_id: Optional[UUID] = None


class QuestionUpdate(BaseModel):
    question_text: Optional[str] = None
    question_type: Optional[str] = Field(default=None, max_length=100)
    tags: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=100)
    sample_policy: Optional[str] = Field(default=None, max_length=50)
    enabled: Optional[bool] = None
    focus: Optional[bool] = None


class QuestionOut(QuestionBase):
    id: UUID
    group_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class QuestionGroupBase(BaseModel):
    layer: str = Field(..., max_length=50)
    intent_name: str = Field(..., max_length=200)
    representative_question: str = Field(..., max_length=1000)
    priority: int = Field(default=50, ge=1, le=100)
    status: str = Field(default="active", max_length=50)


class QuestionGroupCreate(QuestionGroupBase):
    project_id: UUID


class QuestionGroupUpdate(BaseModel):
    layer: Optional[str] = Field(default=None, max_length=50)
    intent_name: Optional[str] = Field(default=None, max_length=200)
    representative_question: Optional[str] = Field(default=None, max_length=1000)
    priority: Optional[int] = Field(default=None, ge=1, le=100)
    status: Optional[str] = Field(default=None, max_length=50)


class QuestionGroupOut(QuestionGroupBase):
    id: UUID
    project_id: UUID
    created_at: datetime
    questions: List[QuestionOut] = []

    class Config:
        from_attributes = True
