from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.auth import require_roles
from app.core.database import get_db
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectOut
from app.services.project_service import ProjectService
from app.models.content_task import ContentTask
from app.models.monitoring import MonitoringRun, MonitoringSample
from app.models.question import Question, QuestionGroup
from app.models.brand import Brand
from app.models.brand_fact import BrandFact
from app.models.user import User
from app.agents.strategy_agent import StrategyAgent
from app.prompts.templates import render_prompt_template
from app.services.question_archetype import (
    get_ai_platform_terms,
    get_industry_forbidden_terms,
    get_industry_question_copy,
    get_question_archetype,
    infer_service_from_archetype,
)

router = APIRouter()

# 行业问题模板（规则-based，不依赖LLM）
INDUSTRY_QUESTION_TEMPLATES = {
    "local_life": {
        "exposure": [
            ("附近好吃的火锅店推荐", "寻找本地餐饮推荐"),
            ("{region}口碑好的{industry}有哪些", "本地服务品牌发现"),
            ("{region}哪里可以{service}", "本地服务需求"),
        ],
        "verification": [
            ("{brand_name}怎么样，靠谱吗", "品牌口碑验证"),
            ("{brand_name}的服务评价如何", "服务评价查询"),
            ("{brand_name}和{competitor}哪个好", "品牌对比"),
        ],
        "conversion": [
            ("{brand_name}的地址和电话", "联系方式查询"),
            ("{brand_name}营业时间", "营业时间查询"),
            ("{brand_name}怎么预约/订座", "预约路径查询"),
        ],
    },
    "education_training": {
        "exposure": [
            ("{region}职业技能培训机构推荐", "培训机构发现"),
            ("想学习{skill}，哪家好", "技能培训推荐"),
            ("{region}靠谱的{course}培训", "本地培训发现"),
        ],
        "verification": [
            ("{brand_name}培训质量怎么样", "培训质量验证"),
            ("{brand_name}的学员就业情况", "学员案例验证"),
            ("{brand_name}有办学资质吗", "资质验证"),
        ],
        "conversion": [
            ("{brand_name}课程价格", "价格查询"),
            ("{brand_name}报名流程", "报名路径查询"),
            ("{brand_name}校区地址", "地址查询"),
        ],
    },
    "manufacturing_b2b": {
        "exposure": [
            ("{product}厂家推荐", "B2B厂家发现"),
            ("靠谱的{product}供应商", "供应商推荐"),
            ("{region}{product}制造商", "本地制造商发现"),
        ],
        "verification": [
            ("{brand_name}的产品质量如何", "产品质量验证"),
            ("{brand_name}有哪些成功案例", "案例验证"),
            ("{brand_name}的工厂规模", "企业实力验证"),
        ],
        "conversion": [
            ("{brand_name}联系方式和官网", "联系信息查询"),
            ("{brand_name}产品报价", "报价查询"),
            ("{brand_name}售后服务", "售后查询"),
        ],
    },
    "consumer_brand": {
        "exposure": [
            ("{product}品牌推荐", "品牌发现"),
            ("好用的{product}有哪些", "产品推荐"),
            ("{product}选购指南", "选购指南"),
        ],
        "verification": [
            ("{brand_name}的产品怎么样", "产品口碑"),
            ("{brand_name}用户评价", "用户评价"),
            ("{brand_name}和{competitor}对比", "竞品对比"),
        ],
        "conversion": [
            ("{brand_name}哪里买", "购买渠道"),
            ("{brand_name}官方店", "官方渠道"),
            ("{brand_name}售后政策", "售后查询"),
        ],
    },
    "professional_service": {
        "exposure": [
            ("{region}专业的{service}服务", "专业服务发现"),
            ("{service}公司推荐", "服务商推荐"),
            ("找{service}哪家好", "服务商发现"),
        ],
        "verification": [
            ("{brand_name}的服务专业吗", "专业度验证"),
            ("{brand_name}团队资质", "资质验证"),
            ("{brand_name}客户评价", "口碑验证"),
        ],
        "conversion": [
            ("{brand_name}咨询方式", "咨询路径"),
            ("{brand_name}服务流程", "流程查询"),
            ("{brand_name}收费标准", "收费查询"),
        ],
    },
}


INDUSTRY_LABELS = {
    "local_life": "本地生活",
    "education_training": "教育培训",
    "healthcare": "医疗健康",
    "real_estate": "房地产",
    "finance": "金融保险",
    "e_commerce": "电商零售",
    "technology": "科技互联网",
    "manufacturing": "制造业",
    "manufacturing_b2b": "制造业 B2B",
    "consumer_brand": "消费品牌",
    "professional_service": "专业服务",
    "tourism": "旅游酒店",
    "catering": "餐饮美食",
    "automobile": "汽车服务",
}

LAYER_LABELS = {
    "pool_layer": "入池层",
    "verification_layer": "验证/口碑层",
    "weight_layer": "权重层",
    "conversion_layer": "转化/承接层",
}

ALLOWED_LAYERS = set(LAYER_LABELS.keys())

AI_PLATFORM_TERMS = tuple(get_ai_platform_terms())
AI_PLATFORM_TERM_RE = "|".join(
    re.escape(term.lower()) for term in sorted(AI_PLATFORM_TERMS, key=len, reverse=True)
)

ALLOWED_KEYWORD_LAYERS = {
    "category",
    "region",
    "scenario",
    "proof",
    "conversion",
    "brand",
    "comparison",
    "other",
}

ALLOWED_SEARCH_ASSET_TYPES = {
    "official_site",
    "qualification",
    "case_page",
    "media_report",
    "faq",
    "comparison",
    "local_guide",
    "contact_page",
    "product_page",
    "other",
}


class ContentMatrixRequest(BaseModel):
    replace_existing: bool = Field(False, description="是否取消当前项目下未开始的旧任务后重新生成")
    max_tasks: int = Field(24, ge=1, le=80)
    apply_schedule: bool = Field(True, description="Apply first-month schedule and cost estimates to generated content tasks")
    start_date: Optional[datetime] = Field(None, description="Schedule start time. Defaults to current UTC time")


CONTENT_TYPE_BY_LAYER = {
    "pool_layer": "brand_intro",
    "verification_layer": "faq",
    "weight_layer": "comparison",
    "conversion_layer": "product",
}


def _task_priority(priority: int) -> str:
    if priority >= 85:
        return "high"
    if priority >= 60:
        return "medium"
    return "low"


def _content_type_for_group(group: QuestionGroup) -> str:
    intent = f"{group.intent_name or ''} {group.representative_question or ''}"
    if re.search(r"资质|证书|口碑|评价|通过率|质量|可信|合规", intent):
        return "faq"
    if re.search(r"对比|排名|测评|优势|指南|避坑|政策", intent):
        return "comparison"
    if re.search(r"价格|费用|报名|地址|电话|联系|流程|售后", intent):
        return "product"
    return CONTENT_TYPE_BY_LAYER.get(group.layer, "brand_intro")


