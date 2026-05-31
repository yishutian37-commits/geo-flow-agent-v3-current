"""
项目与诊断 Agent Service
负责项目创建、资料缺口诊断、行业模板匹配
"""
import re
from typing import List, Optional, Dict, Any, Set
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete

from app.models.approval import Approval
from app.models.baseline_run import BaselineRun
from app.models.project import Project
from app.models.brand import Brand
from app.models.brand_fact import BrandFact
from app.models.compliance_check import ComplianceCheck
from app.models.content_draft import ContentDraft
from app.models.content_task import ContentTask
from app.models.corpus_item import CorpusItem
from app.models.model_target import ModelTarget
from app.models.monitoring import MonitoringRun, MonitoringSample
from app.models.publish_record import PublishRecord
from app.models.question import QuestionGroup, Question
from app.models.recommendation import Recommendation
from app.models.report_archive import ReportArchive
from app.models.sentiment import SentimentRecord
from app.models.source_asset import SourceAsset
from app.models.writing_memory import ContentFeedback, WritingProfile
from app.schemas.project import ProjectCreate, ProjectUpdate


# 行业模板定义：每个行业需要收集的资料清单
INDUSTRY_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "local_life": {
        "name": "本地生活",
        "required_fields": [
            "business_license", "store_photos", "address", "phone",
            "business_hours", "parking_info", "poi_info", "map_location",
            "customer_reviews", "service_menu", "price_list"
        ],
        "optional_fields": ["franchise_info", "branch_locations", "membership_rules"],
        "high_risk_fields": ["medical_claims", "guaranteed_results"]
    },
    "education_training": {
        "name": "教育培训（职业技能/非学科）",
        "required_fields": [
            "training_qualification", "instructor_profiles", "course_catalog",
            "campus_photos", "address", "phone", "pricing", "certification_flow",
            "graduate_cases", "enrollment_process", "refund_policy"
        ],
        "optional_fields": ["scholarship_info", "online_platform", "partner_companies"],
        "high_risk_fields": ["guaranteed_employment", "guaranteed_pass", "k12_academic"]
    },
    "manufacturing_b2b": {
        "name": "制造业 B2B",
        "required_fields": [
            "company_profile", "product_parameters", "factory_photos",
            "b2b_platform_pages", "case_studies", "technical_documents",
            "after_sales_service", "contact_info", "address", "certifications"
        ],
        "optional_fields": ["r_and_d_capability", "patent_info", "export_qualification"],
        "high_risk_fields": ["false_case_studies", "exaggerated_parameters", "unauthorized_client_names"]
    },
    "consumer_brand": {
        "name": "消费品牌",
        "required_fields": [
            "brand_story", "product_introduction", "ecommerce_pages",
            "customer_reviews", "after_sales_policy", "media_coverage",
            "social_media_accounts", "price_value_proposition"
        ],
        "optional_fields": ["celebrity_endorsement", "award_info", "offline_stores"],
        "high_risk_fields": ["fake_reviews", "exaggerated_effects", "unauthorized_medical_claims"]
    },
    "professional_service": {
        "name": "专业服务",
        "required_fields": [
            "team_qualifications", "service_process", "case_studies",
            "client_testimonials", "contract_scope", "contact_info",
            "address", "pricing_model", "faq"
        ],
        "optional_fields": ["industry_certifications", "thought_leadership", "partnerships"],
        "high_risk_fields": ["guaranteed_results", "revenue_sharing", "client_confidentiality_breach"]
    },
}

# 字段中文映射
FIELD_LABELS: Dict[str, str] = {
    "business_license": "营业执照",
    "store_photos": "门店照片",
    "address": "地址",
    "phone": "电话",
    "business_hours": "营业时间",
    "parking_info": "停车信息",
    "poi_info": "POI信息",
    "map_location": "地图定位",
    "customer_reviews": "客户评价",
    "service_menu": "服务菜单",
    "price_list": "价目表",
    "training_qualification": "培训资质",
    "instructor_profiles": "师资介绍",
    "course_catalog": "课程目录",
    "campus_photos": "校区照片",
    "pricing": "价格体系",
    "certification_flow": "考证流程",
    "graduate_cases": "学员案例",
    "enrollment_process": "报名流程",
    "refund_policy": "退费政策",
    "company_profile": "公司介绍",
    "product_parameters": "产品参数",
    "factory_photos": "工厂照片",
    "b2b_platform_pages": "B2B平台页面",
    "case_studies": "案例",
    "technical_documents": "技术文档",
    "after_sales_service": "售后服务",
    "contact_info": "联系方式",
    "certifications": "资质证书",
    "brand_story": "品牌故事",
    "product_introduction": "产品介绍",
    "ecommerce_pages": "电商页面",
    "media_coverage": "媒体报道",
    "social_media_accounts": "社媒账号",
    "price_value_proposition": "价格价值主张",
    "team_qualifications": "团队资质",
    "service_process": "服务流程",
    "client_testimonials": "客户评价",
    "contract_scope": "合同范围",
    "pricing_model": "定价模式",
    "faq": "FAQ",
}


