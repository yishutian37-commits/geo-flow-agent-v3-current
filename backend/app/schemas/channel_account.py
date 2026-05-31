from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChannelAccountBase(BaseModel):
    platform: str = Field(..., max_length=200)
    account_name: str = Field(..., max_length=200)
    account_type: str = Field(default="owned", max_length=100)
    login_required: bool = True
    publish_permission: bool = False
    publisher_url: Optional[str] = Field(default=None, max_length=1000)
    title_selector: Optional[str] = Field(default=None, max_length=500)
    body_selector: Optional[str] = Field(default=None, max_length=500)
    risk_level: str = Field(default="low", max_length=20)
    status: str = Field(default="normal", max_length=50)


class ChannelAccountCreate(ChannelAccountBase):
    tenant_id: Optional[UUID] = None
    owner_tenant_id: Optional[UUID] = None


class ChannelAccountUpdate(BaseModel):
    platform: Optional[str] = Field(None, max_length=200)
    account_name: Optional[str] = Field(None, max_length=200)
    account_type: Optional[str] = Field(None, max_length=100)
    owner_tenant_id: Optional[UUID] = None
    login_required: Optional[bool] = None
    publish_permission: Optional[bool] = None
    publisher_url: Optional[str] = Field(None, max_length=1000)
    title_selector: Optional[str] = Field(None, max_length=500)
    body_selector: Optional[str] = Field(None, max_length=500)
    risk_level: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = Field(None, max_length=50)


class ChannelAccountOut(ChannelAccountBase):
    id: UUID
    tenant_id: UUID
    owner_tenant_id: Optional[UUID] = None
    last_publish_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