LAYER_SCHEDULE_OFFSETS = {
    "verification_layer": 3,
    "pool_layer": 10,
    "weight_layer": 17,
    "conversion_layer": 24,
}

CONTENT_TYPE_COST_PRESETS = {
    "faq": {"tokens": 3500, "api": 0.8, "labor": 25},
    "brand_intro": {"tokens": 5200, "api": 1.2, "labor": 35},
    "product": {"tokens": 5600, "api": 1.3, "labor": 40},
    "comparison": {"tokens": 6800, "api": 1.8, "labor": 50},
    "case_study": {"tokens": 6200, "api": 1.6, "labor": 50},
    "tutorial": {"tokens": 7200, "api": 2.0, "labor": 60},
}


def _normalize_schedule_start(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _task_cost_preset(content_type: str, priority: str) -> dict:
    preset = CONTENT_TYPE_COST_PRESETS.get(content_type, {"tokens": 5000, "api": 1.2, "labor": 35}).copy()
    if priority == "high":
        preset["labor"] += 10
        preset["api"] += 0.3
    return preset


DIAGNOSIS_DIMENSION_PATTERNS = {
    "资质可信": r"资质|证书|认证|许可证|CAAC|AOPA|合规|正规",
    "价格费用": r"价格|费用|收费|学费|报价|成本",
    "地址联系": r"地址|电话|联系|官网|公众号|报名|咨询",
    "案例口碑": r"案例|客户|学员|评价|口碑|通过率|就业",
    "服务流程": r"流程|周期|步骤|交付|售后|复训|服务",
    "对比排名": r"对比|相比|排名|榜单|推荐|哪家好|优势",
}


def _safe_rate(success: int, total: int) -> float:
    return round((success / total) * 100, 1) if total else 0.0


def _derive_known_state(mention_rate: float, recommendation_rate: float) -> str:
    if mention_rate <= 0:
        return "AI样本中暂未识别品牌"
    if mention_rate < 40:
        return "AI偶尔知道品牌，但认知不稳定"
    if recommendation_rate < 30:
        return "AI知道品牌，但推荐意愿偏弱"
    return "AI已能在部分样本中推荐品牌"


def _brand_terms(brands: List[Brand], project_name: str) -> List[str]:
    terms = [project_name]
    for brand in brands:
        terms.append(brand.brand_name)
        terms.append(brand.company_name or "")
        for alias in _split_terms(brand.aliases):
            terms.append(alias)
    seen = []
    for term in terms:
        term = _clean_text(term, 80)
        if term and term not in seen:
            seen.append(term)
    return seen


def _extract_competitor_mentions(answer_texts: List[str], brand_terms: List[str]) -> List[Dict[str, Any]]:
    counter: Dict[str, int] = defaultdict(int)
    for text in answer_texts:
        text = _clean_text(text, 4000)
        candidates = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9（）()·]{2,30}(?:公司|机构|品牌|培训|中心|基地|学校)", text)
        for candidate in candidates:
            if any(term and term in candidate for term in brand_terms):
                continue
            if re.search(r"当前|本地|很多|一些|其他|目标|推荐|正规|培训机构|服务机构", candidate):
                continue
            counter[candidate] += 1
    return [
        {"name": name, "mention_count": count}
        for name, count in sorted(counter.items(), key=lambda item: item[1], reverse=True)[:8]
    ]


def _diagnosis_actions(mention_rate: float, recommendation_rate: float, dimension_counts: Dict[str, int], facts_count: int) -> List[Dict[str, str]]:
    actions = []
    if facts_count == 0:
        actions.append({
            "priority": "high",
            "action": "补充并确认公开事实",
            "reason": "当前缺少可公开引用的已确认品牌事实，后续诊断、内容和报告可信度都会受限。",
        })
    if mention_rate < 50:
        actions.append({
            "priority": "high",
            "action": "补基础验证层与入池层内容",
            "reason": "品牌提及率偏低，需要让联网型/平台型回答先稳定识别品牌主体。",
        })
    if recommendation_rate < 30:
        actions.append({
            "priority": "high",
            "action": "补推荐理由和对比证据",
            "reason": "推荐率偏低，需要补充资质、案例、场景、价格流程和第三方信源。",
        })
    if dimension_counts.get("地址联系", 0) == 0:
        actions.append({
            "priority": "medium",
            "action": "补转化承接信息",
            "reason": "样本中较少出现地址、电话、官网或报名路径，可能影响转化信息准确率。",
        })
    return actions


def _clean_text(value: Any, max_len: int = 1200) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_len]


def _industry_label(industry: Optional[str]) -> str:
    return INDUSTRY_LABELS.get(industry or "", industry or "通用行业")


def _split_terms(value: Optional[str]) -> List[str]:
    terms = []
    for part in re.split(r"[,，、/;；\n\r]+", str(value or "")):
        part = part.strip()
        if part and part not in terms:
            terms.append(part)
    return terms


def _looks_like_ai_platform_keyword_misuse(text: str) -> bool:
    """
    Detect questions that accidentally use AI platform names as service, brand, or audience terms.
    Example: "蒙霁空天智能适合哪些 deepseek".
    """
    normalized = _clean_text(text, 400).lower()
    if not normalized or not re.search(AI_PLATFORM_TERM_RE, normalized):
        return False
    misuse_patterns = [
        rf"(适合哪些|哪些|哪类|哪种)\s*({AI_PLATFORM_TERM_RE})",
        rf"({AI_PLATFORM_TERM_RE})\s*(哪家|推荐|怎么选|机构|品牌|服务|课程|培训|公司|产品|人群|用户)",
        rf"(哪家|推荐|怎么选|机构|品牌|服务|课程|培训|公司|产品|人群|用户)\s*({AI_PLATFORM_TERM_RE})",
    ]
    return any(re.search(pattern, normalized) for pattern in misuse_patterns)


def _sanitize_generated_question_text(value: Any, forbidden_terms: Optional[List[str]] = None) -> str:
    text = _clean_text(value, 260)
    if _looks_like_ai_platform_keyword_misuse(text):
        return ""
    for term in forbidden_terms or []:
        clean_term = str(term or "").strip()
        if clean_term and clean_term in text:
            return ""
    return text


def _infer_audience_label(project, facts: List[BrandFact]) -> str:
    text = " ".join([
        project.notes or "",
        _industry_label(project.industry),
        *(fact.public_wording or fact.value or "" for fact in facts[:80]),
    ])
    if re.search(r"退役军人|转业|转岗|就业|从业", text):
        return "转行或就业提升人群"
    if re.search(r"政府|法院|公安|应急|农牧|学校|企业|采购|机构|单位", text):
        return "个人和机构用户"
    if project.industry == "education_training" or re.search(r"考证|培训|课程|技能|执照", text):
        return "考证或技能提升人群"
    if project.industry in {"manufacturing", "manufacturing_b2b"}:
        return "企业采购方"
    return "目标用户"


