import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Index
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from app.core.database import Base

class ChannelAccount(Base):
    __tablename__ = "channel_accounts"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(UUIDString, nullable=False, index=True)
    platform = Column(String(200), nullable=False)
    account_name = Column(String(200), nullable=False)
    account_type = Column(String(100), nullable=False)
    owner_tenant_id = Column(UUIDString, nullable=True)
    login_required = Column(Boolean, default=True)
    publish_permission = Column(Boolean, default=False)
    publisher_url = Column(String(1000), nullable=True)
    title_selector = Column(String(500), nullable=True)
    body_selector = Column(String(500), nullable=True)
    risk_level = Column(String(20), default="low", nullable=False)
    last_publish_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), default="normal", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        Index("ix_channel_accounts_platform", "platform"),
        Index("ix_channel_accounts_status", "status"),
    )
