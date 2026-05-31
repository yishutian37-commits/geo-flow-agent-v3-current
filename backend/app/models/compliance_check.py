import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from sqlalchemy.orm import relationship
from app.core.database import Base

class ComplianceCheck(Base):
    __tablename__ = "compliance_checks"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    draft_id = Column(UUIDString, ForeignKey("content_drafts.id", ondelete="CASCADE"), nullable=False)
    check_type = Column(String(100), nullable=False)
    result = Column(String(50), default="pending", nullable=False)
    issues = Column(Text, nullable=True)
    reviewer_id = Column(UUIDString, ForeignKey("users.id"), nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=True)
    draft = relationship("ContentDraft", back_populates="compliance_checks")
    reviewer = relationship("User", foreign_keys=[reviewer_id])