FACT_TYPE_FIELD_MAP: Dict[str, List[str]] = {
    "business_license": ["business_license", "company_profile"],
    "qualification": ["training_qualification", "certifications", "team_qualifications"],
    "certification": ["training_qualification", "certifications", "team_qualifications"],
    "license": ["business_license", "training_qualification", "certifications"],
    "address": ["address", "map_location", "poi_info"],
    "phone": ["phone", "contact_info"],
    "contact": ["phone", "contact_info", "social_media_accounts"],
    "price": ["pricing", "price_list", "pricing_model", "price_value_proposition"],
    "course": ["course_catalog", "service_menu", "products_services"],
    "service": ["course_catalog", "service_menu", "service_process", "products_services"],
    "product": ["product_introduction", "product_parameters", "products_services"],
    "case_study": ["graduate_cases", "case_studies", "client_testimonials"],
    "review": ["customer_reviews", "client_testimonials"],
    "teacher": ["instructor_profiles", "team_qualifications"],
    "instructor": ["instructor_profiles", "team_qualifications"],
    "process": ["certification_flow", "enrollment_process", "service_process"],
    "refund": ["refund_policy", "after_sales_policy", "after_sales_service"],
    "after_sales": ["after_sales_policy", "after_sales_service"],
    "media": ["media_coverage", "social_media_accounts"],
    "photo": ["campus_photos", "store_photos", "factory_photos"],
    "factory": ["factory_photos", "company_profile"],
    "company": ["company_profile", "brand_story"],
    "brand": ["brand_story", "company_profile"],
}


FACT_VALUE_FIELD_HINTS = [
    (r"营业执照|统一社会信用代码|经营许可证", ["business_license", "company_profile"]),
    (r"资质|证书|编号|许可证|合格证|CAAC|AOPA|认证", ["training_qualification", "certifications", "team_qualifications"]),
    (r"讲师|教员|老师|师资|导师", ["instructor_profiles", "team_qualifications"]),
    (r"课程|班型|课时|培训内容|教学大纲", ["course_catalog", "service_menu"]),
    (r"校区|基地|场地|训练场|教室|照片|图片", ["campus_photos", "store_photos", "factory_photos", "address"]),
    (r"地址|位于|电话|手机|微信|官网|公众号|联系", ["address", "phone", "contact_info", "social_media_accounts"]),
    (r"价格|费用|学费|报价|收费|预算", ["pricing", "price_list", "pricing_model", "price_value_proposition"]),
    (r"报名|流程|取证|考试|考证|交付|服务流程", ["enrollment_process", "certification_flow", "service_process"]),
    (r"退款|退费|售后|保障|复训", ["refund_policy", "after_sales_policy", "after_sales_service"]),
    (r"案例|学员|客户|通过率|就业|评价|口碑", ["graduate_cases", "case_studies", "client_testimonials", "customer_reviews"]),
    (r"产品|参数|规格|型号|功能", ["product_introduction", "product_parameters"]),
    (r"媒体|报道|新闻|公众号|小红书|抖音", ["media_coverage", "social_media_accounts"]),
]


def _template_for_industry(industry: Optional[str]) -> Dict[str, Any]:
    return INDUSTRY_TEMPLATES.get(industry or "") or {
        "name": "通用",
        "required_fields": ["company_info", "contact", "address", "products_services"],
        "optional_fields": [],
        "high_risk_fields": [],
    }


def _template_fields(template: Dict[str, Any]) -> Set[str]:
    return set(template.get("required_fields", [])) | set(template.get("optional_fields", []))


def _field_item(field: str, severity: str = "medium") -> Dict[str, str]:
    return {"field": field, "label": FIELD_LABELS.get(field, field), "severity": severity}


