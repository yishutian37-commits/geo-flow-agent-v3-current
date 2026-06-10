from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.agents.orchestrator import Orchestrator
from app.core.database import Base
from app.models.brand import Brand
from app.models.brand_fact import BrandFact
from app.models.content_draft import ContentDraft
from app.models.content_task import ContentTask
from app.models.model_target import ModelTarget
from app.models.question import Question, QuestionGroup
from app.schemas.project import ProjectCreate
from app.services.project_service import ProjectService


async def _create_project(db, name: str = "Orchestrator 测试项目"):
    return await ProjectService(db).create_project(
        ProjectCreate(
            name=name,
            industry="local_service",
            region="包头",
            budget=1000,
            target_ai_products="Kimi,DeepSeek",
            notes="用于验证主控编排器前置诊断",
        ),
        owner_id=None,
    )


async def _add_confirmed_public_fact(db, project_id):
    brand = Brand(
        project_id=project_id,
        brand_name="测试品牌",
        company_name="测试品牌有限公司",
    )
    db.add(brand)
    await db.flush()
    fact = BrandFact(
        brand_id=brand.id,
        fact_type="certification",
        value="测试品牌具备公开可核验资质。",
        source="测试资料",
        fact_scope="public",
        status="confirmed",
        risk_level="low",
    )
    db.add(fact)
    await db.flush()
    return brand, fact


async def _add_enabled_question(db, project_id):
    group = QuestionGroup(
        project_id=project_id,
        layer="verification_layer",
        intent_name="资质核验",
        representative_question="测试品牌是否具备正规资质？",
        status="active",
    )
    db.add(group)
    await db.flush()
    question = Question(
        group_id=group.id,
        question_text="测试品牌是否具备正规资质？",
        question_type="brand_reputation",
        enabled=True,
    )
    db.add(question)
    await db.flush()
    return group, question


async def _add_model_target(db, project_id, name: str = "Kimi"):
    target = ModelTarget(
        project_id=project_id,
        product_name=name,
        access_method="web",
        recognition_mode="text",
        web_url="https://example.com/chat",
    )
    db.add(target)
    await db.flush()
    return target


@pytest.mark.asyncio
async def test_diagnosis_workflow_reports_blockers_until_readiness_inputs_exist():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await _create_project(db)
            orchestrator = Orchestrator(db)

            blocked = await orchestrator.run_diagnosis_workflow(project.id)
            assert blocked["status"] == "blocked"
            assert blocked["workflow_stage"] == "facts_pending"
            assert {item["code"] for item in blocked["blockers"]} == {
                "missing_brand_materials",
                "missing_question_matrix",
                "missing_model_targets",
            }

            await _add_confirmed_public_fact(db, project.id)
            await _add_enabled_question(db, project.id)
            await _add_model_target(db, project.id)

            ready = await orchestrator.run_diagnosis_workflow(project.id)
            assert ready["status"] == "diagnosis_ready"
            assert ready["workflow_stage"] == "diagnosis_ready"
            assert ready["blockers"] == []
            assert ready["counts"]["confirmed_public_facts"] == 1
            assert ready["counts"]["enabled_questions"] == 1
            assert ready["counts"]["model_targets"] == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_production_workflow_requires_public_facts_and_recognizes_existing_drafts():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await _create_project(db, "内容生产前置测试")
            task = ContentTask(
                project_id=project.id,
                content_type="brand_intro",
                layer="verification_layer",
                priority="medium",
                status="draft",
            )
            db.add(task)
            await db.flush()
            orchestrator = Orchestrator(db)

            blocked = await orchestrator.run_production_workflow(task.id)
            assert blocked["status"] == "blocked"
            assert blocked["workflow_stage"] == "facts_pending"
            assert blocked["blockers"][0]["code"] == "missing_confirmed_public_facts"

            await _add_confirmed_public_fact(db, project.id)

            ready = await orchestrator.run_production_workflow(task.id)
            assert ready["status"] == "production_ready"
            assert ready["workflow_stage"] == "draft_generation_ready"
            assert ready["counts"]["drafts"] == 0

            db.add(
                ContentDraft(
                    task_id=task.id,
                    title="测试草稿",
                    body="这是一篇基于已确认事实的测试草稿。",
                    platform="baijiahao",
                    status="draft",
                )
            )
            await db.flush()

            review = await orchestrator.run_production_workflow(task.id)
            assert review["status"] == "draft_ready_for_review"
            assert review["workflow_stage"] == "draft_review_pending"
            assert review["counts"]["drafts"] == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_monitoring_workflow_preflight_depends_on_questions_and_targets():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await _create_project(db, "监测前置测试")
            orchestrator = Orchestrator(db)

            blocked = await orchestrator.run_monitoring_workflow(project.id, run_type="web_auto")
            assert blocked["status"] == "blocked"
            assert blocked["workflow_stage"] == "monitoring_preflight_blocked"
            assert {item["code"] for item in blocked["blockers"]} == {
                "missing_question_matrix",
                "missing_model_targets",
            }

            await _add_enabled_question(db, project.id)
            await _add_model_target(db, project.id, name="DeepSeek")

            ready = await orchestrator.run_monitoring_workflow(project.id, run_type="web_auto")
            assert ready["status"] == "monitoring_ready"
            assert ready["workflow_stage"] == "sampling_ready"
            assert ready["run_type"] == "web_auto"
            assert ready["counts"]["enabled_questions"] == 1
            assert ready["counts"]["model_targets"] == 1
    finally:
        await engine.dispose()
