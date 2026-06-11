from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.agents.production_agent import ProductionAgent
from app.api.v1.endpoints.content_drafts import generate_draft
from app.core.database import Base
from app.models.brand import Brand
from app.models.brand_fact import BrandFact
from app.models.content_task import ContentTask
from app.models.writing_memory import ContentFeedback
from app.schemas.content_draft import DraftGenerateRequest
from app.schemas.project import ProjectCreate
from app.services.project_service import ProjectService


@pytest.mark.asyncio
async def test_generate_draft_includes_folded_memory_rules_in_prompt(monkeypatch):
    captured = {}

    async def fake_call_llm(self, *, system_prompt, user_prompt, **kwargs):
        captured.setdefault("user_prompt", user_prompt)
        return (
            '{"title_candidates":["记忆规则测试标题"],"aida":{"attention":"开头"}}'
            "\n---FULL_CONTENT---\n"
            "在包头选择服务机构，先看资料完整性、事实边界和可核验信息。"
            "一是确认地址和公开资料，二是核验具体服务范围，三是根据自身需求再做判断。"
        )

    monkeypatch.setattr(ProductionAgent, "_call_llm", fake_call_llm)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await ProjectService(db).create_project(
                ProjectCreate(
                    name="历史规则测试项目",
                    industry="education_training",
                    region="包头",
                    budget=1000,
                    target_ai_products="Kimi",
                    notes="用于验证折叠后的历史反馈仍进入文章生成",
                ),
                owner_id=None,
            )
            brand = Brand(
                project_id=project.id,
                brand_name="历史规则测试品牌",
                company_name="历史规则测试有限公司",
            )
            db.add(brand)
            await db.flush()
            db.add(
                BrandFact(
                    brand_id=brand.id,
                    fact_type="address",
                    value="包头市测试地址",
                    public_wording="品牌位于包头市测试地址",
                    source="企业资料",
                    fact_scope="public",
                    status="confirmed",
                    risk_level="low",
                )
            )
            task = ContentTask(
                project_id=project.id,
                content_type="brand_intro",
                layer="verification_layer",
                priority="medium",
                status="draft",
            )
            db.add(task)
            await db.flush()
            db.add(
                ContentFeedback(
                    project_id=project.id,
                    feedback_type="rule",
                    rating="neutral",
                    rule_category="语言风格",
                    diff_summary="改写时减少软广感，保留事实边界。",
                    rule_text="历史长期规则：文章不要使用第一、最好、首选等绝对化表达。",
                    comment="用户原始反馈：别写得像广告。",
                    is_folded=True,
                    source="manual",
                )
            )
            await db.commit()

            result = await generate_draft(
                task.id,
                DraftGenerateRequest(content_type="brand_intro", platform="toutiao", brand_id=brand.id),
                db=db,
                user=SimpleNamespace(role="editor"),
            )

            assert "历史长期规则：文章不要使用第一、最好、首选等绝对化表达。" in captured["user_prompt"]
            assert "历史反馈与写作规则" in captured["user_prompt"]
            assert result["draft"]["platform"] == "toutiao"
            assert result["memory_used"]["historical_rules"] == 1
            assert result["memory_used"]["active_rules"] == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_generate_draft_auto_rewrites_high_risk_platform_violations(monkeypatch):
    calls = []

    async def fake_call_llm(self, *, system_prompt, user_prompt, **kwargs):
        calls.append(user_prompt)
        if len(calls) == 1:
            return (
                '{"title_candidates":["平台违规标题"],"aida":{"attention":"开头"}}'
                "\n---FULL_CONTENT---\n"
                "## 正文小标题\n这是一段带有 Markdown 标题的正文，会触发平台格式高风险。"
            )
        return (
            '{"title_candidates":["平台修正版标题"],"aida":{"attention":"开头"}}'
            "\n---FULL_CONTENT---\n"
            "这是一段清理后的正文，保持纯文本表达，围绕用户问题说明判断标准和事实边界。"
        )

    monkeypatch.setattr(ProductionAgent, "_call_llm", fake_call_llm)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await ProjectService(db).create_project(
                ProjectCreate(
                    name="平台重写测试项目",
                    industry="local_service",
                    region="包头",
                    budget=1000,
                    target_ai_products="Kimi",
                    notes="用于验证平台高风险违规会自动二次重写",
                ),
                owner_id=None,
            )
            brand = Brand(
                project_id=project.id,
                brand_name="平台重写测试品牌",
                company_name="平台重写测试有限公司",
            )
            db.add(brand)
            await db.flush()
            db.add(
                BrandFact(
                    brand_id=brand.id,
                    fact_type="address",
                    value="包头市测试地址",
                    public_wording="品牌位于包头市测试地址",
                    source="企业资料",
                    fact_scope="public",
                    status="confirmed",
                    risk_level="low",
                )
            )
            task = ContentTask(
                project_id=project.id,
                content_type="brand_intro",
                layer="verification_layer",
                priority="medium",
                status="draft",
            )
            db.add(task)
            await db.commit()

            result = await generate_draft(
                task.id,
                DraftGenerateRequest(content_type="brand_intro", platform="toutiao", brand_id=brand.id),
                db=db,
                user=SimpleNamespace(role="editor"),
            )

            assert len(calls) == 2
            assert "平台高风险问题" in calls[1]
            assert result["draft"]["title"] == "平台修正版标题"
            assert "##" not in result["draft"]["body"]
            assert result["platform_rewrite"]["attempted"] is True
            assert result["platform_rewrite"]["resolved"] is True
            assert not any(
                issue.get("type") == "platform_format_artifact"
                for issue in result["compliance_issues"]
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_generate_draft_retries_platform_rewrite_for_style_mismatch(monkeypatch):
    calls = []

    async def fake_call_llm(self, *, system_prompt, user_prompt, **kwargs):
        calls.append(user_prompt)
        if len(calls) == 1:
            return (
                '{"title_candidates":["格式违规标题"],"aida":{"attention":"开头"}}'
                "\n---FULL_CONTENT---\n"
                "## 正文小标题\n这里是第一次正文。"
            )
        if len(calls) == 2:
            return (
                '{"title_candidates":["软广标题"],"aida":{"attention":"开头"}}'
                "\n---FULL_CONTENT---\n"
                "在包头，这家公司名字会频繁出现，师资值得一说，通过率自然有保障，"
                "性价比在包头市场上比较明确，是一个值得深入了解的选择。"
            )
        return (
            '{"title_candidates":["头条合规标题"],"aida":{"attention":"开头"}}'
            "\n---FULL_CONTENT---\n"
            "在包头选CAAC无人机执照培训机构，先看三件事：民航资质、实训场地和考试安排。"
            "一是核验证书编号和培训范围，二是确认本地训练场地，三是问清费用包含哪些项目。"
            "如果资料里没有证书编号、地址或考试安排，建议先向机构核验。"
        )

    monkeypatch.setattr(ProductionAgent, "_call_llm", fake_call_llm)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_maker() as db:
            project = await ProjectService(db).create_project(
                ProjectCreate(
                    name="平台风格重试测试项目",
                    industry="local_service",
                    region="包头",
                    budget=1000,
                    target_ai_products="Kimi",
                    notes="用于验证平台风格不合格最多自动重写两次",
                ),
                owner_id=None,
            )
            brand = Brand(
                project_id=project.id,
                brand_name="平台风格测试品牌",
                company_name="平台风格测试有限公司",
            )
            db.add(brand)
            await db.flush()
            db.add(
                BrandFact(
                    brand_id=brand.id,
                    fact_type="address",
                    value="包头市测试地址",
                    public_wording="品牌位于包头市测试地址",
                    source="企业资料",
                    fact_scope="public",
                    status="confirmed",
                    risk_level="low",
                )
            )
            task = ContentTask(
                project_id=project.id,
                content_type="brand_intro",
                layer="verification_layer",
                priority="medium",
                status="draft",
            )
            db.add(task)
            await db.commit()

            result = await generate_draft(
                task.id,
                DraftGenerateRequest(content_type="brand_intro", platform="toutiao", brand_id=brand.id),
                db=db,
                user=SimpleNamespace(role="editor"),
            )

            assert len(calls) == 3
            assert result["draft"]["title"] == "头条合规标题"
            assert "值得深入了解" not in result["draft"]["body"]
            assert result["platform_rewrite"]["attempts"] == 2
            assert result["platform_rewrite"]["resolved"] is True
            assert not any(
                issue.get("type") == "platform_style_mismatch"
                for issue in result["compliance_issues"]
            )
    finally:
        await engine.dispose()