class ProjectService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_project(self, data: ProjectCreate, owner_id: Optional[UUID] = None) -> Project:
        """创建新项目"""
        project = Project(
            name=data.name,
            industry=data.industry,
            region=data.region,
            owner_id=owner_id,
            budget=data.budget,
            start_date=data.start_date,
            end_date=data.end_date,
            target_ai_products=data.target_ai_products,
            notes=data.notes,
        )
        self.db.add(project)
        await self.db.flush()

        default_brand = Brand(
            project_id=project.id,
            brand_name=data.name,
            company_name=data.name,
            description=data.notes,
        )
        self.db.add(default_brand)
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def get_project(self, project_id: UUID) -> Optional[Project]:
        """获取项目详情"""
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        return result.scalar_one_or_none()

    async def list_projects(
        self,
        industry: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Project]:
        """列表查询项目"""
        query = select(Project)
        filters = []
        if industry:
            filters.append(Project.industry == industry)
        if status:
            filters.append(Project.status == status)
        if filters:
            query = query.where(and_(*filters))
        query = query.offset(skip).limit(limit).order_by(Project.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_project(self, project_id: UUID, data: ProjectUpdate) -> Optional[Project]:
        """更新项目"""
        project = await self.get_project(project_id)
        if not project:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(project, field, value)
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def delete_project(self, project_id: UUID) -> bool:
        """删除项目，并清理该项目下的关联业务数据。"""
        project = await self.get_project(project_id)
        if not project:
            return False

        task_ids = select(ContentTask.id).where(ContentTask.project_id == project_id)
        draft_ids = select(ContentDraft.id).where(ContentDraft.task_id.in_(task_ids))
        run_ids = select(MonitoringRun.id).where(MonitoringRun.project_id == project_id)
        sample_ids = select(MonitoringSample.id).where(MonitoringSample.run_id.in_(run_ids))
        group_ids = select(QuestionGroup.id).where(QuestionGroup.project_id == project_id)
        brand_ids = select(Brand.id).where(Brand.project_id == project_id)

        delete_statements = [
            delete(SentimentRecord).where(SentimentRecord.sample_id.in_(sample_ids)),
            delete(MonitoringSample).where(MonitoringSample.run_id.in_(run_ids)),
            delete(BaselineRun).where(BaselineRun.project_id == project_id),
            delete(PublishRecord).where(PublishRecord.task_id.in_(task_ids)),
            delete(ComplianceCheck).where(ComplianceCheck.draft_id.in_(draft_ids)),
            delete(ContentDraft).where(ContentDraft.task_id.in_(task_ids)),
            delete(Approval).where(
                and_(
                    Approval.object_type == "content_task",
                    Approval.object_id.in_(task_ids),
                )
            ),
            delete(ContentTask).where(ContentTask.project_id == project_id),
            delete(MonitoringRun).where(MonitoringRun.project_id == project_id),
            delete(Question).where(Question.group_id.in_(group_ids)),
            delete(QuestionGroup).where(QuestionGroup.project_id == project_id),
            delete(ModelTarget).where(ModelTarget.project_id == project_id),
            delete(BrandFact).where(BrandFact.brand_id.in_(brand_ids)),
            delete(Brand).where(Brand.project_id == project_id),
            delete(CorpusItem).where(CorpusItem.project_id == project_id),
            delete(SourceAsset).where(SourceAsset.project_id == project_id),
            delete(Recommendation).where(Recommendation.project_id == project_id),
            delete(ReportArchive).where(ReportArchive.project_id == project_id),
            delete(ContentFeedback).where(ContentFeedback.project_id == project_id),
            delete(WritingProfile).where(WritingProfile.project_id == project_id),
        ]
        for statement in delete_statements:
            await self.db.execute(statement.execution_options(synchronize_session=False))

        await self.db.delete(project)
        await self.db.commit()
        return True

    async def diagnose_gaps(self, project_id: UUID, provided_fields: List[str]) -> Dict[str, Any]:
        """
        资料缺口诊断
        根据行业模板检查缺失项
        """
        project = await self.get_project(project_id)
        if not project:
            return {"error": "Project not found"}

        template = _template_for_industry(project.industry)

        provided_set = set(provided_fields)
        required_set = set(template.get("required_fields", []))
        optional_set = set(template.get("optional_fields", []))
        high_risk_set = set(template.get("high_risk_fields", []))

        missing_required = list(required_set - provided_set)
        missing_optional = list(optional_set - provided_set)
        provided_high_risk = list(high_risk_set & provided_set)

        # 计算完整性评分
        if required_set:
            completeness = len(provided_set & required_set) / len(required_set)
        else:
            completeness = 1.0

        return {
            "project_id": str(project_id),
            "industry": project.industry,
            "industry_name": template.get("name", project.industry),
            "completeness_score": round(completeness * 100, 1),
            "missing_required": [
                {"field": f, "label": FIELD_LABELS.get(f, f), "severity": "high"}
                for f in missing_required
            ],
            "missing_optional": [
                {"field": f, "label": FIELD_LABELS.get(f, f), "severity": "medium"}
                for f in missing_optional
            ],
            "high_risk_provided": [
                {"field": f, "label": FIELD_LABELS.get(f, f), "severity": "warning"}
                for f in provided_high_risk
            ],
            "total_required": len(required_set),
            "total_provided": len(provided_set & required_set),
        }

    async def diagnose_gaps_from_facts(self, project_id: UUID) -> Dict[str, Any]:
        """
        从品牌事实库自动推断已具备资料，再执行行业资料缺口诊断。
        只有已确认且公开可用的事实会计入完整度；待确认/内部事实会作为待处理动作返回。
        """
        project = await self.get_project(project_id)
        if not project:
            return {"error": "Project not found"}

        template = _template_for_industry(project.industry)
        allowed_fields = _template_fields(template)

        facts_result = await self.db.execute(
            select(BrandFact)
            .join(Brand, BrandFact.brand_id == Brand.id)
            .where(Brand.project_id == project_id)
            .order_by(BrandFact.created_at.desc())
        )
        facts = list(facts_result.scalars().all())

        confirmed_fields: Set[str] = set()
        pending_fields: Set[str] = set()
        fact_coverage = []

        for fact in facts:
            mapped_fields = self._map_fact_to_fields(fact, allowed_fields)
            if not mapped_fields:
                continue
            is_public_confirmed = fact.status == "confirmed" and fact.fact_scope == "public"
            if is_public_confirmed:
                confirmed_fields.update(mapped_fields)
            else:
                pending_fields.update(mapped_fields)
            fact_coverage.append({
                "fact_id": str(fact.id),
                "fact_type": fact.fact_type,
                "status": fact.status,
                "fact_scope": fact.fact_scope,
                "risk_level": fact.risk_level,
                "mapped_fields": [_field_item(field) for field in sorted(mapped_fields)],
                "counts_as_provided": is_public_confirmed,
            })

        diagnosis = await self.diagnose_gaps(project_id, sorted(confirmed_fields))
        if "error" in diagnosis:
            return diagnosis

        missing_required = {item["field"] for item in diagnosis.get("missing_required", [])}
        missing_optional = {item["field"] for item in diagnosis.get("missing_optional", [])}
        action_items = []

        for field in sorted(missing_required):
            if field in pending_fields:
                action_items.append({
                    "field": field,
                    "label": FIELD_LABELS.get(field, field),
                    "priority": "high",
                    "action_type": "confirm_fact",
                    "suggestion": f"事实库已有「{FIELD_LABELS.get(field, field)}」相关候选，请先确认公开口径后再用于生成内容。",
                })
            else:
                action_items.append({
                    "field": field,
                    "label": FIELD_LABELS.get(field, field),
                    "priority": "high",
                    "action_type": "collect_material",
                    "suggestion": f"补充「{FIELD_LABELS.get(field, field)}」资料，并沉淀为已确认的公开品牌事实。",
                })

        for field in sorted(missing_optional):
            action_items.append({
                "field": field,
                "label": FIELD_LABELS.get(field, field),
                "priority": "medium",
                "action_type": "optional_enrichment",
                "suggestion": f"可补充「{FIELD_LABELS.get(field, field)}」以提升后续问题矩阵和稿件可信度。",
            })

        diagnosis.update({
            "diagnosis_source": "brand_facts",
            "provided_fields": [_field_item(field, "low") for field in sorted(confirmed_fields)],
            "pending_fields": [_field_item(field, "warning") for field in sorted(pending_fields - confirmed_fields)],
            "fact_coverage": fact_coverage,
            "action_items": action_items,
        })
        return diagnosis

    def _map_fact_to_fields(self, fact: BrandFact, allowed_fields: Set[str]) -> Set[str]:
        fields: Set[str] = set()
        fact_type = (fact.fact_type or "").strip().lower()
        for key, mapped in FACT_TYPE_FIELD_MAP.items():
            if key in fact_type:
                fields.update(mapped)

        text = " ".join([
            str(fact.fact_type or ""),
            str(fact.value or ""),
            str(fact.public_wording or ""),
            str(fact.source or ""),
        ])
        for pattern, mapped in FACT_VALUE_FIELD_HINTS:
            if re.search(pattern, text, flags=re.I):
                fields.update(mapped)

        if not fields and fact_type:
            fields.add(fact_type)

        if allowed_fields:
            narrowed = fields & allowed_fields
            if narrowed:
                return narrowed
        return fields

    async def get_brand_facts_summary(self, project_id: UUID) -> Dict[str, Any]:
        """获取项目下品牌事实库摘要"""
        result = await self.db.execute(
            select(Brand, BrandFact).join(
                BrandFact, Brand.id == BrandFact.brand_id, isouter=True
            ).where(Brand.project_id == project_id)
        )
        rows = result.all()

        facts_by_status = {}
        for brand, fact in rows:
            if fact:
                status = fact.status
                facts_by_status[status] = facts_by_status.get(status, 0) + 1

        return {
            "project_id": str(project_id),
            "brand_count": len(set(b.id for b, _ in rows)),
            "facts_by_status": facts_by_status,
            "confirmed_facts": facts_by_status.get("confirmed", 0),
            "pending_facts": facts_by_status.get("draft", 0),
            "expired_facts": facts_by_status.get("expired", 0),
            "disputed_facts": facts_by_status.get("disputed", 0),
        }
