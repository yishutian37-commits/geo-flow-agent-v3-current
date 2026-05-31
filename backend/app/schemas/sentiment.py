from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SentimentRecordBase(BaseModel):
    sample_id: UUID
    sentiment_type: str = Field(..., max_length=100)
    severity: str = Field(default="medium", max_length=20)
    source: Optional[str] = Field(None, max_length=500)
    suggested_action: Optional[str] = None
    status: str = Field(default="open", max_length=50)


class SentimentRecordCreate(SentimentRecordBase):
    pass


class SentimentRecordUpdate(BaseModel):
    sentiment_type: Optional[str] = Field(None, max_length=100)
    severity: Optional[str] = Field(None, max_length=20)
    source: Optional[str] = Field(None, max_length=500)
    suggested_action: Optional[str] = None
    status: Optional[str] = Field(None, max_length=50)


class SentimentRecordOut(SentimentRecordBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
