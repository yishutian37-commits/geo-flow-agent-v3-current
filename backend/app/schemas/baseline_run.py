from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class BaselineRunBase(BaseModel):
    model_config = {"protected_namespaces": ()}

    project_id: UUID
    question_id: UUID
    model_target_id: UUID
    mechanism_type: str = Field(..., max_length=50)
    call_mode_detail: Optional[str] = None
    sample_policy: str = Field(default="acceptance", max_length=50)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    confidence_level: str = Field(default="medium", max_length=20)
    valid_status: str = Field(default="valid", max_length=50)
    invalid_reason: Optional[str] = None


class BaselineRunCreate(BaselineRunBase):
    pass


class BaselineRunUpdate(BaseModel):
    model_config = {"protected_namespaces": ()}

    call_mode_detail: Optional[str] = None
    sample_policy: Optional[str] = Field(None, max_length=50)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    confidence_level: Optional[str] = Field(None, max_length=20)
    valid_status: Optional[str] = Field(None, max_length=50)
    invalid_reason: Optional[str] = None


class BaselinePromoteRequest(BaseModel):
    require_acceptance_grade: bool = False
    invalid_reason: Optional[str] = None


class BaselineRunOut(BaselineRunBase):
    id: UUID

    class Config:
        from_attributes = True
