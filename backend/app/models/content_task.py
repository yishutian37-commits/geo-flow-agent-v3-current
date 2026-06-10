import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Text
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from sqlalchemy.orm import relationship
from app.core.database import Base

class ContentTask(Base):
    __tablename__ = "content_tasks"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(UUIDString, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(UUIDString, ForeignKey("question_groups.id"), nullable=True)
    question_id = Column(UUIDString, ForeignKey("questions.id", ondelete="SET NULL"), nullable=True)
    knowledge_asset_ids = Column(Text, nullable=True)
    content_type = Column(String(100), nullable=False)
    layer = Column(String(50), nullable=False)
    priority = Column(String(20), default="medium", nullable=False)
    assignee = Column(UUIDString, ForeignKey("users.id"), nullable=True)
    status = Column(String(50), default="draft", nullable=False)
    due_date = Column(DateTime(timezone=True), nullable=True)
    estimated_token_cost = Column(Numeric(15, 4), nullable=True)
    actual_token_cost = Column(Numeric(15, 4), nullable=True)
    estimated_api_cost = Column(Numeric(15, 4), nullable=True)
    actual_api_cost = Column(Numeric(15, 4), nullable=True)
    estimated_labor_minutes = Column(Numeric(10, 2), nullable=True)
    actual_labor_minutes = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    project = relationship("Project", back_populates="content_tasks")
    question = relationship("Question")
    drafts = relationship("ContentDraft", back_populates="task", cascade="all, delete-orphan")
    publish_records = relationship("PublishRecord", back_populates="task")