def _json_from_llm_text(text: str) -> Dict[str, Any]:
    clean = re.sub(r"```(?:json)?\s*", "", text or "", flags=re.I).replace("```", "").strip()
    try:
        parsed = json.loads(clean)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}


def _priority_to_int(value: Any, default: int = 70) -> int:
    if isinstance(value, str):
        value = value.strip().upper()
        if value == "P0":
            return 90
        if value == "P1":
            return 75
        if value == "P2":
            return 55
    try:
        return max(1, min(100, int(value)))
    except (TypeError, ValueError):
        return default


def _stringify_question_meta(value: Any, limit: int = 1000) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    text = _clean_text(text, limit)
    return text or None


def _normalize_keyword_layer(value: Any) -> Optional[str]:
    text = _clean_text(value, 100)
    lowered = text.lower()
    if lowered in ALLOWED_KEYWORD_LAYERS:
        return lowered
    if re.search(r"品类|行业|类目|category", text, flags=re.I):
        return "category"
    if re.search(r"地域|地区|城市|本地|附近|region|geo|local", text, flags=re.I):
        return "region"
    if re.search(r"场景|用途|人群|需求|scenario|audience", text, flags=re.I):
        return "scenario"
    if re.search(r"证据|验证|资质|证书|合规|口碑|可信|proof|trust|qualification", text, flags=re.I):
        return "proof"
    if re.search(r"转化|价格|购买|报名|咨询|采购|地址|电话|conversion", text, flags=re.I):
        return "conversion"
    if re.search(r"品牌|主体|公司|brand", text, flags=re.I):
        return "brand"
    if re.search(r"对比|竞品|排名|优势|comparison|competitor", text, flags=re.I):
        return "comparison"
    return None


def _normalize_search_asset_type(value: Any) -> Optional[str]:
    text = _clean_text(value, 100)
    lowered = text.lower()
    if lowered in ALLOWED_SEARCH_ASSET_TYPES:
        return lowered
    if re.search(r"官网|官方网站|official", text, flags=re.I):
        return "official_site"
    if re.search(r"资质|证书|认证|许可|合规|qualification", text, flags=re.I):
        return "qualification"
    if re.search(r"案例|客户|项目|case", text, flags=re.I):
        return "case_page"
    if re.search(r"媒体|报道|新闻|稿件|media|news", text, flags=re.I):
        return "media_report"
    if re.search(r"问答|FAQ|常见问题|指南", text, flags=re.I):
        return "faq"
    if re.search(r"对比|测评|竞品|comparison", text, flags=re.I):
        return "comparison"
    if re.search(r"本地|地区|城市|local", text, flags=re.I):
        return "local_guide"
    if re.search(r"联系|地址|电话|报名|咨询|contact", text, flags=re.I):
        return "contact_page"
    if re.search(r"产品|服务|课程|方案|product", text, flags=re.I):
        return "product_page"
    return None


def _infer_keyword_layer(question_text: str, layer: str, tags: str = "") -> str:
    text = f"{question_text or ''} {tags or ''}"
    if re.search(r"资质|证书|编号|合规|核验|真假|正规|靠谱吗|口碑|评价|案例|通过率|认证|许可", text, flags=re.I):
        return "proof"
    if re.search(r"价格|费用|收费|报价|购买|报名|咨询|地址|电话|联系|预约|采购|流程|售后|怎么做", text, flags=re.I):
        return "conversion"
    if re.search(r"对比|相比|排名|榜单|优势|测评|哪家更|哪个更|竞品", text, flags=re.I):
        return "comparison"
    if re.search(r"附近|本地|地区|城市|包头|天津|北京|上海|深圳|广州|成都|杭州|内蒙古", text, flags=re.I):
        return "region"
    if re.search(r"适合|场景|人群|用途|应用|需求|解决", text, flags=re.I):
        return "scenario"
    if re.search(r"品牌|公司|机构|主体|产品|服务", text, flags=re.I):
        return "brand"
    if layer == "verification_layer":
        return "proof"
    if layer == "conversion_layer":
        return "conversion"
    if layer == "weight_layer":
        return "comparison"
    return "category"


def _default_question_bridge_meta(question_text: str, layer: str, tags: str = "") -> Dict[str, str]:
    keyword_layer = _infer_keyword_layer(question_text, layer, tags)
    mapping = {
        "category": {
            "knowledge_need": "需要品类定义、服务范围、适用对象和行业基础解释，帮助 AI 判断品牌是否能进入候选答案。",
            "search_asset_type": "faq",
        },
        "region": {
            "knowledge_need": "需要地区覆盖、服务边界、本地地址、本地案例和可公开核验的主体信息。",
            "search_asset_type": "local_guide",
        },
        "scenario": {
            "knowledge_need": "需要用户画像、使用场景、需求痛点、产品或服务匹配边界和真实案例。",
            "search_asset_type": "faq",
        },
        "proof": {
            "knowledge_need": "需要资质证书、证书编号、有效期、地址、案例、评价和官方核验入口等可验证证据。",
            "search_asset_type": "qualification",
        },
        "conversion": {
            "knowledge_need": "需要价格、服务内容、地址、联系方式、咨询或购买流程、交付周期和售后边界。",
            "search_asset_type": "contact_page",
        },
        "brand": {
            "knowledge_need": "需要品牌主体、公司简介、服务边界、公开资料来源和已确认品牌事实。",
            "search_asset_type": "official_site",
        },
        "comparison": {
            "knowledge_need": "需要可对比维度、竞品差异、案例、参数、价格区间、口碑和第三方来源。",
            "search_asset_type": "comparison",
        },
        "other": {
            "knowledge_need": "需要补充能够回答该问题的公开事实、证据来源和内容素材。",
            "search_asset_type": "faq",
        },
    }
    return {"keyword_layer": keyword_layer, **mapping.get(keyword_layer, mapping["other"])}


def _default_question_meta(question_text: str, layer: str, tags: str = "") -> Dict[str, str]:
    text = question_text or ""
    if layer == "verification_layer":
        return {
            "question_formula": "品牌/主体词 + 合规/资质/口碑/评价/真伪核验",
            "business_value": "high",
            "evidence_support": "需要已确认的资质认证（如适用）、地址、产品/服务边界、案例、评价、交付结果、官方可核验入口等事实。",
            "content_actionability": "适合补可信信息页、品牌FAQ、核验指南、案例稿、第三方媒体稿。",
            "recommended_platforms": "website,official_faq,baijiahao,zhihu",
        }
    if layer == "conversion_layer":
        return {
            "question_formula": "品牌/产品/服务词 + 价格/购买/咨询/报名/采购/地址/流程",
            "business_value": "high",
            "evidence_support": "需要已确认的价格、产品/服务范围、地址、购买/咨询/报名/采购流程、交付周期和公开联系方式等事实。",
            "content_actionability": "适合补价格说明、购买/咨询/报名/采购指南、官网FAQ、公众号承接页。",
            "recommended_platforms": "official_account,website,official_faq,baijiahao",
        }
    if layer == "weight_layer":
        return {
            "question_formula": "品牌/品类词 + 对比/排名/优势/避坑",
            "business_value": "medium",
            "evidence_support": "需要已确认的产品参数、服务能力、案例、荣誉、行业合规依据和可对比维度。",
            "content_actionability": "适合补对比测评、选择标准、案例复盘、行业科普。",
            "recommended_platforms": "zhihu,baijiahao,toutiao,media",
        }
    return {
        "question_formula": "地域/品类/场景词 + 推荐/哪家好/怎么选",
        "business_value": "medium",
        "evidence_support": f"需要品牌主体、服务边界、地区覆盖、可信事实和用户场景证据。标签：{tags or '暂无'}",
        "content_actionability": "适合补本地指南、品牌介绍、入池类媒体稿、问答内容。",
        "recommended_platforms": "baijiahao,toutiao,media,website",
    }


