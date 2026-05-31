from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, EmailStr


class UserBase(BaseModel):
    username: str = Field(..., max_length=100)
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=100)
    role: str = Field(default="viewer", max_length=50)
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=100)
    role: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class UserPasswordUpdate(BaseModel):
    password: str = Field(..., min_length=6)


class UserOut(UserBase):
    id: UUID
    tenant_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class BootstrapAdminRequest(BaseModel):
    username: str = Field(default="admin", max_length=100)
    email: EmailStr = "admin@geoflow.app"
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = Field(default="Local Admin", max_length=100)
