import pytest
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.v1.endpoints.corpus_items import (
    CorpusItemCreate,
    CorpusIngestRequest,
    CorpusItemUpdate,
    create_corpus_item,
    ingest_corpus_items,
    list_corpus_items,
    update_corpus_item,
)
from app.api.v1.endpoints.monitoring import (
    SampleReviewKnowledgeRequest,
    create_review_knowledge_from_sample,
)
from app.core.database import Base
from app.models.experience_skill import ExperienceSkillSuggestion
from app.models.question import Question, QuestionGroup
from app.schemas.project import ProjectCreate
from app.services.monitoring_service import MonitoringService
from app.services.project_knowledge_service import ProjectKnowledgeService
from app.services.project_service import ProjectService


@pytest.mark.asyncio
async def test_corpus_item_keeps_project_knowledge_metadata_and_filters():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await ProjectService(db).create_project(
                ProjectCreate(
                    name="项目知识库测试品牌",
                    industry="local_service",
                    region="包头",
                    budget=1000,
                    target_ai_products="Kimi,DeepSeek",
                    notes="用于验证项目知识库结构化字段",
                ),
                owner_id=None,
            )

            created = await create_corpus_item(
                CorpusItemCreate(
                    project_id=project.id,
                    title="客户案例素材",
                    source_type="case",
                    source_url="https://example.com/cases/1",
                    tags="案例,口碑,转化",
                    content="客户使用服务后形成了可公开引用的结果和评价。",
                    contains_factual_claim=True,
                    knowledge_layer="story",
                    business_use="content_writing",
                    evidence_level="verified",
                    reusable_scope="project",
                ),
                db=db,
            )

            assert created["knowledge_layer"] == "story"
            assert created["business_use"] == "content_writing"
            assert created["evidence_level"] == "verified"
            assert created["reusable_scope"] == "project"
            assert created["source_url"] == "https://example.com/cases/1"

            story_items = await list_corpus_items(
                project_id=project.id,
                contains_factual_claim=None,
                source_type=None,
                knowledge_layer="story",
                business_use="content_writing",
                evidence_level="verified",
                reusable_scope="project",
                skip=0,
                limit=100,
                db=db,
            )
            assert [item["id"] for item in story_items] == [created["id"]]

            updated = await update_corpus_item(
                item_id=created["id"],
                payload=CorpusItemUpdate(
                    knowledge_layer="review_data",
                    business_use="monitoring_review",
                    evidence_level="internal",
                    reusable_scope="industry",
                    source_url="https://example.com/review/1",
                ),
                db=db,
            )

            assert updated["knowledge_layer"] == "review_data"
            assert updated["business_use"] == "monitoring_review"
            assert updated["evidence_level"] == "internal"
            assert updated["reusable_scope"] == "industry"
            assert updated["source_url"] == "https://example.com/review/1"

            old_filter_items = await list_corpus_items(
                project_id=project.id,
                contains_factual_claim=None,
                source_type=None,
                knowledge_layer="story",
                business_use=None,
                evidence_level=None,
                reusable_scope=None,
                skip=0,
                limit=100,
                db=db,
            )
            assert old_filter_items == []

            review_items = await list_corpus_items(
                project_id=project.id,
                contains_factual_claim=None,
                source_type=None,
                knowledge_layer="review_data",
                business_use="monitoring_review",
                evidence_level="internal",
                reusable_scope="industry",
                skip=0,
                limit=100,
                db=db,
            )
            assert [item["id"] for item in review_items] == [created["id"]]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_ai_ingest_splits_long_material_into_project_knowledge_items(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    class FakeLLMClient:
        async def chat(self, messages, temperature=0.1, max_tokens=4000, **kwargs):
            return SimpleNamespace(
                content="""{
                  "items": [
                    {
                      "title": "运营合格证编号",
                      "content": "企业持有民用无人驾驶航空器运营合格证，编号UAOC-O-HQ-20260128179。",
                      "knowledge_layer": "basic_info",
                      "business_use": "fact_extraction",
                      "evidence_level": "verified",
                      "tags": ["资质", "证书编号"],
                      "contains_factual_claim": true,
                      "reason": "这是可核验资质事实"
                    },
                    {
                      "title": "农牧局服务案例",
                      "content": "企业曾为准格尔旗农牧局提供农业植保无人机及操作培训。",
                      "knowledge_layer": "story",
                      "business_use": "content_writing",
                      "evidence_level": "verified",
                      "tags": ["案例", "农业植保"],
                      "contains_factual_claim": true,
                      "reason": "这是可用于内容写作的案例素材"
                    },
                    {
                      "title": "机构合规判断逻辑",
                      "content": "判断无人机培训机构是否合规时，应核验UOM可查、本地场地和本地考试能力。",
                      "knowledge_layer": "judgment",
                      "business_use": "question_generation",
                      "evidence_level": "internal",
                      "tags": ["判断逻辑", "合规"],
                      "contains_factual_claim": false,
                      "reason": "这是问题生成和内容规划可复用的判断框架"
                    }
                  ]
                }"""
            )

    monkeypatch.setattr(ProjectKnowledgeService, "_build_llm_client", lambda self, model_id=None: FakeLLMClient())

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await ProjectService(db).create_project(
                ProjectCreate(
                    name="AI分层入库测试项目",
                    industry="education_training",
                    region="包头",
                    budget=1000,
                    target_ai_products="Kimi,DeepSeek",
                    notes="用于验证AI分层入库",
                ),
                owner_id=None,
            )

            result = await ingest_corpus_items(
                CorpusIngestRequest(
                    project_id=project.id,
                    title="企业长资料",
                    content="企业资料包含资质编号、服务案例和无人机培训机构合规判断逻辑。",
                    source_type="brochure",
                    source_url="https://example.com/material",
                    max_items=10,
                ),
                db=db,
            )

            assert result["created"] == 3
            assert {item["knowledge_layer"] for item in result["items"]} == {
                "basic_info",
                "story",
                "judgment",
            }
            assert all(item["source_url"] == "https://example.com/material" for item in result["items"])

            story_items = await list_corpus_items(
                project_id=project.id,
                contains_factual_claim=None,
                source_type=None,
                knowledge_layer="story",
                business_use="content_writing",
                evidence_level="verified",
                reusable_scope=None,
                skip=0,
                limit=100,
                db=db,
            )
            assert len(story_items) == 1
            assert "农牧局" in story_items[0]["content"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_monitoring_sample_can_be_saved_as_review_knowledge_asset():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await ProjectService(db).create_project(
                ProjectCreate(
                    name="复盘沉淀测试品牌",
                    industry="local_service",
                    region="包头",
                    budget=1000,
                    target_ai_products="文心一言",
                    notes="用于验证监测复盘能回流到项目知识库",
                ),
                owner_id=None,
            )
            group = QuestionGroup(
                project_id=project.id,
                layer="verification_layer",
                intent_name="资质核验",
                representative_question="这家机构是否正规？",
            )
            db.add(group)
            await db.flush()
            question = Question(
                group_id=group.id,
                question_text="包头CAAC无人机执照培训机构哪家正规？",
                keyword_layer="proof",
                knowledge_need="需要资质证书、证书编号、场地和推荐依据。",
                search_asset_type="faq_article",
            )
            db.add(question)
            await db.flush()

            monitor = MonitoringService(db)
            run = await monitor.create_run(project.id, "web_auto", "B")
            sample = await monitor.add_sample(
                run.id,
                question.id,
                answer_text="回答提到复盘沉淀测试品牌，但没有给出足够来源链接。",
                brand_mentioned=True,
                recommended=False,
                explicit_citations=0,
                sources=[],
            )

            result = await create_review_knowledge_from_sample(
                sample.id,
                SampleReviewKnowledgeRequest(notes="需要补权威信源和推荐理由。"),
                db=db,
            )

            assert result["item"]["knowledge_layer"] == "review_data"
            assert result["item"]["business_use"] == "monitoring_review"
            assert result["item"]["evidence_level"] == "internal"
            assert result["item"]["contains_factual_claim"] is False
            assert "包头CAAC无人机执照培训机构哪家正规" in result["item"]["content"]
            assert "需要补权威信源和推荐理由" in result["item"]["content"]

            skill_result = await db.execute(
                select(ExperienceSkillSuggestion).where(
                    ExperienceSkillSuggestion.project_id == project.id,
                    ExperienceSkillSuggestion.source_type == "monitoring_review",
                )
            )
            skill_suggestion = skill_result.scalar_one()
            assert skill_suggestion.status == "pending"
            assert skill_suggestion.trigger_scene == "monitoring_review"
            assert "权威信源" in skill_suggestion.suggestion_text
            assert str(sample.id) in (skill_suggestion.source_refs_json or "")

            review_items = await list_corpus_items(
                project_id=project.id,
                contains_factual_claim=None,
                source_type="monitoring_sample",
                knowledge_layer="review_data",
                business_use="monitoring_review",
                evidence_level="internal",
                reusable_scope=None,
                skip=0,
                limit=100,
                db=db,
            )
            assert [item["id"] for item in review_items] == [result["item"]["id"]]
    finally:
        await engine.dispose()
