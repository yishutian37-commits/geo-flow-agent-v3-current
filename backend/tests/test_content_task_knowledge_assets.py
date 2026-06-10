from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.v1.endpoints.content_tasks import create_content_task
from app.core.database import Base
from app.models.corpus_item import CorpusItem
from app.models.question import Question, QuestionGroup
from app.schemas.content_task import ContentTaskCreate
from app.schemas.project import ProjectCreate
from app.services.project_service import ProjectService


@pytest.mark.asyncio
async def test_content_task_can_reference_project_knowledge_assets():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await ProjectService(db).create_project(
                ProjectCreate(
                    name="项目知识资产测试品牌",
                    industry="professional_service",
                    region="杭州",
                    budget=1000,
                    target_ai_products="Kimi",
                    notes="用于验证内容任务可以引用项目知识资产。",
                ),
                owner_id=None,
            )
            story = CorpusItem(
                project_id=project.id,
                title="客户故事片段",
                content="一位企业客户通过该服务把交付周期从 14 天缩短到 7 天。",
                source_type="case",
                knowledge_layer="story",
                business_use="content_writing",
                evidence_level="verified",
                reusable_scope="project",
            )
            judgment = CorpusItem(
                project_id=project.id,
                title="判断逻辑",
                content="用户最关心的是交付边界、服务流程和售后响应。",
                source_type="interview",
                knowledge_layer="judgment",
                business_use="question_generation",
                evidence_level="internal",
                reusable_scope="project",
            )
            db.add_all([story, judgment])
            await db.commit()
            await db.refresh(story)
            await db.refresh(judgment)

            created = await create_content_task(
                ContentTaskCreate(
                    project_id=project.id,
                    content_type="brand_intro",
                    layer="pool_layer",
                    priority="medium",
                    knowledge_asset_ids=[story.id, judgment.id],
                ),
                db=db,
                user=SimpleNamespace(role="admin"),
            )

            assert created["knowledge_asset_ids"] == [str(story.id), str(judgment.id)]
            assert [item["title"] for item in created["knowledge_assets"]] == ["客户故事片段", "判断逻辑"]
            assert created["knowledge_assets"][0]["knowledge_layer"] == "story"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_content_task_auto_recommends_knowledge_assets_from_linked_question():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await ProjectService(db).create_project(
                ProjectCreate(
                    name="自动推荐知识资产测试品牌",
                    industry="professional_service",
                    region="杭州",
                    budget=1000,
                    target_ai_products="Kimi",
                    notes="用于验证内容任务可按问题需求自动带出知识资产。",
                ),
                owner_id=None,
            )
            group = QuestionGroup(
                project_id=project.id,
                layer="verification_layer",
                intent_name="可信验证",
                representative_question="如何核验这家公司的资质和案例？",
                priority=90,
            )
            db.add(group)
            await db.flush()
            question = Question(
                group_id=group.id,
                question_text="如何核验这家公司的资质证书和交付案例？",
                keyword_layer="proof",
                knowledge_need="需要资质证书、证书编号、客户案例和官方核验入口。",
                search_asset_type="qualification",
                evidence_support="资质、案例、地址",
                content_actionability="适合补可信核验指南和案例稿。",
            )
            qualification = CorpusItem(
                project_id=project.id,
                title="资质证书信息",
                content="公司拥有可公开核验的行业服务资质证书，证书编号为 TEST-001。",
                knowledge_layer="basic_info",
                business_use="content_writing",
                evidence_level="verified",
                reusable_scope="project",
                contains_factual_claim=True,
            )
            case_story = CorpusItem(
                project_id=project.id,
                title="客户案例素材",
                content="客户在一次复杂项目中通过该服务缩短了交付周期。",
                knowledge_layer="story",
                business_use="content_writing",
                evidence_level="verified",
                reusable_scope="project",
            )
            unrelated = CorpusItem(
                project_id=project.id,
                title="无关内部备忘",
                content="这是一条与资质和案例无关的内部待办。",
                knowledge_layer="review_data",
                business_use="monitoring_review",
                evidence_level="internal",
                reusable_scope="project",
            )
            db.add_all([question, qualification, case_story, unrelated])
            await db.commit()
            await db.refresh(question)

            created = await create_content_task(
                ContentTaskCreate(
                    project_id=project.id,
                    question_id=question.id,
                    content_type="faq",
                    layer="verification_layer",
                    priority="high",
                ),
                db=db,
                user=SimpleNamespace(role="admin"),
            )

            titles = [item["title"] for item in created["knowledge_assets"]]
            assert "资质证书信息" in titles
            assert "客户案例素材" in titles
            assert "无关内部备忘" not in titles
            assert created["knowledge_asset_ids"]
    finally:
        await engine.dispose()
