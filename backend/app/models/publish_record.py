import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Text
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from sqlalchemy.orm import relationship
from app.core.database import Base

class PublishRecord(Base):
    __tablename__ = "publish_records"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(UUIDString, ForeignKey("content_tasks.id"), nullable=False)
    draft_id = Column(UUIDString, ForeignKey("content_drafts.id", ondelete="SET NULL"), nullable=True)
    draft_version = Column(String(20), nullable=True)
    channel_account_id = Column(UUIDString, ForeignKey("channel_accounts.id"), nullable=True)
    platform = Column(String(200), nullable=False)
    url = Column(String(1000), nullable=True)
    title = Column(String(500), nullable=True)
    content_type = Column(String(100), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    publisher_id = Column(UUIDString, ForeignKey("users.id"), nullable=True)
    status = Column(String(50), default="pending", nullable=False)
    is_indexed = Column(Boolean, default=False)
    first_indexed_at = Column(DateTime(timezone=True), nullable=True)
    related_content_task_id = Column(UUIDString, nullable=True)
    related_question_group_id = Column(UUIDString, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    task = relationship("ContentTask", back_populates="publish_records")
    draft = relationship("ContentDraft")
    publisher = relationship("User", back_populates="publish_records")
