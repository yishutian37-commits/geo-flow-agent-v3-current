import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Index
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from sqlalchemy.orm import relationship
from app.core.database import Base

class BrandFact(Base):
    __tablename__ = "brand_facts"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id = Column(UUIDString, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    fact_type = Column(String(100), nullable=False)
    value = Column(Text, nullable=False)
    source = Column(String(500), nullable=True)
    evidence_file_url = Column(String(1000), nullable=True)
    evidence_type = Column(String(100), nullable=True)
    fact_scope = Column(String(50), default="public", nullable=False)
    public_wording = Column(Text, nullable=True)
    internal_note = Column(Text, nullable=True)
    confirmed_by = Column(UUIDString, ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    risk_level = Column(String(20), default="low", nullable=False)
    status = Column(String(50), default="draft", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    brand = relationship("Brand", back_populates="brand_facts")
    confirmed_by_user = relationship("User", foreign_keys=[confirmed_by])
    __table_args__ = (
        Index("ix_brand_facts_brand_id", "brand_id"),
        Index("ix_brand_facts_status", "status"),
        Index("ix_brand_facts_fact_type", "fact_type"),
    )
