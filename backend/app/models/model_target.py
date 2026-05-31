import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Text, Index
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from sqlalchemy.orm import relationship
from app.core.database import Base

class ModelTarget(Base):
    __tablename__ = "model_targets"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(UUIDString, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    product_name = Column(String(200), nullable=False)
    supported_mechanisms = Column(Text, nullable=True)
    search_backend = Column(String(200), nullable=True)
    search_backend_confidence = Column(String(50), default="medium", nullable=False)
    search_backend_evidence = Column(Text, nullable=True)
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
    api_available = Column(Boolean, default=False)
    access_method = Column(String(100), nullable=True)
    recognition_mode = Column(String(50), default="text", nullable=False)
    web_url = Column(String(1000), nullable=True)
    input_selector = Column(String(500), nullable=True)
    submit_selector = Column(String(500), nullable=True)
    response_selector = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    project = relationship("Project", back_populates="model_targets")
    baseline_runs = relationship("BaselineRun", back_populates="model_target")
    monitoring_runs = relationship("MonitoringRun", back_populates="model_target")
    __table_args__ = (
        Index("ix_model_targets_project_id", "project_id"),
    )
