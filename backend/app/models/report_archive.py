import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.types import UUIDString


class ReportArchive(Base):
    __tablename__ = "report_archives"

    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(UUIDString, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    report_type = Column(String(50), nullable=False)
    title = Column(String(300), nullable=False)
    run_id = Column(UUIDString, nullable=True)
    baseline_run_id = Column(UUIDString, nullable=True)
    time_window_days = Column(Integer, default=30, nullable=False)
    acceptance_ready = Column(Boolean, default=False, nullable=False)
    confidence_level = Column(String(50), nullable=True)
    sample_count = Column(Integer, default=0, nullable=False)
    markdown = Column(Text, nullable=False)
    payload_json = Column(Text, nullable=False)
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    project = relationship("Project", back_populates="report_archives")

    __table_args__ = (
        Index("ix_report_archives_project_id", "project_id"),
        Index("ix_report_archives_report_type", "report_type"),
        Index("ix_report_archives_created_at", "created_at"),
    )
