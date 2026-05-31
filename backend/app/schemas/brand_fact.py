from datetime import datetime
from typing import Any, Dict, Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class BrandFactBase(BaseModel):
    fact_type: str = Field(..., max_length=100)
    value: str
    source: Optional[str] = Field(None, max_length=500)
    evidence_file_url: Optional[str] = Field(None, max_length=1000)
    evidence_type: Optional[str] = Field(None, max_length=100)
    fact_scope: str = Field(default="public", max_length=50)
    public_wording: Optional[str] = None
    internal_note: Optional[str] = None
    valid_until: Optional[datetime] = None
    risk_level: str = Field(default="low", max_length=20)


class BrandFactCreate(BrandFactBase):
    brand_id: UUID


class BrandFactOut(BrandFactBase):
    id: UUID
    brand_id: UUID
    confirmed_by: Optional[UUID] = None
    confirmed_at: Optional[datetime] = None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BrandFactConfirmRequest(BaseModel):
    confirmed_by: Optional[UUID] = None
    public_wording: Optional[str] = None
    confirmation_note: Optional[str] = None
    evidence_file_url: Optional[str] = Field(None, max_length=1000)
    evidence_type: Optional[str] = Field(None, max_length=100)


class BrandFactUpdate(BaseModel):
    value: Optional[str] = None
    source: Optional[str] = Field(None, max_length=500)
    evidence_file_url: Optional[str] = Field(None, max_length=1000)
    evidence_type: Optional[str] = Field(None, max_length=100)
    fact_scope: Optional[str] = Field(None, max_length=50)
    public_wording: Optional[str] = None
    internal_note: Optional[str] = None
    valid_until: Optional[datetime] = None
    risk_level: Optional[str] = Field(None, max_length=20)


class BrandFactEventOut(BaseModel):
    id: UUID
    fact_id: UUID
    action: str
    actor_id: Optional[UUID] = None
    previous_status: Optional[str] = None
    new_status: Optional[str] = None
    snapshot: Optional[Dict[str, Any]] = None
    note: Optional[str] = None
    created_at: datetime


class ExtractFromCorpusRequest(BaseModel):
    corpus_item_id: UUID
    suggested_facts: List[dict] = []


class ExtractFromTextRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    brand_id: UUID
    content: str = Field(..., min_length=20)
    source: Optional[str] = Field(default="pasted_enterprise_material", max_length=500)
    model_id: Optional[str] = None
    max_facts: int = Field(default=24, ge=1, le=50)
