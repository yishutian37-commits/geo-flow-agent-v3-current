import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, Index, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.types import UUIDString


class ExperienceSkill(Base):
    __tablename__ = "experience_skills"

    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    scope = Column(String(50), default="project", nullable=False)
    project_id = Column(UUIDString, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    industry = Column(String(100), nullable=True)
    trigger_scene = Column(String(100), default="article_writing", nullable=False)
    skill_type = Column(String(100), default="rule", nullable=False)
    content = Column(Text, nullable=False)
    source_type = Column(String(100), nullable=True)
    source_refs_json = Column(Text, nullable=True)
    confidence = Column(Numeric(3, 2), nullable=True)
    usage_count = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    current_version = Column(Integer, default=1, nullable=False)
    status = Column(String(50), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project = relationship("Project", back_populates="experience_skills")
    versions = relationship("ExperienceSkillVersion", back_populates="skill", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_experience_skills_project_id", "project_id"),
        Index("ix_experience_skills_scope", "scope"),
        Index("ix_experience_skills_trigger_scene", "trigger_scene"),
        Index("ix_experience_skills_status", "status"),
    )


class ExperienceSkillVersion(Base):
    __tablename__ = "experience_skill_versions"

    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    skill_id = Column(UUIDString, ForeignKey("experience_skills.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    name = Column(String(200), nullable=False)
    scope = Column(String(50), nullable=False)
    project_id = Column(UUIDString, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    industry = Column(String(100), nullable=True)
    trigger_scene = Column(String(100), nullable=False)
    skill_type = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(50), nullable=False)
    confidence = Column(Numeric(3, 2), nullable=True)
    change_type = Column(String(100), default="revise", nullable=False)
    revision_reason = Column(Text, nullable=True)
    source_refs_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    skill = relationship("ExperienceSkill", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("skill_id", "version", name="uq_experience_skill_versions_skill_version"),
        Index("ix_experience_skill_versions_skill_id", "skill_id"),
    )


class ExperienceSkillSuggestion(Base):
    __tablename__ = "experience_skill_suggestions"

    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(UUIDString, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    suggested_scope = Column(String(50), default="project", nullable=False)
    industry = Column(String(100), nullable=True)
    trigger_scene = Column(String(100), default="article_writing", nullable=False)
    skill_type = Column(String(100), default="rule", nullable=False)
    name = Column(String(200), nullable=True)
    suggestion_text = Column(Text, nullable=False)
    reason = Column(Text, nullable=True)
    evidence = Column(Text, nullable=True)
    risk_note = Column(Text, nullable=True)
    source_type = Column(String(100), nullable=True)
    source_refs_json = Column(Text, nullable=True)
    confidence = Column(Numeric(3, 2), nullable=True)
    status = Column(String(50), default="pending", nullable=False)
    approved_skill_id = Column(UUIDString, ForeignKey("experience_skills.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    project = relationship("Project", back_populates="experience_skill_suggestions")
    approved_skill = relationship("ExperienceSkill")

    __table_args__ = (
        Index("ix_experience_skill_suggestions_project_id", "project_id"),
        Index("ix_experience_skill_suggestions_scope", "suggested_scope"),
        Index("ix_experience_skill_suggestions_trigger_scene", "trigger_scene"),
        Index("ix_experience_skill_suggestions_status", "status"),
    )
