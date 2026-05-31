from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SourceAssetBase(BaseModel):
    project_id: UUID
    source_type: str = Field(..., max_length=100)
    platform: Optional[str] = Field(None, max_length=200)
    url: Optional[str] = Field(None, max_length=1000)
    authority_level: str = Field(default="medium", max_length=50)
    crawlability: str = Field(default="unknown", max_length=50)
    status: str = Field(default="active", max_length=50)


class SourceAssetCreate(SourceAssetBase):
    pass


class SourceAssetUpdate(BaseModel):
    source_type: Optional[str] = Field(None, max_length=100)
    platform: Optional[str] = Field(None, max_length=200)
    url: Optional[str] = Field(None, max_length=1000)
    authority_level: Optional[str] = Field(None, max_length=50)
    crawlability: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field(None, max_length=50)


class SourceAssetOut(SourceAssetBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
