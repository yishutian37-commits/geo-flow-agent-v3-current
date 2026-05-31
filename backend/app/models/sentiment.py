import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from sqlalchemy.orm import relationship
from app.core.database import Base

class SentimentRecord(Base):
    __tablename__ = "sentiment_records"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    sample_id = Column(UUIDString, ForeignKey("monitoring_samples.id", ondelete="CASCADE"), nullable=False)
    sentiment_type = Column(String(100), nullable=False)
    severity = Column(String(20), default="medium", nullable=False)
    source = Column(String(500), nullable=True)
    suggested_action = Column(Text, nullable=True)
    status = Column(String(50), default="open", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    sample = relationship("MonitoringSample", back_populates="sentiment_records")
