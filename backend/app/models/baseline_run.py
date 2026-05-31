import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from sqlalchemy.orm import relationship
from app.core.database import Base

class BaselineRun(Base):
    __tablename__ = "baseline_runs"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(UUIDString, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUIDString, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    model_target_id = Column(UUIDString, ForeignKey("model_targets.id", ondelete="CASCADE"), nullable=False)
    mechanism_type = Column(String(50), nullable=False)
    call_mode_detail = Column(Text, nullable=True)
    sample_policy = Column(String(50), default="acceptance", nullable=False)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime(timezone=True), nullable=True)
    confidence_level = Column(String(20), default="medium", nullable=False)
    valid_status = Column(String(50), default="valid", nullable=False)
    invalid_reason = Column(Text, nullable=True)
    project = relationship("Project", back_populates="baseline_runs")
    question = relationship("Question", back_populates="baseline_runs")
    model_target = relationship("ModelTarget", back_populates="baseline_runs")
