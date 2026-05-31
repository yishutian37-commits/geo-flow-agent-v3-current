from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.v1.endpoints.reports import (
    delete_report_archive,
    generate_and_archive_report,
    get_report_archive,
    get_report_archive_markdown,
    list_report_archives,
)
from app.core.database import Base
from app.models.brand import Brand
from app.models.brand_fact import BrandFact
from app.models.model_target import ModelTarget
from app.models.monitoring import MonitoringRun, MonitoringSample
from app.models.project import Project
from app.models.question import Question, QuestionGroup
from app.models.source_asset import SourceAsset
from app.schemas.report_archive import ReportArchiveGenerateRequest


@pytest.mark.asyncio
async def test_generate_list_read_markdown_and_delete_report_archive():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = Project(name="archive-smoke-project", industry="training", region="baotou")
            db.add(project)
            await db.flush()

            brand = Brand(project_id=project.id, brand_name="mengji", company_name="mengji company")
            target = ModelTarget(project_id=project.id, product_name="doubao", supported_mechanisms="B")
            source = SourceAsset(
                project_id=project.id,
                source_type="official_site",
                url="https://example.com",
                authority_level="high",
                crawlability="crawlable",
            )
            group = QuestionGroup(
                project_id=project.id,
                layer="verification_layer",
                intent_name="qualification",
                representative_question="does mengji have caac qualification?",
            )
            db.add_all([brand, target, source, group])
            await db.flush()

            fact = BrandFact(
                brand_id=brand.id,
                fact_type="qualification",
                value="CAAC",
                public_wording="has CAAC qualification",
                fact_scope="public",
                status="confirmed",
                risk_level="low",
            )
            question = Question(group_id=group.id, question_text="does mengji have caac qualification?", priority=90)
            run = MonitoringRun(
                project_id=project.id,
                run_type="post",
                mechanism_type="B",
                model_target_id=target.id,
                status="completed",
            )
            run2 = MonitoringRun(
                project_id=project.id,
                run_type="post",
                mechanism_type="B",
                model_target_id=target.id,
                status="completed",
            )
            db.add_all([fact, question, run, run2])
            await db.flush()

            sampled_at = datetime.now(timezone.utc)
            db.add_all(
                [
                    MonitoringSample(
                        run_id=run.id,
                        question_id=question.id,
                        answer_text="answer",
                        brand_mentioned=index < 8,
                        recommended=index < 3,
                        sampled_at=sampled_at,
                    )
                    for index in range(10)
                ]
            )
            db.add_all(
                [
                    MonitoringSample(
                        run_id=run2.id,
                        question_id=question.id,
                        answer_text="answer2",
                        brand_mentioned=index < 2,
                        recommended=index < 1,
                        sampled_at=sampled_at,
                    )
                    for index in range(5)
                ]
            )
            await db.commit()

            archive = await generate_and_archive_report(
                ReportArchiveGenerateRequest(
                    project_id=project.id,
                    report_type="client",
                    run_id=run.id,
                    title="archive-smoke",
                ),
                db,
            )
            assert archive["title"] == "archive-smoke"
            assert archive["payload"]["report_type"] == "client"

            items = await list_report_archives(project_id=project.id, report_type=None, limit=20, db=db)
            assert len(items) == 1
            assert items[0]["sample_count"] == 10

            detail = await get_report_archive(archive["id"], db)
            assert "acceptance_baseline" in detail["payload"]
            assert detail["markdown"]

            multi_archive = await generate_and_archive_report(
                ReportArchiveGenerateRequest(
                    project_id=project.id,
                    report_type="client",
                    run_ids=[run.id, run2.id],
                ),
                db,
            )
            assert multi_archive["sample_count"] == 15
            assert len(multi_archive["run_ids"]) == 2
            assert multi_archive["payload"]["monitoring_results"]["aggregation_mode"] == "multi_run"
            assert "聚合 2 组检测记录" in multi_archive["markdown"]

            markdown = await get_report_archive_markdown(archive["id"], db)
            assert "GEO" in markdown

            deleted = await delete_report_archive(archive["id"], db)
            assert deleted["deleted"] is True
    finally:
        await engine.dispose()