def _normalize_layer(layer: Any, intent_name: str = "") -> str:
    value = str(layer or "").strip()
    if value in ALLOWED_LAYERS:
        return value
    text = f"{value} {intent_name}"
    if re.search(r"转化|承接|报名|价格|费用|地址|电话|联系|咨询|购买", text):
        return "conversion_layer"
    if re.search(r"权重|对比|排名|测评|优势|指南|教程|政策|合规", text):
        return "weight_layer"
    if re.search(r"验证|口碑|资质|证书|案例|评价|可信|通过率", text):
        return "verification_layer"
    return "pool_layer"


def _infer_service(project, brand_name: str, facts: List[BrandFact]) -> str:
    text = " ".join([
        project.name or "",
        project.industry or "",
        project.notes or "",
        *(fact.public_wording or fact.value or "" for fact in facts[:80]),
    ])
    return infer_service_from_archetype(
        project.industry,
        text,
        brand_name,
        _industry_label(project.industry),
    )


def _industry_question_copy(project, service: str) -> Dict[str, str]:
    return get_industry_question_copy(project.industry, service, project.region)


def _extract_fact_context(facts: List[BrandFact], limit: int = 28) -> Tuple[str, List[str], List[str]]:
    lines = []
    credentials = []
    competitors = []
    for fact in facts[:limit]:
        value = _clean_text(fact.public_wording or fact.value, 260)
        if not value:
            continue
        status = "已确认" if fact.status == "confirmed" else "待确认"
        fact_type = fact.fact_type or "资料"
        lines.append(f"- [{status}/{fact_type}] {value}")
        if re.search(r"资质|证书|编号|许可证|合格证|执照|专利|软著|信用代码|CAAC|AOPA", value, flags=re.I):
            credentials.append(value)
        if re.search(r"竞品|对比|相比|vs|VS|同行|同类", value, flags=re.I):
            competitors.append(value)
    return "\n".join(lines), credentials[:6], competitors[:3]


def _build_template_groups(project, brand_name: str, facts: List[BrandFact]) -> List[Dict[str, Any]]:
    region = project.region or "本地"
    industry = _industry_label(project.industry)
    service = _infer_service(project, brand_name, facts)
    fact_context, credentials, competitors = _extract_fact_context(facts)
    audience_label = _infer_audience_label(project, facts)
    copy = _industry_question_copy(project, service)
    entity_label = copy["entity_label"]
    subject = copy["subject"]
    competitor = competitors[0] if competitors else f"同类{entity_label}"

    has_credential_evidence = bool(credentials)
    qualification_question = (
        copy["verified_question"]
        if has_credential_evidence
        else f"{brand_name}{copy['trust_question']}"
    )

    raw_groups = [
        {
            "layer": "pool_layer",
            "intent_name": f"本地推荐/入池 - {brand_name}",
            "representative_question": f"{region}{subject}哪家靠谱？",
            "priority": 88,
            "questions": [
                f"{region}{subject}推荐",
                f"{region}{subject}哪家靠谱？",
                f"想了解{service}，应该怎么选{entity_label}？",
                f"{industry}领域有哪些值得关注的{subject}？",
                f"哪些{audience_label}适合选择{brand_name}{service}？",
                f"{region}口碑好的{subject}有哪些？",
            ],
        },
        {
            "layer": "verification_layer",
            "intent_name": f"资质可信/验证 - {brand_name}",
            "representative_question": qualification_question,
            "priority": 92,
            "questions": [
                qualification_question,
                f"{brand_name}{copy['trust_question']}",
                f"{brand_name}{service}质量怎么样？",
                f"{brand_name}{copy['proof_question']}",
                f"{brand_name}{copy['outcome_question']}",
                copy["compliance_question"],
            ],
        },
        {
            "layer": "weight_layer",
            "intent_name": f"对比/权重 - {brand_name}",
            "representative_question": f"{brand_name}和{competitor}相比有什么优势？",
            "priority": 82,
            "questions": [
                f"{brand_name}和{competitor}相比有什么优势？",
                f"{region}{subject}排名或口碑榜怎么参考？",
                f"{brand_name}的{copy['quality_angle']}有哪些亮点？",
                f"{service}费用、周期和服务内容应该怎么对比？",
                f"{brand_name}{copy['fit_question']}",
                f"{service}选择时最容易踩哪些坑？",
            ],
        },
        {
            "layer": "weight_layer",
            "intent_name": f"政策合规/指南 - {brand_name}",
            "representative_question": f"{service}需要满足哪些政策和合规要求？",
            "priority": 78,
            "questions": [
                f"{service}需要满足哪些政策和合规要求？",
                f"{service}{copy['material_check_question']}",
                f"{region}{service}{copy['prepare_action']}",
                f"{service}{copy['journey_question']}",
                f"{brand_name}能提供哪些官方或第三方背书资料？",
            ],
        },
        {
            "layer": "conversion_layer",
            "intent_name": f"{copy['conversion_intent']} - {brand_name}",
            "representative_question": f"{brand_name}{service}价格多少钱？",
            "priority": 84,
            "questions": [
                f"{brand_name}{service}价格多少钱？",
                f"{brand_name}{copy['process_question']}",
                f"{brand_name}地址和联系方式是什么？",
                f"{brand_name}{copy['cycle_question']}",
                f"{brand_name}{copy['support_policy']}",
                f"{brand_name}官网、公众号或客服入口在哪里？",
            ],
        },
    ]

    if fact_context:
        raw_groups[1]["questions"].append(f"{brand_name}{copy['public_material_question']}")

    return _coerce_question_groups(
        {"groups": raw_groups},
        forbidden_terms=get_industry_forbidden_terms(project.industry),
    )


