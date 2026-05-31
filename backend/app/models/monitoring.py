import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Integer, Boolean, Text
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from sqlalchemy.orm import relationship
from app.core.database import Base

class MonitoringRun(Base):
    __tablename__ = "monitoring_runs"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(UUIDString, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    run_type = Column(String(100), nullable=False)
    mechanism_type = Column(String(50), nullable=False)
    model_target_id = Column(UUIDString, ForeignKey("model_targets.id"), nullable=False)
    call_mode_detail = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime(timezone=True), nullable=True)
    sample_policy = Column(String(50), default="mvp", nullable=False)
    status = Column(String(50), default="running", nullable=False)
    estimated_api_cost = Column(Numeric(15, 4), nullable=True)
    actual_api_cost = Column(Numeric(15, 4), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    project = relationship("Project", back_populates="monitoring_runs")
    model_target = relationship("ModelTarget", back_populates="monitoring_runs")
    samples = relationship("MonitoringSample", back_populates="run", cascade="all, delete-orphan")

class MonitoringSample(Base):
    __tablename__ = "monitoring_samples"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(UUIDString, ForeignKey("monitoring_runs.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUIDString, ForeignKey("questions.id"), nullable=False)
    answer_text = Column(Text, nullable=True)
    brand_mentioned = Column(Boolean, default=False)
    recommended = Column(Boolean, default=False)
    position = Column(Integer, nullable=True)
    list_length = Column(Integer, nullable=True)
    visibility_score = Column(Numeric(5, 4), nullable=True)
    explicit_citations = Column(Integer, default=0)
    inferred_source_matches = Column(Integer, default=0)
    sources_json = Column(Text, nullable=True)
    analysis_json = Column(Text, nullable=True)
    screenshot_url = Column(String(1000), nullable=True)
    sampled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    run = relationship("MonitoringRun", back_populates="samples")
    question = relationship("Question", back_populates="monitoring_samples")
    sentiment_records = relationship("SentimentRecord", back_populates="sample", cascade="all, delete-orphan")
