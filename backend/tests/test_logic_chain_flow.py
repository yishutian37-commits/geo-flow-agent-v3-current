from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.v1.endpoints.brands import create_brand
from app.api.v1.endpoints.content_drafts import create_content_draft
from app.main import ensure_runtime_schema
from app.main import repair_reserved_local_user_emails
from app.api.v1.endpoints.baseline_runs import promote_monitoring_run_to_baseline
from app.api.v1.endpoints.projects import (
    ContentMatrixRequest,
    generate_content_matrix,
    generate_question_bank,
)
from app.api.v1.endpoints.questions import create_question, create_question_group
from app.core.database import Base
from app.models.baseline_run import BaselineRun
from app.models.brand import Brand
from app.models.brand_fact import BrandFact
from app.models.content_task import ContentTask
from app.models.monitoring import MonitoringRun, MonitoringSample
from app.models.question import Question, QuestionGroup
from app.models.report_archive import ReportArchive
from app.models.sentiment import SentimentRecord
from app.models.user import User
from app.schemas.baseline_run import BaselinePromoteRequest
from app.schemas.brand import BrandCreate
from app.schemas.content_draft import ContentDraftCreate
from app.schemas.project import ProjectCreate
from app.schemas.question import QuestionCreate, QuestionGroupCreate
from app.schemas.user import UserOut
from app.services.monitoring_service import MonitoringService
from app.services.project_service import ProjectService


@pytest.mark.asyncio
async def test_project_to_question_content_monitoring_baseline_flow_is_connected():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await ProjectService(db).create_project(
                ProjectCreate(
                    name="蒙霁空天智能",
                    industry="education_training",
                    region="包头",
                    budget=1000,
                    target_ai_products="豆包,Kimi",
                    notes="CAAC无人机执照培训和无人机科普基地",
                ),
                owner_id=None,
            )
            brand = (
                await db.execute(select(Brand).where(Brand.project_id == project.id))
            ).scalars().first()
            db.add(
                BrandFact(
                    brand_id=brand.id,
                    fact_type="qualification",
                    value="拥有民用无人驾驶航空器运营合格证，编号 UAOC-O-HQ-20260128179。",
                    public_wording="民用无人驾驶航空器运营合格证编号 UAOC-O-HQ-20260128179。",
                    fact_scope="public",
                    status="confirmed",
                    risk_level="low",
                )
            )
            await db.commit()

            first_bank = await generate_question_bank(
                project.id,
                replace_existing=True,
                db=db,
            )
            active_after_first = await _count_groups(db, project.id, status="active")
            assert first_bank["generated_groups"] >= 4
            assert active_after_first == first_bank["generated_groups"]

            second_bank = await generate_question_bank(
                project.id,
                replace_existing=True,
                db=db,
            )
            active_after_second = await _count_groups(db, project.id, status="active")
            archived_after_second = await _count_groups(db, project.id, status="archived")
            assert active_after_second == second_bank["generated_groups"]
            assert archived_after_second == active_after_first

            matrix = await generate_content_matrix(
                project.id,
                ContentMatrixRequest(replace_existing=False, max_tasks=8, apply_schedule=True),
                db=db,
                user=SimpleNamespace(role="admin"),
            )
            assert matrix["created_tasks"] > 0
            created_task_count = (
                await db.execute(
                    select(func.count())
                    .select_from(ContentTask)
                    .where(ContentTask.project_id == project.id, ContentTask.status != "cancelled")
                )
            ).scalar_one()
            assert created_task_count == matrix["created_tasks"]

            duplicate_matrix = await generate_content_matrix(
                project.id,
                ContentMatrixRequest(replace_existing=False, max_tasks=8, apply_schedule=True),
                db=db,
                user=SimpleNamespace(role="admin"),
            )
            assert duplicate_matrix["created_tasks"] == 0
            assert duplicate_matrix["skipped_tasks"] == matrix["created_tasks"]

            question = (
                await db.execute(
                    select(Question)
                    .join(QuestionGroup, Question.group_id == QuestionGroup.id)
                    .where(QuestionGroup.project_id == project.id, QuestionGroup.status == "active")
                    .order_by(Question.created_at.asc())
                    .limit(1)
                )
            ).scalars().first()
            monitor = MonitoringService(db)
            run = await monitor.create_run(project.id, "routine", "B")
            await monitor.add_sample(
                run.id,
                question.id,
                answer_text="包头无人机培训可以关注蒙霁空天智能，建议核验证书编号。",
                brand_mentioned=True,
                recommended=True,
                position=1,
                list_length=4,
                explicit_citations=1,
            )
            metrics = await monitor.calculate_run_metrics(run.id)
            assert metrics["sample_count"] == 1
            assert metrics["raw_counts"]["mentioned"] == 1
            assert metrics["raw_counts"]["recommended"] == 1
            assert metrics["metrics"]["average_visibility_score"] == 1.0

            baseline = await promote_monitoring_run_to_baseline(
                run.id,
                BaselinePromoteRequest(require_acceptance_grade=False),
                db=db,
            )
            assert baseline["run_marked_as_baseline"] is True
            assert baseline["created_baselines"] == 1
            run_after = (
                await db.execute(select(MonitoringRun).where(MonitoringRun.id == run.id))
            ).scalar_one()
            assert run_after.run_type == "baseline"
            baseline_rows = (
                await db.execute(
                    select(func.count())
                    .select_from(BaselineRun)
                    .where(BaselineRun.project_id == project.id)
                )
            ).scalar_one()
            assert baseline_rows == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_repair_reserved_local_user_emails_prevents_userout_validation_failure():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            db.add_all(
                [
                    User(
                        id=str(uuid4()),
                        username="admin",
                        email="admin@geoflow.local",
                        hashed_password="x",
                        full_name="系统管理员",
                        role="admin",
                        is_active=True,
                    ),
                    User(
                        id=str(uuid4()),
                        username="pm01",
                        email="pm01@geoflow.local",
                        hashed_password="x",
                        full_name="项目负责人",
                        role="project_owner",
                        is_active=True,
                    ),
                ]
            )
            await db.commit()

            changed = await repair_reserved_local_user_emails(db)
            assert changed == 2

            result = await db.execute(select(User).order_by(User.username))
            users = list(result.scalars().all())
            emails = {user.username: user.email for user in users}
            assert emails["admin"] == "admin@geoflow.app"
            assert emails["pm01"] == "pm01@geoflow.app"

            for user in users:
                UserOut.model_validate(user)
    finally:
        await engine.dispose()


