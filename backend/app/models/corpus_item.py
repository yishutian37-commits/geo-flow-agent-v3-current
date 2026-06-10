import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Numeric, Index
from app.core.types import UUIDString
# from sqlalchemy.dialects.postgresql import UUID  # SQLite compat
from sqlalchemy.orm import relationship
from app.core.database import Base

class CorpusItem(Base):
    __tablename__ = "corpus_items"
    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(UUIDString, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    source_type = Column(String(100), nullable=True)
    source_url = Column(String(1000), nullable=True)
    tags = Column(Text, nullable=True)
    knowledge_layer = Column(String(100), nullable=False, default="basic_info")
    business_use = Column(String(100), nullable=False, default="general")
    evidence_level = Column(String(100), nullable=False, default="unverified")
    reusable_scope = Column(String(100), nullable=False, default="project")
    contains_factual_claim = Column(Boolean, default=False)
    confidence = Column(Numeric(3, 2), nullable=True)
    source_fact_candidate = Column(UUIDString, ForeignKey("brand_facts.id"), nullable=True)
    created_by = Column(UUIDString, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    project = relationship("Project", back_populates="corpus_items")
    __table_args__ = (
        Index("ix_corpus_items_project_id", "project_id"),
        Index("ix_corpus_items_contains_factual_claim", "contains_factual_claim"),
        Index("ix_corpus_items_knowledge_layer", "knowledge_layer"),
        Index("ix_corpus_items_business_use", "business_use"),
        Index("ix_corpus_items_evidence_level", "evidence_level"),
        Index("ix_corpus_items_reusable_scope", "reusable_scope"),
    )
