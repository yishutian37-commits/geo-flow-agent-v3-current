import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from sqlalchemy.orm import relationship
from app.core.database import Base

class Approval(Base):
    __tablename__ = "approvals"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    object_type = Column(String(100), nullable=False)
    object_id = Column(UUIDString, nullable=False)
    step = Column(String(100), nullable=False)
    approver_id = Column(UUIDString, ForeignKey("users.id"), nullable=True)
    decision = Column(String(50), default="pending", nullable=False)
    comment = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    approver = relationship("User", back_populates="approvals")
