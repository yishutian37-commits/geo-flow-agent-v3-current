from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.api.v1.endpoints.publish_records import assist_publish_with_webbridge
from app.core.database import Base
from app.models.brand import Brand
from app.models.brand_fact import BrandFact
from app.models.channel_account import ChannelAccount
from app.models.content_draft import ContentDraft
from app.models.content_task import ContentTask
from app.models.project import Project
from app.schemas.publish_record import PublishWebBridgeAssistRequest


@pytest.mark.asyncio
async def test_publish_assist_returns_copy_package_when_channel_has_no_url():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = Project(name="publish-smoke", industry="training", region="baotou")
            db.add(project)
            await db.flush()

            brand = Brand(project_id=project.id, brand_name="mengji", company_name="mengji company")
            account = ChannelAccount(
                tenant_id="00000000-0000-0000-0000-000000000000",
                platform="other",
                account_name="manual channel",
                account_type="owned",
                publish_permission=True,
                status="normal",
            )
            task = ContentTask(
                project_id=project.id,
                content_type="brand_intro",
                layer="verification_layer",
                priority="medium",
                status="approved",
            )
            db.add_all([brand, account, task])
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
            draft = ContentDraft(
                task_id=task.id,
                title="CAAC training intro",
                body="mengji has CAAC qualification.",
                version="1.0",
                status="approved",
                risk_level="low",
            )
            db.add_all([fact, draft])
            await db.commit()
            await db.refresh(account)
            await db.refresh(draft)

            result = await assist_publish_with_webbridge(
                PublishWebBridgeAssistRequest(
                    draft_id=draft.id,
                    channel_account_id=account.id,
                    platform="other",
                ),
                db=db,
                user=SimpleNamespace(id="00000000-0000-0000-0000-000000000001"),
            )

            assert result["can_publish"] is True
            assert result["webbridge"]["attempted"] is False
            assert result["content_package"]["title"] == "CAAC training intro"
            assert result["content_package"]["body"] == "mengji has CAAC qualification."
    finally:
        await engine.dispose()
