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
    _build_question_generation_strategy,
    _build_template_groups,
    _looks_like_ai_platform_keyword_misuse,
    generate_content_matrix,
    generate_question_bank,
)
from app.api.v1.endpoints.monitoring import (
    SampleContentTaskRequest,
    create_content_task_from_sample,
)
from app.api.v1.endpoints.questions import create_question, create_question_group, delete_question, update_question
from app.core.database import Base
from app.models.baseline_run import BaselineRun
from app.models.brand import Brand
from app.models.brand_fact import BrandFact
from app.models.content_task import ContentTask
from app.models.monitoring import MonitoringRun, MonitoringSample
from app.models.question import Question, QuestionGroup
from app.models.question_template_feedback import QuestionTemplateFeedback
from app.models.report_archive import ReportArchive
from app.models.sentiment import SentimentRecord
from app.models.user import User
from app.schemas.baseline_run import BaselinePromoteRequest
from app.schemas.brand import BrandCreate
from app.schemas.content_draft import ContentDraftCreate
from app.schemas.project import ProjectCreate
from app.schemas.question import QuestionCreate, QuestionGroupCreate, QuestionUpdate
from app.schemas.user import UserOut
from app.services.monitoring_service import MonitoringService
from app.services.project_service import ProjectService
from app.services.question_template_learning import build_question_template_suggestions