def _coerce_question_groups(
    parsed: Dict[str, Any],
    forbidden_terms: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    raw_groups = parsed.get("groups") or parsed.get("question_groups") or []
    if not isinstance(raw_groups, list):
        return []

    groups: List[Dict[str, Any]] = []
    seen_questions = set()
    total_questions = 0

    for idx, raw in enumerate(raw_groups):
        if not isinstance(raw, dict):
            continue
        intent_name = _clean_text(raw.get("intent_name") or raw.get("name") or raw.get("cluster") or f"问题组 {idx + 1}", 180)
        layer = _normalize_layer(raw.get("layer"), intent_name)
        priority = _priority_to_int(raw.get("priority"), 80 if layer in {"pool_layer", "verification_layer"} else 70)
        questions: List[Dict[str, Any]] = []

        raw_questions = raw.get("questions") or raw.get("items") or []
        if isinstance(raw_questions, str):
            raw_questions = _split_terms(raw_questions)
        if not isinstance(raw_questions, list):
            raw_questions = []

        for item in raw_questions:
            if isinstance(item, dict):
                q_text = item.get("question_text") or item.get("text") or item.get("question") or item.get("query")
                q_priority = _priority_to_int(item.get("priority"), priority)
                sample_policy = _clean_text(item.get("sample_policy") or "mvp", 30) or "mvp"
                question_type = _clean_text(item.get("question_type") or item.get("type") or "brand_reputation", 100) or "brand_reputation"
                raw_tags = item.get("tags") or item.get("labels") or ""
                tags = "，".join(_split_terms(raw_tags)) if isinstance(raw_tags, str) else "，".join(str(tag) for tag in raw_tags[:8]) if isinstance(raw_tags, list) else ""
                focus = bool(item.get("focus") or item.get("important") or False)
                keyword_breakdown = _stringify_question_meta(item.get("keyword_breakdown") or item.get("keywords"), 1200)
                keyword_layer = _stringify_question_meta(item.get("keyword_layer") or item.get("keyword_level"), 100)
                question_formula = _stringify_question_meta(item.get("question_formula") or item.get("formula"), 500)
                knowledge_need = _stringify_question_meta(
                    item.get("knowledge_need") or item.get("required_knowledge") or item.get("knowledge_assets"),
                    1200,
                )
                search_asset_type = _stringify_question_meta(item.get("search_asset_type") or item.get("asset_type"), 100)
                business_value = _stringify_question_meta(item.get("business_value") or item.get("commercial_value"), 100)
                evidence_support = _stringify_question_meta(item.get("evidence_support") or item.get("required_facts") or item.get("evidence_need"), 1200)
                content_actionability = _stringify_question_meta(item.get("content_actionability") or item.get("content_suggestion"), 1200)
                recommended_platforms = _stringify_question_meta(item.get("recommended_platforms") or item.get("platforms"), 500)
            else:
                q_text = item
                q_priority = priority
                sample_policy = "mvp"
                question_type = "brand_reputation"
                tags = ""
                focus = False
                keyword_breakdown = None
                keyword_layer = None
                question_formula = None
                knowledge_need = None
                search_asset_type = None
                business_value = None
                evidence_support = None
                content_actionability = None
                recommended_platforms = None
            q_text = _sanitize_generated_question_text(q_text, forbidden_terms=forbidden_terms)
            if not q_text or q_text in seen_questions:
                continue
            seen_questions.add(q_text)
            defaults = _default_question_meta(q_text, layer, tags)
            bridge_defaults = _default_question_bridge_meta(q_text, layer, tags)
            keyword_breakdown = keyword_breakdown or json.dumps({
                "question_terms": _split_terms(q_text),
                "tags": _split_terms(tags),
                "layer": layer,
            }, ensure_ascii=False)
            keyword_layer = _normalize_keyword_layer(keyword_layer) or bridge_defaults["keyword_layer"]
            question_formula = question_formula or defaults["question_formula"]
            knowledge_need = knowledge_need or bridge_defaults["knowledge_need"]
            search_asset_type = _normalize_search_asset_type(search_asset_type) or bridge_defaults["search_asset_type"]
            business_value = business_value or defaults["business_value"]
            evidence_support = evidence_support or defaults["evidence_support"]
            content_actionability = content_actionability or defaults["content_actionability"]
            recommended_platforms = recommended_platforms or defaults["recommended_platforms"]
            questions.append({
                "question_text": q_text,
                "question_type": question_type,
                "tags": tags,
                "keyword_breakdown": keyword_breakdown,
                "keyword_layer": keyword_layer,
                "question_formula": question_formula,
                "knowledge_need": knowledge_need,
                "search_asset_type": search_asset_type,
                "business_value": business_value,
                "evidence_support": evidence_support,
                "content_actionability": content_actionability,
                "recommended_platforms": recommended_platforms,
                "priority": q_priority,
                "sample_policy": sample_policy,
                "enabled": True,
                "focus": focus,
            })
            total_questions += 1
            if len(questions) >= 8 or total_questions >= 36:
                break

        representative = _sanitize_generated_question_text(
            raw.get("representative_question"),
            forbidden_terms=forbidden_terms,
        )
        if not representative and questions:
            representative = questions[0]["question_text"]
        if not representative or not questions:
            continue
        groups.append({
            "layer": layer,
            "intent_name": intent_name,
            "representative_question": representative,
            "priority": priority,
            "questions": questions,
        })
        if len(groups) >= 6 or total_questions >= 36:
            break

    return groups


async def _generate_question_groups_with_llm(project, brand_name: str, facts: List[BrandFact]) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    try:
        from app.llm.client import LLMClientFactory
        from app.llm.registry import get_model_registry

        registry = get_model_registry()
        config = registry.get_default_model()
        if not config:
            return None, "未配置可用的大模型，已使用本地矩阵模板生成"

        fact_context, credentials, _ = _extract_fact_context(facts, limit=36)
        service = _infer_service(project, brand_name, facts)
        archetype = get_question_archetype(project.industry)
        context = {
            "project_name": project.name,
            "brand_name": brand_name,
            "industry": _industry_label(project.industry),
            "region": project.region,
            "service_or_product": service,
            "industry_template": {
                "entity_label": archetype.get("entity_label"),
                "forbidden_terms": archetype.get("forbidden_terms") or [],
                "positive_examples": archetype.get("positive_examples") or [],
                "negative_examples": archetype.get("negative_examples") or [],
            },
            "excluded_ai_platform_terms": list(AI_PLATFORM_TERMS),
            "monitoring_ai_platform_note": "这些是检测平台/模型名称，只用于后续监测，不是用户、服务、品类或问题关键词；生成问题时不要写入问题文本。",
            "notes": project.notes,
            "known_facts": fact_context,
            "credential_clues": credentials,
        }
        prompt = f"""
你是 GEO/AIO 生成式引擎优化的问题矩阵专家。请基于项目资料生成问题库，不要生成文章。

核心逻辑参考：
1. 先覆盖真实用户会向 AI 提问的搜索意图，而不是机械关键词堆叠。
2. 必须覆盖这些簇：品类推荐/品牌入池、可信验证、价格/购买/咨询/报名/采购承接、产品或服务匹配、竞品对比、案例口碑、政策合规。
3. 按四层组织：pool_layer 入池层、verification_layer 验证/口碑层、weight_layer 权重层、conversion_layer 转化/承接层。
4. 如果资料里没有明确事实，只能写成“有没有/如何核验/怎么样”类问题，不要把未确认内容写成事实。
5. 问题要像真实用户会问 AI 的自然语言，避免重复“哪家好 推荐”。
6. 如果有城市/地区，至少一半问题自然包含地区词；如果有品牌名，验证层和转化层必须包含品牌名。
7. 不要默认使用培训行业词，例如“课程、报名、学员、通过率、复训、师资、校区”；只有项目资料明确属于培训/教育时才可使用。
8. 不要把检测平台或模型名称写入问题文本，例如 DeepSeek、Kimi、豆包、文心、通义、ChatGPT、Gemini。

项目资料：
{json.dumps(context, ensure_ascii=False, indent=2)}

请只输出 JSON，不要 Markdown，不要解释。格式：
{{
  "groups": [
    {{
      "layer": "pool_layer",
      "intent_name": "本地推荐/入池 - 品牌名",
      "representative_question": "代表性问题",
      "priority": 85,
      "questions": [
        {{"question_text": "具体问题", "priority": 85, "sample_policy": "mvp"}}
      ]
    }}
  ]
}}

数量要求：生成 5 个问题组，每组 5-7 个问题，总量 25-35 个。
"""
        prompt = render_prompt_template("geo/question_bank_v1.md", {
            "project_context_json": json.dumps(context, ensure_ascii=False, indent=2),
        })
        client = LLMClientFactory.create_client_from_config({
            "provider": config.provider,
            "model": config.model,
            "api_key": config.api_key,
            "base_url": config.base_url,
            "input_price_per_1k": config.input_price_per_1k,
            "output_price_per_1k": config.output_price_per_1k,
        })
        response = await client.chat(
            [
                {"role": "system", "content": "你只输出可解析 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
            max_tokens=3600,
        )
        groups = _coerce_question_groups(
            _json_from_llm_text(response.content),
            forbidden_terms=archetype.get("forbidden_terms") or [],
        )
        if len(groups) >= 3 and sum(len(g["questions"]) for g in groups) >= 12:
            return groups, None
        return None, "大模型返回的问题矩阵数量不足，已使用本地矩阵模板兜底"
    except Exception as exc:
        return None, f"大模型生成失败，已使用本地矩阵模板兜底：{str(exc)[:180]}"


def _build_question_generation_strategy(project, brand_name: str, facts: List[BrandFact]) -> Dict[str, Any]:
    fact_context, credentials, _ = _extract_fact_context(facts, limit=36)
    service = _infer_service(project, brand_name, facts)
    credential_terms = []
    for item in credentials:
        for term in _split_terms(item):
            if term and term not in credential_terms:
                credential_terms.append(term)
    keyword_breakdown = {
        "brand_terms": [term for term in _split_terms(brand_name) if term],
        "geo_terms": [term for term in _split_terms(project.region) if term],
        "industry_terms": [term for term in _split_terms(_industry_label(project.industry)) if term],
        "service_terms": [term for term in _split_terms(service) if term],
        "credential_terms": credential_terms[:12],
        "fact_source_preview": fact_context[:500],
    }
    formulas = [
        {
            "layer": "pool_layer",
            "name": "本地品类推荐",
            "formula": "地区词 + 服务/品类词 + 哪家靠谱/推荐/怎么选",
        },
        {
            "layer": "verification_layer",
            "name": "资质与可信核验",
            "formula": "品牌词 + 资质/证书/编号/地址 + 是否真实/如何核验",
        },
        {
            "layer": "weight_layer",
            "name": "对比与权重提升",
            "formula": "品牌词 + 竞品/同类机构 + 优势/价格/案例/口碑对比",
        },
        {
            "layer": "conversion_layer",
            "name": "转化承接",
            "formula": "品牌词 + 价格/流程/地址/预约/售后 + 具体怎么做",
        },
    ]
    return {
        "keyword_breakdown": keyword_breakdown,
        "question_formulas": formulas,
        "principle": "问题库优先模拟真实用户向 AI 提问的自然语言，并把事实库中的资质、产品、地址、价格、案例等可信信息转成可检测的问题线索。",
    }


@router.get("", response_model=List[ProjectOut])
async def list_projects(
    industry: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """获取项目列表"""
    service = ProjectService(db)
    projects = await service.list_projects(industry=industry, status=status, skip=skip, limit=limit)
    return projects


@router.post("", response_model=ProjectOut)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("project_owner")),
):
    """创建新项目"""
    service = ProjectService(db)
    project = await service.create_project(data)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """获取项目详情"""
    service = ProjectService(db)
    project = await service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("project_owner")),
):
    """更新项目"""
    service = ProjectService(db)
    project = await service.update_project(project_id, data)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}")
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("project_owner")),
):
    """删除项目，并同步删除该项目下的关联数据。"""
    service = ProjectService(db)
    deleted = await service.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"message": "Project deleted", "id": str(project_id)}


