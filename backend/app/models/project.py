import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Numeric, ForeignKey, Text, Index
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from sqlalchemy.orm import relationship

from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    industry = Column(String(100), nullable=False)
    region = Column(String(100), nullable=False)
    owner_id = Column(UUIDString, ForeignKey("users.id"), nullable=True)
    status = Column(String(50), default="active", nullable=False)
    budget = Column(Numeric(15, 2), nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    target_ai_products = Column(Text, nullable=True)  # JSON list of model_target_ids
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    owner = relationship("User", back_populates="projects")
    brands = relationship("Brand", back_populates="project", cascade="all, delete-orphan")
    corpus_items = relationship("CorpusItem", back_populates="project", cascade="all, delete-orphan")
    source_assets = relationship("SourceAsset", back_populates="project", cascade="all, delete-orphan")
    question_groups = relationship("QuestionGroup", back_populates="project", cascade="all, delete-orphan")
    model_targets = relationship("ModelTarget", back_populates="project", cascade="all, delete-orphan")
    baseline_runs = relationship("BaselineRun", back_populates="project", cascade="all, delete-orphan")
    content_tasks = relationship("ContentTask", back_populates="project", cascade="all, delete-orphan")
    monitoring_runs = relationship("MonitoringRun", back_populates="project", cascade="all, delete-orphan")
    report_archives = relationship("ReportArchive", back_populates="project", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="project", cascade="all, delete-orphan")
    content_feedbacks = relationship("ContentFeedback", back_populates="project", cascade="all, delete-orphan")
    writing_profile = relationship("WritingProfile", back_populates="project", cascade="all, delete-orphan", uselist=False)
    experience_skills = relationship("ExperienceSkill", back_populates="project", cascade="all, delete-orphan")
    experience_skill_suggestions = relationship("ExperienceSkillSuggestion", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_projects_industry", "industry"),
        Index("ix_projects_region", "region"),
        Index("ix_projects_status", "status"),
    )
