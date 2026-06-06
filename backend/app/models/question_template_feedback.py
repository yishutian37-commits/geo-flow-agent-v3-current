import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, String, Text

from app.core.database import Base
from app.core.types import UUIDString


class QuestionTemplateFeedback(Base):
    __tablename__ = "question_template_feedbacks"

    id = Column(UUIDString, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(UUIDString, nullable=False)
    group_id = Column(UUIDString, nullable=True)
    question_id = Column(UUIDString, nullable=True)
    industry = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    before_text = Column(Text, nullable=True)
    after_text = Column(Text, nullable=True)
    before_payload = Column(Text, nullable=True)
    after_payload = Column(Text, nullable=True)
    status = Column(String(50), default="pending", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    applied_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_question_template_feedbacks_industry_status", "industry", "status"),
        Index("ix_question_template_feedbacks_project_id", "project_id"),
        Index("ix_question_template_feedbacks_created_at", "created_at"),
    )
