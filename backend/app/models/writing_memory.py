import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.types import UUIDString


class ContentFeedback(Base):
    __tablename__ = "content_feedbacks"

    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(UUIDString, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    draft_id = Column(UUIDString, ForeignKey("content_drafts.id", ondelete="SET NULL"), nullable=True)
    feedback_type = Column(String(50), nullable=False)
    rating = Column(String(50), nullable=True)
    comment = Column(Text, nullable=True)
    rule_text = Column(Text, nullable=True)
    rule_category = Column(String(100), nullable=True)
    diff_summary = Column(Text, nullable=True)
    source = Column(String(50), default="manual", nullable=False)
    is_folded = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="content_feedbacks")


class WritingProfile(Base):
    __tablename__ = "writing_profiles"

    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(UUIDString, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    style_preferences = Column(Text, nullable=True)
    title_preferences = Column(Text, nullable=True)
    constraints = Column(Text, nullable=True)
    platform_habits = Column(Text, nullable=True)
    feedback_count = Column(Integer, default=0, nullable=False)
    last_folded_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project = relationship("Project", back_populates="writing_profile")

    __table_args__ = (UniqueConstraint("project_id", name="uq_writing_profiles_project_id"),)
