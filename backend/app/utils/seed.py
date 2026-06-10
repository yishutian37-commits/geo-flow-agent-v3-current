"""
数据库种子数据
用于开发和测试环境初始化示例数据
"""
import asyncio
import os
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import async_engine, Base
from app.models.user import User
from app.models.project import Project
from app.models.brand import Brand
from app.models.brand_fact import BrandFact
from app.models.question import QuestionGroup, Question
from app.models.model_target import ModelTarget
from app.models.channel_account import ChannelAccount
from app.core.security import get_password_hash


async def seed_data():
    """初始化种子数据"""
    if os.getenv("GEO_ALLOW_SAMPLE_SEED", "").strip().lower() not in {"1", "true", "yes", "on"}:
        raise RuntimeError("Sample seed is disabled. Set GEO_ALLOW_SAMPLE_SEED=1 to create demo data.")

    admin_password = os.getenv("GEO_SAMPLE_ADMIN_PASSWORD")
    owner_password = os.getenv("GEO_SAMPLE_PROJECT_OWNER_PASSWORD")
    if not admin_password or not owner_password:
        raise RuntimeError(
            "Set GEO_SAMPLE_ADMIN_PASSWORD and GEO_SAMPLE_PROJECT_OWNER_PASSWORD before seeding demo users."
        )

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # 1. 创建测试用户
        admin_user = User(
            id=uuid4(),
            username="admin",
            email="admin@geoflow.app",
            hashed_password=get_password_hash(admin_password),
            full_name="系统管理员",
            role="admin",
            is_active=True,
        )
        db.add(admin_user)

        project_owner = User(
            id=uuid4(),
            username="pm01",
            email="pm01@geoflow.app",
            hashed_password=get_password_hash(owner_password),
            full_name="项目负责人",
            role="project_owner",
            is_active=True,
        )
        db.add(project_owner)

        await db.commit()

        # 2. 创建示例项目
        project = Project(
            id=uuid4(),
            name="包头本地无人机培训品牌GEO优化",
            industry="education_training",
            region="内蒙古包头",
            owner_id=project_owner.id,
            status="active",
            budget=50000.00,
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=90),
            target_ai_products='["豆包", "Kimi", "文心一言"]',
            notes="职业教育培训 + 本地服务 + 资质敏感场景",
        )
        db.add(project)
        await db.commit()

        # 3. 创建品牌
        brand = Brand(
            id=uuid4(),
            project_id=project.id,
            brand_name="包头无人机培训中心",
            company_name="包头市XX航空科技有限公司",
            aliases="包头无人机驾校, 包头CAAC培训",
            official_site="https://example-btuav.com",
            description="专注无人机驾驶员执照培训，CAAC认证机构",
        )
        db.add(brand)
        await db.commit()

        # 4. 创建品牌事实
        facts = [
            BrandFact(
                id=uuid4(),
                brand_id=brand.id,
                fact_type="qualification",
                value="CAAC民用无人驾驶航空器运营合格证",
                source="中国民航局官网",
                evidence_type="certificate",
                fact_scope="public",
                public_wording="本机构持有中国民航局颁发的民用无人驾驶航空器运营合格证",
                status="confirmed",
                confirmed_by=project_owner.id,
                confirmed_at=datetime.now(timezone.utc),
            ),
            BrandFact(
                id=uuid4(),
                brand_id=brand.id,
                fact_type="address",
                value="内蒙古包头市青山区XX路XX号",
                source="客户提供",
                evidence_type="official_page",
                fact_scope="public",
                public_wording="校区地址：包头市青山区XX路XX号",
                status="confirmed",
                confirmed_by=project_owner.id,
                confirmed_at=datetime.now(timezone.utc),
            ),
            BrandFact(
                id=uuid4(),
                brand_id=brand.id,
                fact_type="phone",
                value="0472-XXXXXXX",
                source="客户提供",
                evidence_type="official_page",
                fact_scope="public",
                public_wording="咨询热线：0472-XXXXXXX",
                status="confirmed",
                confirmed_by=project_owner.id,
                confirmed_at=datetime.now(timezone.utc),
            ),
            BrandFact(
                id=uuid4(),
                brand_id=brand.id,
                fact_type="price",
                value="多旋翼视距内驾驶员课程 6800元/人",
                source="客户提供",
                evidence_type="contract",
                fact_scope="public",
                public_wording="视距内驾驶员课程费用请咨询官方渠道",
                status="draft",
            ),
        ]
        for f in facts:
            db.add(f)
        await db.commit()

        # 5. 创建问题库
        qg1 = QuestionGroup(
            id=uuid4(),
            project_id=project.id,
            layer="exposure",
            intent_name="品牌发现与推荐",
            representative_question="包头无人机培训机构哪家好",
            priority=90,
        )
        db.add(qg1)
        await db.commit()

        questions = [
            Question(
                id=uuid4(),
                group_id=qg1.id,
                question_text="包头无人机培训机构哪家好",
                priority=90,
                sample_policy="key",
            ),
            Question(
                id=uuid4(),
                group_id=qg1.id,
                question_text="包头学无人机驾照推荐哪家",
                priority=85,
                sample_policy="key",
            ),
        ]
        for q in questions:
            db.add(q)
        await db.commit()

        # 6. 创建检测平台
        targets = [
            ModelTarget(
                id=uuid4(),
                project_id=project.id,
                product_name="豆包",
                supported_mechanisms='["B", "C"]',
                search_backend="字节搜索",
                access_method="manual_entry",
                api_available=False,
            ),
            ModelTarget(
                id=uuid4(),
                project_id=project.id,
                product_name="Kimi",
                supported_mechanisms='["B", "C"]',
                search_backend="混合搜索",
                access_method="official_api",
                api_available=True,
            ),
        ]
        for t in targets:
            db.add(t)
        await db.commit()

        # 7. 创建渠道账号
        channels = [
            ChannelAccount(
                id=uuid4(),
                tenant_id=project_owner.id,
                platform="公众号",
                account_name="包头无人机培训官方号",
                account_type="official",
                publish_permission=True,
                risk_level="low",
            ),
            ChannelAccount(
                id=uuid4(),
                tenant_id=project_owner.id,
                platform="小红书",
                account_name="包头飞手训练营",
                account_type="official",
                publish_permission=True,
                risk_level="low",
            ),
        ]
        for c in channels:
            db.add(c)
        await db.commit()

        print("Seed data created successfully!")
        print(f"- Users: 2")
        print(f"- Projects: 1 ({project.name})")
        print(f"- Brands: 1 ({brand.brand_name})")
        print(f"- Brand Facts: {len(facts)}")
        print(f"- Questions: {len(questions)}")
        print(f"- Model Targets: {len(targets)}")
        print(f"- Channel Accounts: {len(channels)}")


if __name__ == "__main__":
    asyncio.run(seed_data())
