import pytest
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.v1.endpoints.experience_skills import (
    approve_skill_suggestion,
    create_skill,
    ExperienceSkillCreate,
    ExperienceSkillRevision,
    list_skill_versions,
    list_skill_suggestions,
    list_skills,
    revise_skill,
    rollback_skill_version,
)
from app.api.v1.endpoints.publish_records import _validate_and_record_publish_check
from app.api.v1.endpoints.writing_memory import create_feedback
from app.core.database import Base
from app.models.content_draft import ContentDraft
from app.models.content_task import ContentTask
from app.models.experience_skill import ExperienceSkillSuggestion
from app.schemas.project import ProjectCreate
from app.schemas.writing_memory import ContentFeedbackCreate
from app.services.project_service import ProjectService


@pytest.mark.asyncio
async def test_feedback_creates_pending_project_skill_suggestion_and_approval_activates_skill():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await ProjectService(db).create_project(
                ProjectCreate(
                    name="经验技能测试项目",
                    industry="local_service",
                    region="包头",
                    budget=1000,
                    target_ai_products="Kimi",
                    notes="用于验证反馈沉淀技能建议",
                ),
                owner_id=None,
            )

            feedback = await create_feedback(
                ContentFeedbackCreate(
                    project_id=project.id,
                    feedback_type="rewrite",
                    rating="neutral",
                    comment="文章少一点AI味，多写本地场景和人的口吻。",
                    rule_category="语言风格",
                    source="manual",
                ),
                db=db,
            )

            suggestions = await list_skill_suggestions(
                project_id=project.id,
                scope=None,
                trigger_scene="article_writing",
                status="pending",
                db=db,
            )

            assert len(suggestions) == 1
            suggestion = suggestions[0]
            assert suggestion["source_type"] == "feedback"
            assert suggestion["source_refs"]["feedback_id"] == feedback["id"]
            assert suggestion["suggested_scope"] == "project"
            assert suggestion["trigger_scene"] == "article_writing"
            assert "本地场景" in suggestion["suggestion_text"]

            approved = await approve_skill_suggestion(
                suggestion["id"],
                db=db,
                user=SimpleNamespace(role="admin"),
            )

            assert approved["suggestion"]["status"] == "approved"
            assert approved["skill"]["status"] == "active"
            assert approved["skill"]["scope"] == "project"
            assert approved["skill"]["project_id"] == str(project.id)

            active_skills = await list_skills(
                project_id=project.id,
                scope=None,
                trigger_scene="article_writing",
                status="active",
                db=db,
            )
            assert [item["id"] for item in active_skills] == [approved["skill"]["id"]]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_publish_check_creates_pending_skill_suggestion_for_risky_draft():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await ProjectService(db).create_project(
                ProjectCreate(
                    name="发布检查经验项目",
                    industry="local_service",
                    region="包头",
                    budget=1000,
                    target_ai_products="Kimi",
                    notes="用于验证发布检查沉淀技能建议",
                ),
                owner_id=None,
            )
            task = ContentTask(
                project_id=project.id,
                content_type="brand_intro",
                layer="verification",
                priority="medium",
                status="draft",
            )
            db.add(task)
            await db.flush()
            draft = ContentDraft(
                task_id=task.id,
                title="发布检查测试稿",
                body="这是一篇待发布文章。",
                platform="baijiahao",
                risk_level="high",
            )
            db.add(draft)
            await db.flush()

            validation = await _validate_and_record_publish_check(db, draft, task)

            assert validation["can_publish"] is False
            skill_result = await db.execute(
                select(ExperienceSkillSuggestion).where(
                    ExperienceSkillSuggestion.project_id == project.id,
                    ExperienceSkillSuggestion.source_type == "publish_check",
                )
            )
            suggestion = skill_result.scalar_one()
            assert suggestion.status == "pending"
            assert suggestion.trigger_scene == "publish_check"
            assert "高风险" in suggestion.suggestion_text
            assert str(draft.id) in (suggestion.source_refs_json or "")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_skill_revision_history_and_rollback_create_traceable_versions():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await ProjectService(db).create_project(
                ProjectCreate(
                    name="技能版本测试项目",
                    industry="local_service",
                    region="包头",
                    budget=1000,
                    target_ai_products="Kimi",
                    notes="用于验证技能版本历史",
                ),
                owner_id=None,
            )

            created = await create_skill(
                ExperienceSkillCreate(
                    name="本地化写作",
                    content="多写本地服务场景，避免空泛宣传。",
                    scope="project",
                    project_id=project.id,
                    trigger_scene="article_writing",
                    skill_type="rule",
                ),
                db=db,
                user=SimpleNamespace(role="admin"),
            )

            v1_history = await list_skill_versions(created["id"], db=db)
            assert len(v1_history) == 1
            assert v1_history[0]["version"] == 1
            assert v1_history[0]["content"] == "多写本地服务场景，避免空泛宣传。"
            assert v1_history[0]["change_type"] == "create"

            revised = await revise_skill(
                created["id"],
                ExperienceSkillRevision(
                    content="多写本地服务场景、真实用户顾虑和核验证据，避免空泛宣传。",
                    revision_reason="补充用户顾虑和证据要求",
                    change_type="revise",
                ),
                db=db,
                user=SimpleNamespace(role="admin"),
            )
            assert revised["version"] == 2
            assert "真实用户顾虑" in revised["content"]

            v2_history = await list_skill_versions(created["id"], db=db)
            assert [item["version"] for item in v2_history] == [2, 1]
            assert v2_history[0]["revision_reason"] == "补充用户顾虑和证据要求"

            rolled_back = await rollback_skill_version(
                created["id"],
                1,
                db=db,
                user=SimpleNamespace(role="admin"),
            )
            assert rolled_back["version"] == 3
            assert rolled_back["content"] == "多写本地服务场景，避免空泛宣传。"

            final_history = await list_skill_versions(created["id"], db=db)
            assert [item["version"] for item in final_history] == [3, 2, 1]
            assert final_history[0]["change_type"] == "rollback"
            assert final_history[0]["revision_reason"] == "回滚到 v1"
    finally:
        await engine.dispose()
