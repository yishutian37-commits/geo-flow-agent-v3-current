from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class BrandBase(BaseModel):
    brand_name: str = Field(..., max_length=200)
    company_name: Optional[str] = Field(None, max_length=200)
    aliases: Optional[str] = None
    official_site: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None


class BrandCreate(BrandBase):
    project_id: UUID


class BrandOut(BrandBase):
    id: UUID
    project_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