def test_question_templates_stay_industry_aware_and_do_not_use_ai_platform_terms():
    cases = [
        {
            "industry": "manufacturing_b2b",
            "region": "鎴愰兘",
            "brand": "鐜勯搧鐚溂",
            "notes": "宸ヤ笟瑙嗚妫€娴嬭澶囥€佷骇绾胯川妫€銆佷紒涓氶噰璐?,
            "facts": [
                "涓昏惀宸ヤ笟瑙嗚妫€娴嬭澶囷紝鏈嶅姟鐢靛瓙鍒堕€犲拰姹借溅闆堕儴浠朵骇绾裤€?,
                "鎷ユ湁ISO璐ㄩ噺绠＄悊浣撶郴璁よ瘉銆?,
            ],
            "expected_terms": ["宸ヤ笟瑙嗚妫€娴嬭澶囦緵搴斿晢", "閲囪喘"],
            "forbidden_terms": ["鏈嶅姟鏈烘瀯鎺ㄨ崘", "涓汉鎶ュ悕", "鎶ュ悕", "瀛﹀憳", "澶嶈", "甯堣祫", "鏍″尯", "閫氳繃鐜?],
        },
        {
            "industry": "local_life",
            "region": "鑻忓窞",
            "brand": "闇滄ˉ灏忕倝",
            "notes": "绀惧尯椁愰ギ銆佸瀹点€侀棬搴楄瘎浠枫€侀绾?,
            "facts": [
                "涓绘墦鑻忓紡灏忕倝鐮傞攨鍜屽瀹靛爞椋熴€?,
                "闂ㄥ簵浣嶄簬鑻忓窞甯傚鑻忓尯銆?,
            ],
            "expected_terms": ["椁愰ギ闂ㄥ簵", "鍒板簵"],
            "forbidden_terms": ["鏈嶅姟鏈烘瀯鎺ㄨ崘", "浼佷笟閲囪喘", "涓汉鎶ュ悕", "鎶ュ悕", "瀛﹀憳", "澶嶈", "甯堣祫", "鏍″尯", "閫氳繃鐜?, "璧勮川璇佷功"],
        },
        {
            "industry": "consumer_brand",
            "region": "娣卞湷",
            "brand": "鍖楃含闆剁硸",
            "notes": "浣庣硸楗搧銆佸勾杞绘秷璐硅€呫€佺嚎涓婅喘涔般€侀厤鏂欒〃",
            "facts": [
                "浜у搧涓轰綆绯栨皵娉￠ギ锛屽凡鍦ㄧ嚎涓婃笭閬撻攢鍞€?,
                "閰嶆枡琛ㄦ爣娉ㄨ丹钘撶硸閱囧拰鏋滄眮鍚噺銆?,
            ],
            "expected_terms": ["浣庣硸楗搧鍝佺墝", "璐拱"],
            "forbidden_terms": ["鏈嶅姟鏈烘瀯鎺ㄨ崘", "浼佷笟閲囪喘", "涓汉鎶ュ悕", "鎶ュ悕", "瀛﹀憳", "澶嶈", "甯堣祫", "鏍″尯", "閫氳繃鐜?, "璧勮川璇佷功"],
        },
    ]
    platform_terms = ["deepseek", "kimi", "璞嗗寘", "qwen", "moonshot", "鏂囧績", "chatgpt", "gemini"]

    for case in cases:
        project = SimpleNamespace(
            name=f"{case['brand']}鏈夐檺鍏徃",
            industry=case["industry"],
            region=case["region"],
            notes=case["notes"],
            target_ai_products="DeepSeek,Kimi,璞嗗寘",
        )
        facts = [
            SimpleNamespace(public_wording=value, value=value, fact_type="service", status="confirmed")
            for value in case["facts"]
        ]
        groups = _build_template_groups(project, case["brand"], facts)
        questions = [q["question_text"] for group in groups for q in group["questions"]]
        strategy = _build_question_generation_strategy(project, case["brand"], facts)
        joined = " ".join(questions)

        assert len(groups) >= 4
        assert len(questions) >= 25
        assert strategy["keyword_breakdown"]["service_terms"]
        assert not any(_looks_like_ai_platform_keyword_misuse(question) for question in questions)
        assert not any(term in joined.lower() for term in platform_terms)
        assert any(term in joined for term in case["expected_terms"])
        assert not any(term in joined for term in case["forbidden_terms"])


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
                    name="钂欓渷绌哄ぉ鏅鸿兘",
                    industry="education_training",
                    region="鍖呭ご",
                    budget=1000,
                    target_ai_products="DeepSeek,Kimi,璞嗗寘",
                    notes="CAAC鏃犱汉鏈烘墽鐓у煿璁拰鏃犱汉鏈虹鏅熀鍦?,
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
                    value="鎷ユ湁姘戠敤鏃犱汉椹鹃┒鑸┖鍣ㄨ繍钀ュ悎鏍艰瘉锛岀紪鍙?UAOC-O-HQ-20260128179銆?,
                    public_wording="姘戠敤鏃犱汉椹鹃┒鑸┖鍣ㄨ繍钀ュ悎鏍艰瘉缂栧彿 UAOC-O-HQ-20260128179銆?,
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
            generated_question_texts = [
                question["question_text"]
                for group in first_bank["groups"]
                for question in group["questions"]
            ]
            assert not any(
                "deepseek" in text.lower() or "kimi" in text.lower() or "璞嗗寘" in text
                for text in generated_question_texts
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
            sample = await monitor.add_sample(
                run.id,
                question.id,
                answer_text="鍖呭ご鏃犱汉鏈哄煿璁彲浠ュ叧娉ㄨ挋闇佺┖澶╂櫤鑳斤紝寤鸿鏍搁獙璇佷功缂栧彿銆?,
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

            sample_task = await create_content_task_from_sample(
                sample.id,
                SampleContentTaskRequest(),
                db=db,
                user=SimpleNamespace(role="project_owner"),
            )
            assert sample_task["task"]["project_id"] == str(project.id)
            assert sample_task["task"]["group_id"] == str(question.group_id)
            duplicate_sample_task = await create_content_task_from_sample(
                sample.id,
                SampleContentTaskRequest(),
                db=db,
                user=SimpleNamespace(role="project_owner"),
            )
            assert duplicate_sample_task["task"]["already_exists"] is True

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
async def test_question_edits_create_template_learning_suggestions():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await ProjectService(db).create_project(
                ProjectCreate(
                    name="鐜勯搧瑙嗚",
                    industry="manufacturing_b2b",
                    region="娣卞湷",
                    notes="宸ヤ笟瑙嗚妫€娴嬭澶囥€佷骇绾胯川妫€銆佷紒涓氶噰璐?,
                ),
                owner_id=None,
            )
            group = await create_question_group(
                QuestionGroupCreate(
                    project_id=project.id,
                    layer="pool_layer",
                    intent_name="鏈湴鎺ㄨ崘/鍏ユ睜",
                    representative_question="娣卞湷宸ヤ笟瑙嗚妫€娴嬭澶囦緵搴斿晢鎬庝箞閫夛紵",
                ),
                db=db,
            )
            good_question = await create_question(
                group_id=group["id"],
                data=QuestionCreate(question_text="娣卞湷宸ヤ笟瑙嗚妫€娴嬭澶囦緵搴斿晢鎬庝箞閫夛紵"),
                db=db,
            )
            updated_question = await update_question(
                good_question["id"],
                QuestionUpdate(question_text="娣卞湷宸ヤ笟瑙嗚璐ㄦ渚涘簲鍟嗘€庝箞鏍搁獙妗堜緥锛?),
                db=db,
            )
            bad_question = await create_question(
                group_id=group["id"],
                data=QuestionCreate(question_text="娣卞湷宸ヤ笟瑙嗚妫€娴嬭澶囧煿璁姤鍚嶉潬璋卞悧锛?),
                db=db,
            )
            await delete_question(bad_question["id"], db=db)

            feedback_count = (
                await db.execute(select(func.count()).select_from(QuestionTemplateFeedback))
            ).scalar_one()
            assert feedback_count >= 4

            suggestions = await build_question_template_suggestions(db, industry=project.industry)
            assert len(suggestions) == 1
            suggestion = suggestions[0]
            joined_positive = " ".join(suggestion["positive_examples"])
            joined_negative = " ".join(suggestion["negative_examples"])
            assert suggestion["industry"] == project.industry
            assert updated_question["question_text"] in joined_positive
            assert bad_question["question_text"] in joined_negative
            assert "鎶ュ悕" in suggestion["add_forbidden_terms"]
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
                        full_name="绯荤粺绠＄悊鍛?,
                        role="admin",
                        is_active=True,
                    ),
                    User(
                        id=str(uuid4()),
                        username="pm01",
                        email="pm01@geoflow.local",
                        hashed_password="x",
                        full_name="椤圭洰璐熻矗浜?,
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
                ProjectCreate(name="椤圭洰A", industry="training", region="鍖呭ご"),
                owner_id=None,
            )
            project_b = await ProjectService(db).create_project(
                ProjectCreate(name="椤圭洰B", industry="training", region="鍛煎拰娴╃壒"),
                owner_id=None,
            )
            group_b = QuestionGroup(
                project_id=project_b.id,
                layer="manual",
                intent_name="璺ㄩ」鐩棶棰?,
                representative_question="椤圭洰B闂",
            )
            disabled_group = QuestionGroup(
                project_id=project_a.id,
                layer="manual",
                intent_name="绂佺敤闂",
                representative_question="绂佺敤闂",
            )
            active_group = QuestionGroup(
                project_id=project_a.id,
                layer="manual",
                intent_name="鏈夋晥闂",
                representative_question="鏈夋晥闂",
            )
            db.add_all([group_b, disabled_group, active_group])
            await db.flush()
            cross_project_question = Question(group_id=group_b.id, question_text="椤圭洰B闂")
            disabled_question = Question(
                group_id=disabled_group.id,
                question_text="椤圭洰A绂佺敤闂",
                enabled=False,
            )
            active_question = Question(group_id=active_group.id, question_text="椤圭洰A鏈夋晥闂")
            db.add_all([cross_project_question, disabled_question, active_question])
            await db.commit()

            monitor = MonitoringService(db)
            run = await monitor.create_run(project_a.id, "routine", "B")

            with pytest.raises(ValueError, match="涓嶅睘浜?):
                await monitor.add_sample(run.id, cross_project_question.id, answer_text="閿欒椤圭洰鏍锋湰")
            with pytest.raises(ValueError, match="宸插仠鐢?):
                await monitor.add_sample(run.id, disabled_question.id, answer_text="绂佺敤闂鏍锋湰")

            sample = await monitor.add_sample(
                run.id,
                active_question.id,
                answer_text="钂欓渷绌哄ぉ鏅鸿兘琚彁鍙?,
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
                answer_text="寰呭垹闄ゆ暣娆℃娴?,
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
                ProjectCreate(name="褰掓。娓呯悊椤圭洰", industry="training", region="鍖呭ご"),
                owner_id=None,
            )
            archive = ReportArchive(
                project_id=project.id,
                report_type="monitoring",
                title="娴嬭瘯鎶ュ憡",
                markdown="# 娴嬭瘯鎶ュ憡",
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
            with pytest.raises(HTTPException, match="鍝佺墝蹇呴』缁戝畾"):
                await create_brand(
                    BrandCreate(project_id=missing_project_id, brand_name="涓嶅瓨鍦ㄩ」鐩搧鐗?),
                    db=db,
                )
            with pytest.raises(HTTPException, match="闂缁勫繀椤荤粦瀹?):
                await create_question_group(
                    QuestionGroupCreate(
                        project_id=missing_project_id,
                        layer="manual",
                        intent_name="涓嶅瓨鍦ㄩ」鐩棶棰樼粍",
                        representative_question="闂",
                    ),
                    db=db,
                )
            with pytest.raises(HTTPException, match="绋夸欢鑽夌蹇呴』缁戝畾"):
                await create_content_draft(
                    ContentDraftCreate(task_id=uuid4(), title="鑽夌", body="姝ｆ枃"),
                    db=db,
                    user=SimpleNamespace(role="project_owner"),
                )

            project = await ProjectService(db).create_project(
                ProjectCreate(name="椤圭洰", industry="training", region="鍖呭ご"),
                owner_id=None,
            )
            group = await create_question_group(
                QuestionGroupCreate(
                    project_id=project.id,
                    layer="manual",
                    intent_name="姝ｅ父闂缁?,
                    representative_question="闂",
                ),
                db=db,
            )
            with pytest.raises(HTTPException, match="涓嶄竴鑷?):
                await create_question(
                    group_id=group["id"],
                    data=QuestionCreate(group_id=uuid4(), question_text="闂"),
                    db=db,
                )
    finally:
        await engine.dispose()
