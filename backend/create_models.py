import os

base_path = r"C:\Users\Administrator\Desktop\geo-flow-agent-v2\backend\app\models"

files = {}

files["brand.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class Brand(Base):
    __tablename__ = "brands"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    brand_name = Column(String(200), nullable=False)
    company_name = Column(String(200), nullable=True)
    aliases = Column(Text, nullable=True)
    official_site = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    project = relationship("Project", back_populates="brands")
    brand_facts = relationship("BrandFact", back_populates="brand", cascade="all, delete-orphan")
"""

files["brand_fact.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class BrandFact(Base):
    __tablename__ = "brand_facts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(UUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    fact_type = Column(String(100), nullable=False)
    value = Column(Text, nullable=False)
    source = Column(String(500), nullable=True)
    evidence_file_url = Column(String(1000), nullable=True)
    evidence_type = Column(String(100), nullable=True)
    fact_scope = Column(String(50), default="public", nullable=False)
    public_wording = Column(Text, nullable=True)
    internal_note = Column(Text, nullable=True)
    confirmed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
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
"""

files["corpus_item.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Numeric, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class CorpusItem(Base):
    __tablename__ = "corpus_items"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    source_type = Column(String(100), nullable=True)
    tags = Column(Text, nullable=True)
    contains_factual_claim = Column(Boolean, default=False)
    confidence = Column(Numeric(3, 2), nullable=True)
    source_fact_candidate = Column(UUID(as_uuid=True), ForeignKey("brand_facts.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    project = relationship("Project", back_populates="corpus_items")
    __table_args__ = (
        Index("ix_corpus_items_project_id", "project_id"),
        Index("ix_corpus_items_contains_factual_claim", "contains_factual_claim"),
    )
"""

files["source_asset.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class SourceAsset(Base):
    __tablename__ = "source_assets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
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
"""

files["channel_account.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class ChannelAccount(Base):
    __tablename__ = "channel_accounts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    platform = Column(String(200), nullable=False)
    account_name = Column(String(200), nullable=False)
    account_type = Column(String(100), nullable=False)
    owner_tenant_id = Column(UUID(as_uuid=True), nullable=True)
    login_required = Column(Boolean, default=True)
    publish_permission = Column(Boolean, default=False)
    risk_level = Column(String(20), default="low", nullable=False)
    last_publish_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), default="normal", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        Index("ix_channel_accounts_platform", "platform"),
        Index("ix_channel_accounts_status", "status"),
    )
"""

files["question.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class QuestionGroup(Base):
    __tablename__ = "question_groups"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    layer = Column(String(50), nullable=False)
    intent_name = Column(String(200), nullable=False)
    representative_question = Column(String(1000), nullable=False)
    priority = Column(Integer, default=50)
    status = Column(String(50), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    project = relationship("Project", back_populates="question_groups")
    questions = relationship("Question", back_populates="group", cascade="all, delete-orphan")
    __table_args__ = (
        Index("ix_question_groups_project_id", "project_id"),
        Index("ix_question_groups_layer", "layer"),
    )

class Question(Base):
    __tablename__ = "questions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id = Column(UUID(as_uuid=True), ForeignKey("question_groups.id", ondelete="CASCADE"), nullable=False)
    question_text = Column(String(2000), nullable=False)
    priority = Column(Integer, default=50)
    sample_policy = Column(String(50), default="mvp", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    group = relationship("QuestionGroup", back_populates="questions")
    baseline_runs = relationship("BaselineRun", back_populates="question")
    monitoring_samples = relationship("MonitoringSample", back_populates="question")
    __table_args__ = (
        Index("ix_questions_group_id", "group_id"),
    )
"""

files["model_target.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class ModelTarget(Base):
    __tablename__ = "model_targets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    product_name = Column(String(200), nullable=False)
    supported_mechanisms = Column(Text, nullable=True)
    search_backend = Column(String(200), nullable=True)
    search_backend_confidence = Column(String(50), default="medium", nullable=False)
    search_backend_evidence = Column(Text, nullable=True)
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
    api_available = Column(Boolean, default=False)
    access_method = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    project = relationship("Project", back_populates="model_targets")
    baseline_runs = relationship("BaselineRun", back_populates="model_target")
    monitoring_runs = relationship("MonitoringRun", back_populates="model_target")
    __table_args__ = (
        Index("ix_model_targets_project_id", "project_id"),
    )
"""

files["baseline_run.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class BaselineRun(Base):
    __tablename__ = "baseline_runs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    model_target_id = Column(UUID(as_uuid=True), ForeignKey("model_targets.id", ondelete="CASCADE"), nullable=False)
    mechanism_type = Column(String(50), nullable=False)
    call_mode_detail = Column(Text, nullable=True)
    sample_policy = Column(String(50), default="acceptance", nullable=False)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime(timezone=True), nullable=True)
    confidence_level = Column(String(20), default="medium", nullable=False)
    valid_status = Column(String(50), default="valid", nullable=False)
    invalid_reason = Column(Text, nullable=True)
    project = relationship("Project", back_populates="baseline_runs")
    question = relationship("Question", back_populates="baseline_runs")
    model_target = relationship("ModelTarget", back_populates="baseline_runs")
"""

files["content_task.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class ContentTask(Base):
    __tablename__ = "content_tasks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(UUID(as_uuid=True), ForeignKey("question_groups.id"), nullable=True)
    content_type = Column(String(100), nullable=False)
    layer = Column(String(50), nullable=False)
    priority = Column(String(20), default="medium", nullable=False)
    assignee = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(String(50), default="draft", nullable=False)
    due_date = Column(DateTime(timezone=True), nullable=True)
    estimated_token_cost = Column(Numeric(15, 4), nullable=True)
    actual_token_cost = Column(Numeric(15, 4), nullable=True)
    estimated_api_cost = Column(Numeric(15, 4), nullable=True)
    actual_api_cost = Column(Numeric(15, 4), nullable=True)
    estimated_labor_minutes = Column(Numeric(10, 2), nullable=True)
    actual_labor_minutes = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    project = relationship("Project", back_populates="content_tasks")
    drafts = relationship("ContentDraft", back_populates="task", cascade="all, delete-orphan")
    publish_records = relationship("PublishRecord", back_populates="task")
"""

files["content_draft.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class ContentDraft(Base):
    __tablename__ = "content_drafts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("content_tasks.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=True)
    body = Column(Text, nullable=True)
    version = Column(String(20), default="1.0", nullable=False)
    status = Column(String(50), default="draft", nullable=False)
    risk_level = Column(String(20), default="low", nullable=False)
    fact_refs = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    task = relationship("ContentTask", back_populates="drafts")
    compliance_checks = relationship("ComplianceCheck", back_populates="draft", cascade="all, delete-orphan")
"""

files["compliance_check.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class ComplianceCheck(Base):
    __tablename__ = "compliance_checks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id = Column(UUID(as_uuid=True), ForeignKey("content_drafts.id", ondelete="CASCADE"), nullable=False)
    check_type = Column(String(100), nullable=False)
    result = Column(String(50), default="pending", nullable=False)
    issues = Column(Text, nullable=True)
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=True)
    draft = relationship("ContentDraft", back_populates="compliance_checks")
    reviewer = relationship("User", foreign_keys=[reviewer_id])
"""

files["approval.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class Approval(Base):
    __tablename__ = "approvals"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    object_type = Column(String(100), nullable=False)
    object_id = Column(UUID(as_uuid=True), nullable=False)
    step = Column(String(100), nullable=False)
    approver_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decision = Column(String(50), default="pending", nullable=False)
    comment = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    approver = relationship("User", back_populates="approvals")
"""

files["publish_record.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class PublishRecord(Base):
    __tablename__ = "publish_records"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("content_tasks.id"), nullable=False)
    channel_account_id = Column(UUID(as_uuid=True), ForeignKey("channel_accounts.id"), nullable=True)
    platform = Column(String(200), nullable=False)
    url = Column(String(1000), nullable=True)
    title = Column(String(500), nullable=True)
    content_type = Column(String(100), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    publisher_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(String(50), default="pending", nullable=False)
    is_indexed = Column(Boolean, default=False)
    first_indexed_at = Column(DateTime(timezone=True), nullable=True)
    related_content_task_id = Column(UUID(as_uuid=True), nullable=True)
    related_question_group_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    task = relationship("ContentTask", back_populates="publish_records")
    publisher = relationship("User", back_populates="publish_records")
"""

files["monitoring.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Integer, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class MonitoringRun(Base):
    __tablename__ = "monitoring_runs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    run_type = Column(String(100), nullable=False)
    mechanism_type = Column(String(50), nullable=False)
    model_target_id = Column(UUID(as_uuid=True), ForeignKey("model_targets.id"), nullable=False)
    call_mode_detail = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime(timezone=True), nullable=True)
    sample_policy = Column(String(50), default="mvp", nullable=False)
    status = Column(String(50), default="running", nullable=False)
    estimated_api_cost = Column(Numeric(15, 4), nullable=True)
    actual_api_cost = Column(Numeric(15, 4), nullable=True)
    project = relationship("Project", back_populates="monitoring_runs")
    model_target = relationship("ModelTarget", back_populates="monitoring_runs")
    samples = relationship("MonitoringSample", back_populates="run", cascade="all, delete-orphan")

class MonitoringSample(Base):
    __tablename__ = "monitoring_samples"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("monitoring_runs.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)
    answer_text = Column(Text, nullable=True)
    brand_mentioned = Column(Boolean, default=False)
    recommended = Column(Boolean, default=False)
    position = Column(Integer, nullable=True)
    list_length = Column(Integer, nullable=True)
    visibility_score = Column(Numeric(5, 4), nullable=True)
    explicit_citations = Column(Integer, default=0)
    inferred_source_matches = Column(Integer, default=0)
    screenshot_url = Column(String(1000), nullable=True)
    sampled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    run = relationship("MonitoringRun", back_populates="samples")
    question = relationship("Question", back_populates="monitoring_samples")
    sentiment_records = relationship("SentimentRecord", back_populates="sample", cascade="all, delete-orphan")
"""

files["sentiment.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class SentimentRecord(Base):
    __tablename__ = "sentiment_records"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sample_id = Column(UUID(as_uuid=True), ForeignKey("monitoring_samples.id", ondelete="CASCADE"), nullable=False)
    sentiment_type = Column(String(100), nullable=False)
    severity = Column(String(20), default="medium", nullable=False)
    source = Column(String(500), nullable=True)
    suggested_action = Column(Text, nullable=True)
    status = Column(String(50), default="open", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    sample = relationship("MonitoringSample", back_populates="sentiment_records")
"""

files["recommendation.py"] = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class Recommendation(Base):
    __tablename__ = "recommendations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    recommendation_type = Column(String(100), nullable=False)
    reason = Column(Text, nullable=False)
    priority = Column(String(20), default="medium", nullable=False)
    linked_metric = Column(String(200), nullable=True)
    status = Column(String(50), default="open", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    project = relationship("Project", back_populates="recommendations")
"""

for filename, content in files.items():
    filepath = os.path.join(base_path, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Created: {filepath}")

print("\nAll model files created successfully.")
