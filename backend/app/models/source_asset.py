import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from sqlalchemy.orm import relationship
from app.core.database import Base

class SourceAsset(Base):
    __tablename__ = "source_assets"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(UUIDString, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(String(100), nullable=False)
    platform = Column(String(200), nullable=True)
    url = Column(String(1000), nullable=True)
    authority_level = Column(String(50), default="medium", nullable=False)
    crawlability = Column(String(50), default="unknown", nullable=False)
    status = Column(String(50), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    project = relationship("Project", back_populates="source_assets")
    __table_args__ = (
        Index("ix_source_assets_project_id", "project_id"),
        Index("ix_source_assets_source_type", "source_type"),
    )