@router.post("/{project_id}/diagnose-gaps")
async def diagnose_gaps(
    project_id: UUID,
    provided_fields: List[str] = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("collector", "strategist", "project_owner")),
):
    """资料缺口诊断"""
    service = ProjectService(db)
    result = await service.diagnose_gaps(project_id, provided_fields)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{project_id}/diagnose-gaps-from-facts")
async def diagnose_gaps_from_facts(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("collector", "strategist", "project_owner")),
):
    """基于当前项目事实库自动诊断资料缺口，并返回补齐动作。"""
    service = ProjectService(db)
    result = await service.diagnose_gaps_from_facts(project_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{project_id}/brands")
async def get_project_brands(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """获取项目关联的品牌列表"""
    result = await db.execute(select(Brand).where(Brand.project_id == project_id))
    brands = result.scalars().all()
    return [
        {
            "id": str(b.id),
            "project_id": str(b.project_id),
            "brand_name": b.brand_name,
            "company_name": b.company_name,
            "official_site": b.official_site,
            "description": b.description,
            "aliases": b.aliases,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "updated_at": b.updated_at.isoformat() if b.updated_at else None,
        }
        for b in brands
    ]


@router.get("/{project_id}/brand-facts-summary")
async def get_brand_facts_summary(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """获取项目品牌事实库摘要"""
    service = ProjectService(db)
    result = await service.get_brand_facts_summary(project_id)
    return result


@router.get("/{project_id}/diagnosis-report")
async def get_project_diagnosis_report(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    基于已录入检测样本生成品牌 AI 体检、回答模式和竞品差距的观察报告。
    该接口只做可解释的样本归纳，不宣称掌握模型内部排序逻辑。
    """
    service = ProjectService(db)
    project = await service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    brands_result = await db.execute(select(Brand).where(Brand.project_id == project_id))
    brands = list(brands_result.scalars().all())
    brand_terms = _brand_terms(brands, project.name)

    facts_result = await db.execute(
        select(BrandFact)
        .join(Brand, BrandFact.brand_id == Brand.id)
        .where(
            Brand.project_id == project_id,
            BrandFact.status == "confirmed",
            BrandFact.fact_scope == "public",
        )
    )
    public_facts = list(facts_result.scalars().all())

    samples_result = await db.execute(
        select(MonitoringSample, Question, QuestionGroup, MonitoringRun)
        .select_from(MonitoringSample)
        .join(Question, MonitoringSample.question_id == Question.id)
        .join(QuestionGroup, Question.group_id == QuestionGroup.id)
        .join(MonitoringRun, MonitoringSample.run_id == MonitoringRun.id)
        .where(MonitoringRun.project_id == project_id)
        .order_by(MonitoringSample.sampled_at.desc())
    )
    rows = samples_result.all()
    samples = [row[0] for row in rows]
    total = len(samples)
    mentioned = sum(1 for sample in samples if sample.brand_mentioned)
    recommended = sum(1 for sample in samples if sample.recommended)
    answer_texts = [sample.answer_text or "" for sample in samples if sample.answer_text]

    dimension_counts = {name: 0 for name in DIAGNOSIS_DIMENSION_PATTERNS}
    for text in answer_texts:
        for name, pattern in DIAGNOSIS_DIMENSION_PATTERNS.items():
            if re.search(pattern, text, flags=re.I):
                dimension_counts[name] += 1

    layer_summary: Dict[str, Dict[str, Any]] = {}
    for sample, question, group, run in rows:
        key = group.layer
        item = layer_summary.setdefault(key, {
            "layer": key,
            "layer_label": LAYER_LABELS.get(key, key),
            "sample_count": 0,
            "mentioned": 0,
            "recommended": 0,
            "questions": set(),
            "mechanisms": set(),
        })
        item["sample_count"] += 1
        item["mentioned"] += 1 if sample.brand_mentioned else 0
        item["recommended"] += 1 if sample.recommended else 0
        item["questions"].add(question.question_text)
        item["mechanisms"].add(run.mechanism_type)

    layer_items = []
    for item in layer_summary.values():
        sample_count = item["sample_count"]
        layer_items.append({
            "layer": item["layer"],
            "layer_label": item["layer_label"],
            "sample_count": sample_count,
            "mention_rate": _safe_rate(item["mentioned"], sample_count),
            "recommendation_rate": _safe_rate(item["recommended"], sample_count),
            "questions": sorted(item["questions"])[:8],
            "mechanisms": sorted(item["mechanisms"]),
        })

    mention_rate = _safe_rate(mentioned, total)
    recommendation_rate = _safe_rate(recommended, total)
    competitors = _extract_competitor_mentions(answer_texts, brand_terms)

    return {
        "project_id": str(project_id),
        "sample_count": total,
        "brand_health": {
            "brand_terms": brand_terms,
            "mentioned": mentioned,
            "recommended": recommended,
            "mention_rate": mention_rate,
            "recommendation_rate": recommendation_rate,
            "known_state": _derive_known_state(mention_rate, recommendation_rate),
            "public_confirmed_facts": len(public_facts),
        },
        "answer_pattern": {
            "dimension_counts": [
                {"dimension": name, "sample_hits": count}
                for name, count in sorted(dimension_counts.items(), key=lambda item: item[1], reverse=True)
            ],
            "layer_summary": layer_items,
            "source_signal": {
                "explicit_citations": sum(sample.explicit_citations for sample in samples),
                "inferred_source_matches": sum(sample.inferred_source_matches for sample in samples),
                "note": "显式引用和推定匹配不能合并，只能分别解释。",
            },
        },
        "competitor_gap": {
            "detected_competitors": competitors,
            "target_brand_mentions": mentioned,
            "note": "竞品识别来自样本文本中的实体提取，属于观察线索；正式报告需人工复核竞品名单。",
        },
        "actions": _diagnosis_actions(mention_rate, recommendation_rate, dimension_counts, len(public_facts)),
        "limitations": [
            "该诊断基于系统内已录入样本，不能代表所有 AI 产品长期表现。",
            "回答模式分析只归纳可观察样本，不声称掌握模型内部排序逻辑。",
            "样本数不足时，结果只能作为初步观察，不应用作验收结论。",
        ],
    }


@router.post("/{project_id}/generate-content-matrix")
async def generate_content_matrix(
    project_id: UUID,
    data: Optional[ContentMatrixRequest] = Body(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("strategist", "project_owner")),
):
    """
    将当前有效问题矩阵转成内容任务。
    每个问题组生成一个可写作任务，避免问题库和内容管理之间断链。
    """
    service = ProjectService(db)
    project = await service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    data = data or ContentMatrixRequest()

    groups_result = await db.execute(
        select(QuestionGroup)
        .where(
            QuestionGroup.project_id == project_id,
            QuestionGroup.status != "archived",
        )
        .order_by(QuestionGroup.priority.desc(), QuestionGroup.created_at.desc())
        .limit(data.max_tasks)
    )
    groups = list(groups_result.scalars().all())
    if not groups:
        raise HTTPException(status_code=400, detail="当前项目还没有可用的问题矩阵，请先生成问题库")

    cancelled_tasks = 0
    if data.replace_existing:
        existing_result = await db.execute(
            select(ContentTask).where(
                ContentTask.project_id == project_id,
                ContentTask.status.in_(["draft", "in_progress", "review", "rework", "approved"]),
            )
        )
        for task in existing_result.scalars().all():
            task.status = "cancelled"
            cancelled_tasks += 1
        if cancelled_tasks:
            await db.flush()

    existing_result = await db.execute(
        select(ContentTask).where(
            ContentTask.project_id == project_id,
            ContentTask.status != "cancelled",
        )
    )
    existing_keys = {
        (str(task.group_id), task.content_type, task.layer)
        for task in existing_result.scalars().all()
        if task.group_id
    }

    created_tasks: List[ContentTask] = []
    skipped_tasks = 0
    schedule_start = _normalize_schedule_start(data.start_date)
    layer_schedule_counts: dict[str, int] = defaultdict(int)
    for group in groups:
        content_type = _content_type_for_group(group)
        key = (str(group.id), content_type, group.layer)
        if key in existing_keys:
            skipped_tasks += 1
            continue
        priority = _task_priority(group.priority or 0)
        cost_preset = _task_cost_preset(content_type, priority)
        due_date = None
        if data.apply_schedule:
            layer_index = layer_schedule_counts[group.layer]
            layer_schedule_counts[group.layer] += 1
            due_date = schedule_start + timedelta(
                days=LAYER_SCHEDULE_OFFSETS.get(group.layer, 10) + layer_index * 2
            )
        task = ContentTask(
            project_id=project_id,
            group_id=group.id,
            content_type=content_type,
            layer=group.layer,
            priority=priority,
            status="draft",
            due_date=due_date,
            estimated_token_cost=cost_preset["tokens"],
            estimated_api_cost=cost_preset["api"],
            estimated_labor_minutes=cost_preset["labor"],
        )
        db.add(task)
        created_tasks.append(task)
        existing_keys.add(key)

    await db.commit()
    for task in created_tasks:
        await db.refresh(task)

    content_matrix = [
        {
            "layer": task.layer,
            "content_type": task.content_type,
            "priority": task.priority,
            "estimated_articles": 1,
        }
        for task in created_tasks
    ]
    budget_summary = StrategyAgent().estimate_budget(content_matrix, article_count=len(created_tasks)) if created_tasks else None

    return {
        "project_id": str(project_id),
        "source_groups": len(groups),
        "created_tasks": len(created_tasks),
        "skipped_tasks": skipped_tasks,
        "cancelled_tasks": cancelled_tasks,
        "schedule": {
            "applied": data.apply_schedule,
            "start_date": schedule_start.isoformat(),
            "first_due_date": min((task.due_date for task in created_tasks if task.due_date), default=None).isoformat()
            if any(task.due_date for task in created_tasks) else None,
            "last_due_date": max((task.due_date for task in created_tasks if task.due_date), default=None).isoformat()
            if any(task.due_date for task in created_tasks) else None,
        },
        "budget_estimate": budget_summary,
        "tasks": [
            {
                "id": str(task.id),
                "group_id": str(task.group_id) if task.group_id else None,
                "content_type": task.content_type,
                "layer": task.layer,
                "priority": task.priority,
                "status": task.status,
                "due_date": task.due_date.isoformat() if task.due_date else None,
                "estimated_token_cost": float(task.estimated_token_cost) if task.estimated_token_cost is not None else None,
                "estimated_api_cost": float(task.estimated_api_cost) if task.estimated_api_cost is not None else None,
                "estimated_labor_minutes": float(task.estimated_labor_minutes) if task.estimated_labor_minutes is not None else None,
            }
            for task in created_tasks
        ],
    }


@router.post("/{project_id}/generate-question-bank", dependencies=[Depends(require_roles("strategist", "project_owner"))])
async def generate_question_bank(
    project_id: UUID,
    brand_name: Optional[str] = None,
    replace_existing: bool = Query(True, description="重新生成时归档旧问题矩阵，避免重复累加"),
    db: AsyncSession = Depends(get_db)
):
    """
    生成 GEO 问题矩阵。
    优先使用用户配置的大模型生成；没有可用模型或模型失败时，使用原项目同源的确定性矩阵模板兜底。
    """
    service = ProjectService(db)
    project = await service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    brand_result = await db.execute(
        select(Brand).where(Brand.project_id == project_id).order_by(Brand.created_at.asc())
    )
    brands = list(brand_result.scalars().all())
    primary_brand = brands[0] if brands else None
    effective_brand_name = (
        brand_name
        or (primary_brand.brand_name if primary_brand else None)
        or project.name
        or "该品牌"
    )

    facts_result = await db.execute(
        select(BrandFact)
        .join(Brand, BrandFact.brand_id == Brand.id)
        .where(Brand.project_id == project_id)
        .order_by(BrandFact.created_at.desc())
        .limit(120)
    )
    facts = list(facts_result.scalars().all())

    generated_groups, fallback_reason = await _generate_question_groups_with_llm(
        project,
        effective_brand_name,
        facts,
    )
    source = "llm"
    if not generated_groups:
        generated_groups = _build_template_groups(project, effective_brand_name, facts)
        source = "template"

    if not generated_groups:
        raise HTTPException(status_code=500, detail="Failed to generate question bank")

    archived_groups = 0
    if replace_existing:
        existing_result = await db.execute(
            select(QuestionGroup).where(
                QuestionGroup.project_id == project_id,
                QuestionGroup.status != "archived",
            )
        )
        existing_groups = list(existing_result.scalars().all())
        for group in existing_groups:
            group.status = "archived"
        archived_groups = len(existing_groups)
        if archived_groups:
            await db.flush()

    created_groups: List[QuestionGroup] = []
    created_questions: List[Question] = []

    for group_data in generated_groups:
        group = QuestionGroup(
            project_id=project_id,
            layer=group_data["layer"],
            intent_name=group_data["intent_name"],
            representative_question=group_data["representative_question"],
            priority=group_data["priority"],
            status="active",
        )
        db.add(group)
        await db.flush()

        for question_data in group_data["questions"]:
            question = Question(
                group_id=group.id,
                question_text=question_data["question_text"],
                question_type=question_data.get("question_type") or "brand_reputation",
                tags=question_data.get("tags"),
                keyword_breakdown=question_data.get("keyword_breakdown"),
                keyword_layer=question_data.get("keyword_layer"),
                question_formula=question_data.get("question_formula"),
                knowledge_need=question_data.get("knowledge_need"),
                search_asset_type=question_data.get("search_asset_type"),
                business_value=question_data.get("business_value"),
                evidence_support=question_data.get("evidence_support"),
                content_actionability=question_data.get("content_actionability"),
                recommended_platforms=question_data.get("recommended_platforms"),
                priority=question_data["priority"],
                sample_policy=question_data["sample_policy"],
                enabled=question_data.get("enabled", True),
                focus=question_data.get("focus", False),
            )
            db.add(question)
            created_questions.append(question)

        created_groups.append(group)

    await db.commit()

    for group in created_groups:
        await db.refresh(group)
    for question in created_questions:
        await db.refresh(question)

    group_ids = [g.id for g in created_groups]
    result = await db.execute(
        select(QuestionGroup)
        .where(QuestionGroup.id.in_(group_ids))
        .options(selectinload(QuestionGroup.questions))
    )
    groups_with_questions = {g.id: g for g in result.scalars().all()}

    return {
        "project_id": str(project_id),
        "brand_name": effective_brand_name,
        "replace_existing": replace_existing,
        "archived_groups": archived_groups,
        "source": source,
        "fallback_reason": fallback_reason,
        "generation_strategy": _build_question_generation_strategy(project, effective_brand_name, facts),
        "generated_groups": len(created_groups),
        "generated_questions": len(created_questions),
        "groups": [
            {
                "id": str(g.id),
                "layer": g.layer,
                "layer_label": LAYER_LABELS.get(g.layer, g.layer),
                "intent_name": g.intent_name,
                "representative_question": g.representative_question,
                "priority": g.priority,
                "questions": [
                    {
                        "id": str(q.id),
                        "question_text": q.question_text,
                        "question_type": q.question_type,
                        "tags": q.tags,
                        "keyword_breakdown": q.keyword_breakdown,
                        "keyword_layer": q.keyword_layer,
                        "question_formula": q.question_formula,
                        "knowledge_need": q.knowledge_need,
                        "search_asset_type": q.search_asset_type,
                        "business_value": q.business_value,
                        "evidence_support": q.evidence_support,
                        "content_actionability": q.content_actionability,
                        "recommended_platforms": q.recommended_platforms,
                        "priority": q.priority,
                        "sample_policy": q.sample_policy,
                    }
                    for q in groups_with_questions.get(g.id, g).questions
                ],
            }
            for g in created_groups
        ],
    }