async def _count_groups(db, project_id, status):
    return (
        await db.execute(
            select(func.count())
            .select_from(QuestionGroup)
            .where(QuestionGroup.project_id == project_id, QuestionGroup.status == status)
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_runtime_schema_backfills_missing_model_columns_for_legacy_sqlite_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE content_drafts (id VARCHAR(36) PRIMARY KEY)"))
            await conn.execute(text("CREATE TABLE monitoring_samples (id VARCHAR(36) PRIMARY KEY)"))
            await conn.execute(text("CREATE TABLE model_targets (id VARCHAR(36) PRIMARY KEY)"))
            await ensure_runtime_schema(conn)

            draft_columns = {
                row[1] for row in (await conn.execute(text("PRAGMA table_info(content_drafts)"))).fetchall()
            }
            sample_columns = {
                row[1] for row in (await conn.execute(text("PRAGMA table_info(monitoring_samples)"))).fetchall()
            }
            target_columns = {
                row[1] for row in (await conn.execute(text("PRAGMA table_info(model_targets)"))).fetchall()
            }

        assert {"title", "body", "version", "risk_level", "fact_refs"}.issubset(draft_columns)
        assert {"sources_json", "analysis_json", "screenshot_url"}.issubset(sample_columns)
        assert {"recognition_mode", "web_url", "submit_selector", "search_backend"}.issubset(target_columns)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_monitoring_sample_rejects_cross_project_or_disabled_questions(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project_a = await ProjectService(db).create_project(
                ProjectCreate(name="项目A", industry="training", region="包头"),
                owner_id=None,
            )
            project_b = await ProjectService(db).create_project(
                ProjectCreate(name="项目B", industry="training", region="呼和浩特"),
                owner_id=None,
            )
            group_b = QuestionGroup(
                project_id=project_b.id,
                layer="manual",
                intent_name="跨项目问题",
                representative_question="项目B问题",
            )
            disabled_group = QuestionGroup(
                project_id=project_a.id,
                layer="manual",
                intent_name="禁用问题",
                representative_question="禁用问题",
            )
            active_group = QuestionGroup(
                project_id=project_a.id,
                layer="manual",
                intent_name="有效问题",
                representative_question="有效问题",
            )
            db.add_all([group_b, disabled_group, active_group])
            await db.flush()
            cross_project_question = Question(group_id=group_b.id, question_text="项目B问题")
            disabled_question = Question(
                group_id=disabled_group.id,
                question_text="项目A禁用问题",
                enabled=False,
            )
            active_question = Question(group_id=active_group.id, question_text="项目A有效问题")
            db.add_all([cross_project_question, disabled_question, active_question])
            await db.commit()

            monitor = MonitoringService(db)
            run = await monitor.create_run(project_a.id, "routine", "B")

            with pytest.raises(ValueError, match="不属于"):
                await monitor.add_sample(run.id, cross_project_question.id, answer_text="错误项目样本")
            with pytest.raises(ValueError, match="已停用"):
                await monitor.add_sample(run.id, disabled_question.id, answer_text="禁用问题样本")

            sample = await monitor.add_sample(
                run.id,
                active_question.id,
                answer_text="蒙霁空天智能被提及",
                brand_mentioned=True,
                screenshot_url="/api/v1/monitoring/screenshots/evidence.png",
            )
            screenshot_file = tmp_path / "evidence.png"
            screenshot_file.write_bytes(b"png")
            monkeypatch.setenv("GEO_SCREENSHOT_DIR", str(tmp_path))
            db.add(
                SentimentRecord(
                    sample_id=sample.id,
                    sentiment_type="negative",
                    severity="low",
                    source="test",
                )
            )
            await db.commit()
            deleted = await monitor.delete_sample(sample.id)
            assert deleted["id"] == str(sample.id)
            remaining_samples = (
                await db.execute(
                    select(func.count())
                    .select_from(MonitoringSample)
                    .where(MonitoringSample.id == sample.id)
                )
            ).scalar_one()
            remaining_sentiments = (
                await db.execute(
                    select(func.count())
                    .select_from(SentimentRecord)
                    .where(SentimentRecord.sample_id == sample.id)
                )
            ).scalar_one()
            assert remaining_samples == 0
            assert remaining_sentiments == 0
            assert not screenshot_file.exists()
            assert await monitor.delete_sample(sample.id) is None

            run_to_delete = await monitor.create_run(project_a.id, "routine", "B")
            run_screenshot = tmp_path / "run-evidence.png"
            run_screenshot.write_bytes(b"png")
            await monitor.add_sample(
                run_to_delete.id,
                active_question.id,
                answer_text="待删除整次检测",
                screenshot_url="/api/v1/monitoring/screenshots/run-evidence.png",
            )
            deleted_run = await monitor.delete_run(run_to_delete.id)
            assert deleted_run["id"] == str(run_to_delete.id)
            assert not run_screenshot.exists()
            assert await monitor.get_run(run_to_delete.id) is None

            cancelled = await monitor.update_run_status(run.id, "cancelled")
            assert cancelled.status == "cancelled"
            assert cancelled.ended_at is not None
            with pytest.raises(ValueError, match="Invalid monitoring run status"):
                await monitor.update_run_status(run.id, "unknown")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_delete_project_cleans_report_archives():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await ProjectService(db).create_project(
                ProjectCreate(name="归档清理项目", industry="training", region="包头"),
                owner_id=None,
            )
            archive = ReportArchive(
                project_id=project.id,
                report_type="monitoring",
                title="测试报告",
                markdown="# 测试报告",
                payload_json="{}",
            )
            db.add(archive)
            await db.commit()

            deleted = await ProjectService(db).delete_project(project.id)
            assert deleted is True
            remaining_archives = (
                await db.execute(
                    select(func.count())
                    .select_from(ReportArchive)
                    .where(ReportArchive.project_id == project.id)
                )
            ).scalar_one()
            assert remaining_archives == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_endpoints_validate_required_parent_links_before_database_write():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            missing_project_id = uuid4()
            with pytest.raises(HTTPException, match="品牌必须绑定"):
                await create_brand(
                    BrandCreate(project_id=missing_project_id, brand_name="不存在项目品牌"),
                    db=db,
                )
            with pytest.raises(HTTPException, match="问题组必须绑定"):
                await create_question_group(
                    QuestionGroupCreate(
                        project_id=missing_project_id,
                        layer="manual",
                        intent_name="不存在项目问题组",
                        representative_question="问题",
                    ),
                    db=db,
                )
            with pytest.raises(HTTPException, match="稿件草稿必须绑定"):
                await create_content_draft(
                    ContentDraftCreate(task_id=uuid4(), title="草稿", body="正文"),
                    db=db,
                    user=SimpleNamespace(role="project_owner"),
                )

            project = await ProjectService(db).create_project(
                ProjectCreate(name="项目", industry="training", region="包头"),
                owner_id=None,
            )
            group = await create_question_group(
                QuestionGroupCreate(
                    project_id=project.id,
                    layer="manual",
                    intent_name="正常问题组",
                    representative_question="问题",
                ),
                db=db,
            )
            with pytest.raises(HTTPException, match="不一致"):
                await create_question(
                    group_id=group["id"],
                    data=QuestionCreate(group_id=uuid4(), question_text="问题"),
                    db=db,
                )
    finally:
        await engine.dispose()
