import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.types import UUIDString


class BrandFactEvent(Base):
    __tablename__ = "brand_fact_events"

    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    fact_id = Column(UUIDString, ForeignKey("brand_facts.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    actor_id = Column(UUIDString, ForeignKey("users.id"), nullable=True)
    previous_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=True)
    snapshot_json = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    fact = relationship("BrandFact")
    actor = relationship("User")

    __table_args__ = (
        Index("ix_brand_fact_events_fact_created", "fact_id", "created_at"),
    )
