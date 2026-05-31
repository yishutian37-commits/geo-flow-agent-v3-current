import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from sqlalchemy.orm import relationship
from app.core.database import Base

class ContentDraft(Base):
    __tablename__ = "content_drafts"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(UUIDString, ForeignKey("content_tasks.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=True)
    body = Column(Text, nullable=True)
    version = Column(String(20), default="1.0", nullable=False)
    status = Column(String(50), default="draft", nullable=False)
    risk_level = Column(String(20), default="low", nullable=False)
    fact_refs = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    task = relationship("ContentTask", back_populates="drafts")
    compliance_checks = relationship("ComplianceCheck", back_populates="draft", cascade="all, delete-orphan")
