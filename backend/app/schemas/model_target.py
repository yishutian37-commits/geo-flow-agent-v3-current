from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ModelTargetBase(BaseModel):
    project_id: UUID
    product_name: str = Field(..., max_length=200)
    supported_mechanisms: Optional[str] = None
    search_backend: Optional[str] = Field(None, max_length=200)
    search_backend_confidence: str = Field(default="medium", max_length=50)
    search_backend_evidence: Optional[str] = None
    last_verified_at: Optional[datetime] = None
    api_available: bool = False
    access_method: Optional[str] = Field(None, max_length=100)
    recognition_mode: str = Field(default="text", max_length=50)
    web_url: Optional[str] = Field(None, max_length=1000)
    input_selector: Optional[str] = Field(None, max_length=500)
    submit_selector: Optional[str] = Field(None, max_length=500)
    response_selector: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None


class ModelTargetCreate(ModelTargetBase):
    pass


class ModelTargetUpdate(BaseModel):
    product_name: Optional[str] = Field(None, max_length=200)
    supported_mechanisms: Optional[str] = None
    search_backend: Optional[str] = Field(None, max_length=200)
    search_backend_confidence: Optional[str] = Field(None, max_length=50)
    search_backend_evidence: Optional[str] = None
    last_verified_at: Optional[datetime] = None
    api_available: Optional[bool] = None
    access_method: Optional[str] = Field(None, max_length=100)
    recognition_mode: Optional[str] = Field(None, max_length=50)
    web_url: Optional[str] = Field(None, max_length=1000)
    input_selector: Optional[str] = Field(None, max_length=500)
    submit_selector: Optional[str] = Field(None, max_length=500)
    response_selector: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None


class ModelTargetOut(ModelTargetBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
