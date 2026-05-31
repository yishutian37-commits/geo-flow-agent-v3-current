import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, String, DateTime, ForeignKey, Integer, Text, Index
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from sqlalchemy.orm import relationship
from app.core.database import Base

class QuestionGroup(Base):
    __tablename__ = "question_groups"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(UUIDString, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    layer = Column(String(50), nullable=False)
    intent_name = Column(String(200), nullable=False)
    representative_question = Column(String(1000), nullable=False)
    priority = Column(Integer, default=50)
    status = Column(String(50), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    project = relationship("Project", back_populates="question_groups")
    questions = relationship("Question", back_populates="group", cascade="all, delete-orphan")
    __table_args__ = (
        Index("ix_question_groups_project_id", "project_id"),
        Index("ix_question_groups_layer", "layer"),
    )

class Question(Base):
    __tablename__ = "questions"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(UUIDString, ForeignKey("question_groups.id", ondelete="CASCADE"), nullable=False)
    question_text = Column(String(2000), nullable=False)
    question_type = Column(String(100), default="brand_reputation", nullable=False)
    tags = Column(Text, nullable=True)
    priority = Column(Integer, default=50)
    sample_policy = Column(String(50), default="mvp", nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    focus = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    group = relationship("QuestionGroup", back_populates="questions")
    baseline_runs = relationship("BaselineRun", back_populates="question")
    monitoring_samples = relationship("MonitoringSample", back_populates="question")
    __table_args__ = (
        Index("ix_questions_group_id", "group_id"),
    )
