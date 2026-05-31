from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ApprovalCreate(BaseModel):
    object_type: str = Field(..., max_length=100)
    object_id: UUID
    step: str = Field(..., max_length=100)
    approver_id: Optional[UUID] = None
    comment: Optional[str] = None


class ApprovalDecision(BaseModel):
    decision: str = Field(..., max_length=50)
    comment: Optional[str] = None
    approver_id: Optional[UUID] = None


class ApprovalOut(BaseModel):
    id: UUID
    object_type: str
    object_id: UUID
    step: str
    approver_id: Optional[UUID] = None
    decision: str
    comment: Optional[str] = None
    decided_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
