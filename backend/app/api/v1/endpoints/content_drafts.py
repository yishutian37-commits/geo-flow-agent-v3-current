from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, update

from app.core.auth import require_roles
from app.core.database import get_db
from app.models.brand import Brand
from app.models.project import Project
from app.models.content_draft import ContentDraft
from app.models.content_task import ContentTask
from app.models.corpus_item import CorpusItem
from app.models.brand_fact import BrandFact
from app.models.publish_record import PublishRecord
from app.models.question import Question, QuestionGroup
from app.models.experience_skill import ExperienceSkill
from app.models.writing_memory import ContentFeedback, WritingProfile
from app.models.compliance_check import ComplianceCheck
from app.models.user import User
from app.schemas.content_draft import ContentDraftCreate, ContentDraftUpdate, DraftGenerateRequest
from app.agents.production_agent import ProductionAgent
import json

router = APIRouter()


def _decode_knowledge_asset_ids(value: Optional[str]) -> List[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    ids = []
    for item in parsed:
        text = str(item).strip()
        if text and text not in ids:
            ids.append(text)
    return ids


def _draft_to_dict(draft: ContentDraft) -> dict:
    return {
        "id": str(draft.id),
        "task_id": str(draft.task_id),
        "title": draft.title,
        "body": draft.body,
        "version": draft.version,
        "platform": getattr(draft, "platform", None) or "media",
        "status": draft.status,
        "risk_level": draft.risk_level,
        "fact_refs": draft.fact_refs,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
    }


def _fact_is_unexpired(fact: BrandFact) -> bool:
    if not fact.valid_until:
        return True
    valid_until = fact.valid_until
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=timezone.utc)
    return valid_until >= datetime.now(timezone.utc)


def _next_version(version: Optional[str]) -> str:
    if not version:
        return "1.1"
    try:
        major, minor = str(version).split(".", 1)
        return f"{int(major)}.{int(minor) + 1}"
    except Exception:
        return f"{version}.1"


def _high_risk_platform_issues(issues: List[dict]) -> List[dict]:
    return [
        item for item in (issues or [])
        if item.get("severity") == "high" and str(item.get("type", "")).startswith("platform_")
    ]


def _format_fact_refs(fact_refs: list[dict], raw_refs: Optional[str] = None) -> str:
    lines = []
    for index, ref in enumerate(fact_refs, start=1):
        fact_id = str(ref.get("fact_id") or "")
        short_id = fact_id.split("-")[0] if fact_id else "-"
        fact_type = ref.get("fact_type") or "事实"
        wording = ref.get("wording") or ""
        lines.append(f"{index}. [{fact_type}] {wording}（事实ID：{short_id}）")
    if raw_refs:
        if lines:
            lines.append("")
        lines.append("模型原始引用：")
        lines.append(raw_refs)
    return "\n".join(lines)


@router.get("")
async def list_content_drafts(
    task_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db)
):
    """获取稿件草稿列表"""
    query = select(ContentDraft)
    filters = []
    if task_id:
        filters.append(ContentDraft.task_id == task_id)
    if status:
        filters.append(ContentDraft.status == status)
    if filters:
        query = query.where(and_(*filters))
    query = query.offset(skip).limit(limit).order_by(ContentDraft.created_at.desc())
    result = await db.execute(query)
    drafts = result.scalars().all()
    return [_draft_to_dict(d) for d in drafts]


@router.post("")
async def create_content_draft(
    data: ContentDraftCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("editor", "project_owner")),
):
    """创建稿件草稿"""
    task_result = await db.execute(select(ContentTask.id).where(ContentTask.id == data.task_id))
    if task_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail="稿件草稿必须绑定已存在的内容任务")

    draft = ContentDraft(
        task_id=data.task_id,
        title=data.title,
        body=data.body,
        version=data.version,
        platform=data.platform,
        status=data.status,
        risk_level=data.risk_level,
        fact_refs=data.fact_refs,
    )
    db.add(draft)
    await db.commit()
    await db.refresh(draft)
    return _draft_to_dict(draft)


@router.get("/{draft_id}")
async def get_content_draft(
    draft_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """获取草稿详情"""
    result = await db.execute(select(ContentDraft).where(ContentDraft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Content draft not found")
    return _draft_to_dict(draft)


@router.put("/{draft_id}")
async def update_content_draft(
    draft_id: UUID,
    data: ContentDraftUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("editor", "project_owner")),
):
    """更新草稿"""
    result = await db.execute(select(ContentDraft).where(ContentDraft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Content draft not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(draft, field, value)

    await db.commit()
    await db.refresh(draft)
    return _draft_to_dict(draft)


@router.delete("/{draft_id}")
async def delete_content_draft(
    draft_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("editor", "project_owner")),
):
    """删除草稿"""
    result = await db.execute(select(ContentDraft).where(ContentDraft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Content draft not found")

    await db.execute(
        update(PublishRecord)
        .where(PublishRecord.draft_id == draft_id)
        .values(draft_id=None)
        .execution_options(synchronize_session=False)
    )
    await db.execute(
        update(ContentFeedback)
        .where(ContentFeedback.draft_id == draft_id)
        .values(draft_id=None)
        .execution_options(synchronize_session=False)
    )

    await db.delete(draft)
    await db.commit()
    return {"message": "Deleted"}


@router.post("/{task_id}/generate")
async def generate_draft(
    task_id: UUID,
    req: DraftGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("editor", "project_owner")),
):
    """
    调用 ProductionAgent + LLM 生成草稿
    需要传入 content_type 和 platform
    """
    # 获取任务
    task_result = await db.execute(select(ContentTask).where(ContentTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Content task not found")

    project_result = await db.execute(select(Project).where(Project.id == task.project_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=400,
            detail="内容任务没有绑定有效项目，请先删除该任务并重新选择真实项目创建内容任务",
        )

    source_draft = None
    source_draft_context = None
    if req.source_draft_id:
        source_result = await db.execute(
            select(ContentDraft).where(
                ContentDraft.id == req.source_draft_id,
                ContentDraft.task_id == task_id,
            )
        )
        source_draft = source_result.scalar_one_or_none()
        if not source_draft:
            raise HTTPException(status_code=400, detail="上一版草稿不存在，无法按反馈重新生成")
        source_body = (source_draft.body or "")[:5000]
        source_draft_context = f"标题：{source_draft.title or ''}\n正文：\n{source_body}"

    # 获取当前项目/品牌下的事实，避免跨项目串用事实库。
    fact_filters = [Brand.project_id == task.project_id]
    if req.brand_id:
        fact_filters.append(BrandFact.brand_id == req.brand_id)

    facts_result = await db.execute(
        select(BrandFact)
        .join(Brand, BrandFact.brand_id == Brand.id)
        .where(and_(*fact_filters))
    )
    project_facts = list(facts_result.scalars().all())
    publishable_facts = [
        fact for fact in project_facts
        if fact.status == "confirmed" and fact.fact_scope == "public"
        and _fact_is_unexpired(fact)
    ]

    brand = None
    if req.brand_id:
        brand_result = await db.execute(select(Brand).where(Brand.id == req.brand_id, Brand.project_id == task.project_id))
        brand = brand_result.scalar_one_or_none()
    if not brand:
        brand_result = await db.execute(select(Brand).where(Brand.project_id == task.project_id).order_by(Brand.created_at.asc()))
        brand = brand_result.scalars().first()

    profile_result = await db.execute(select(WritingProfile).where(WritingProfile.project_id == task.project_id))
    writing_profile = profile_result.scalar_one_or_none()

    feedback_result = await db.execute(
        select(ContentFeedback)
        .where(
            ContentFeedback.project_id == task.project_id,
            or_(
                ContentFeedback.is_folded == False,  # noqa: E712
                ContentFeedback.rule_text.isnot(None),
                ContentFeedback.diff_summary.isnot(None),
            ),
        )
        .order_by(ContentFeedback.is_folded.asc(), ContentFeedback.created_at.desc())
        .limit(30)
    )
    memory_rules = list(feedback_result.scalars().all())

    skill_scenes = ["article_writing", "rewrite"]
    skill_scope_filters = [
        and_(ExperienceSkill.scope == "project", ExperienceSkill.project_id == task.project_id),
        and_(ExperienceSkill.scope == "industry", ExperienceSkill.industry == project.industry),
        ExperienceSkill.scope == "global",
    ]
    skills_result = await db.execute(
        select(ExperienceSkill)
        .where(
            ExperienceSkill.status == "active",
            ExperienceSkill.trigger_scene.in_(skill_scenes),
            or_(*skill_scope_filters),
        )
        .order_by(ExperienceSkill.scope.asc(), ExperienceSkill.updated_at.desc())
        .limit(30)
    )
    experience_skills = list(skills_result.scalars().all())

    knowledge_assets = []
    knowledge_asset_ids = _decode_knowledge_asset_ids(task.knowledge_asset_ids)
    if knowledge_asset_ids:
        assets_result = await db.execute(
            select(CorpusItem).where(
                CorpusItem.id.in_(knowledge_asset_ids),
                CorpusItem.project_id == task.project_id,
            )
        )
        assets_by_id = {str(item.id): item for item in assets_result.scalars().all()}
        knowledge_assets = [
            assets_by_id[item_id]
            for item_id in knowledge_asset_ids
            if item_id in assets_by_id
        ]

    question_context = {}
    linked_question = None
    if task.question_id:
        question_result = await db.execute(select(Question).where(Question.id == task.question_id))
        linked_question = question_result.scalar_one_or_none()
    if task.group_id:
        group_result = await db.execute(select(QuestionGroup).where(QuestionGroup.id == task.group_id))
        group = group_result.scalar_one_or_none()
        if group:
            question_context = {
                "问题层级": group.layer,
                "意图组": group.intent_name,
                "代表性问题": group.representative_question,
                "问题优先级": group.priority,
            }

    # 初始化 ProductionAgent 并调用 LLM
    if linked_question:
        question_context.update({
            "具体承接问题": linked_question.question_text,
            "问题类型": linked_question.question_type,
            "问题标签": linked_question.tags,
            "关键词拆解": linked_question.keyword_breakdown,
            "关键词层": linked_question.keyword_layer,
            "问题公式": linked_question.question_formula,
            "知识需求": linked_question.knowledge_need,
            "推荐搜索资产": linked_question.search_asset_type,
            "商业价值": linked_question.business_value,
            "证据支撑": linked_question.evidence_support,
            "内容建议": linked_question.content_actionability,
            "推荐发布平台": linked_question.recommended_platforms,
            "问题优先级": linked_question.priority,
        })

    agent = ProductionAgent()

    # 组装 Prompt
    try:
        prompt = agent.generate_article_prompt(
            task,
            project_facts,
            req.platform,
            project=project,
            brand=brand,
            writing_profile=writing_profile,
            active_rules=memory_rules,
            question_context=question_context,
            knowledge_assets=knowledge_assets,
            experience_skills=experience_skills,
            feedback_context=req.feedback_context,
            source_draft_context=source_draft_context,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成提示词失败: {str(e)}") from e

    try:
        # 真正调用 LLM
        llm_response = await agent._call_llm(
            system_prompt="你是资深AI搜索营销文案专家，精通AIDA转化模型、GEO采信证据和多平台内容适配。只使用已确认事实，正文不要残留JSON。",
            user_prompt=prompt,
            agent_name="production_agent",
            project_id=task.project_id,
            temperature=0.55,
        )

        # 结构化解析 LLM 输出
        parsed = ProductionAgent.parse_llm_output(llm_response)
        title = parsed["title"] or "未命名草稿"
        body = parsed["body"] or llm_response
        platform_rewrite = {
            "attempted": False,
            "attempts": 0,
            "max_attempts": 2,
            "resolved": None,
            "initial_high_risk_count": 0,
            "remaining_high_risk_count": 0,
        }

        # 合规检查
        compliance_issues = agent.check_compliance(f"{title}\n{body}", project_facts)
        compliance_issues.extend(agent.check_platform_compliance(f"{title}\n{body}", req.platform))
        if not publishable_facts:
            compliance_issues.insert(0, {
                "type": "missing_publishable_facts",
                "name": "资料完整性提示",
                "severity": "medium",
                "message": "当前项目没有可公开使用的已确认品牌事实，本次生成的是资料不足版草稿，发布前需补充并确认资质、产品、地址、案例等基础事实。",
            })

        high_risk_platform_issues = _high_risk_platform_issues(compliance_issues)
        platform_rewrite["initial_high_risk_count"] = len(high_risk_platform_issues)
        while high_risk_platform_issues and platform_rewrite["attempts"] < platform_rewrite["max_attempts"]:
            platform_rewrite["attempted"] = True
            platform_rewrite["attempts"] += 1
            try:
                rewrite_prompt = agent.generate_platform_rewrite_prompt(
                    title=title,
                    body=body,
                    platform=req.platform,
                    platform_issues=high_risk_platform_issues,
                )
                rewritten_response = await agent._call_llm(
                    system_prompt="你是严格的平台合规编辑。只修复平台违规和机器格式残留，不新增未经确认事实。",
                    user_prompt=rewrite_prompt,
                    agent_name="production_agent_platform_rewrite",
                    project_id=task.project_id,
                    temperature=0.25,
                )
                rewritten_parsed = ProductionAgent.parse_llm_output(rewritten_response)
                title = rewritten_parsed["title"] or title
                body = rewritten_parsed["body"] or body
                parsed = rewritten_parsed
                llm_response = rewritten_response
                compliance_issues = agent.check_compliance(f"{title}\n{body}", project_facts)
                compliance_issues.extend(agent.check_platform_compliance(f"{title}\n{body}", req.platform))
                if not publishable_facts:
                    compliance_issues.insert(0, {
                        "type": "missing_publishable_facts",
                        "name": "资料完整性提示",
                        "severity": "medium",
                        "message": "当前项目没有可公开使用的已确认品牌事实，本次生成的是资料不足版草稿，发布前需补充并确认资质、产品、地址、案例等基础事实。",
                    })
                high_risk_platform_issues = _high_risk_platform_issues(compliance_issues)
                platform_rewrite["remaining_high_risk_count"] = len(high_risk_platform_issues)
                platform_rewrite["resolved"] = not high_risk_platform_issues
            except Exception as rewrite_error:
                platform_rewrite["resolved"] = False
                platform_rewrite["error"] = str(rewrite_error)
                compliance_issues.append({
                    "type": "platform_auto_rewrite_failed",
                    "name": "平台自动修复失败",
                    "severity": "medium",
                    "message": f"检测到平台高风险问题，但自动二次重写失败：{rewrite_error}",
                })
                break
        if platform_rewrite["attempted"] and high_risk_platform_issues:
            platform_rewrite["remaining_high_risk_count"] = len(high_risk_platform_issues)
            platform_rewrite["resolved"] = False

        # 事实引用检查
        fact_refs = agent.generate_fact_references(body, publishable_facts)

        # 风险等级判定
        risk_level = "high" if any(i.get("severity") == "high" for i in compliance_issues) else (
            "medium" if compliance_issues else "low"
        )

        # 构建面向用户可读的 fact_refs 字符串（包含解析出的原始引用）
        fact_refs_str = _format_fact_refs(fact_refs, parsed["fact_refs_raw"])

        # 创建草稿记录
        draft = ContentDraft(
            task_id=task_id,
            title=title,
            body=body,
            version=_next_version(source_draft.version) if source_draft else "1.0",
            platform=req.platform,
            status="draft",
            risk_level=risk_level,
            fact_refs=fact_refs_str,
        )
        db.add(draft)
        await db.commit()
        await db.refresh(draft)

        return {
            "draft": _draft_to_dict(draft),
            "compliance_issues": compliance_issues,
            "fact_references": fact_refs,
            "parsed": {
                "title": parsed["title"],
                "has_body": bool(parsed["body"]),
                "has_fact_refs": bool(parsed["fact_refs_raw"]),
                "has_compliance": bool(parsed["compliance_raw"]),
            },
            "memory_used": {
                "profile_version": writing_profile.version if writing_profile else None,
                "active_rules": len([item for item in memory_rules if not item.is_folded]),
                "historical_rules": len([item for item in memory_rules if item.is_folded]),
                "active_feedbacks": len([item for item in memory_rules if not item.is_folded]),
                "writing_profile_used": bool(writing_profile),
                "experience_skills": len(experience_skills),
            },
            "platform_rewrite": platform_rewrite,
            "llm_raw_output": llm_response,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM generation failed: {str(e)}")


@router.post("/{draft_id}/validate-publish-ready")
async def validate_publish_ready(
    draft_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("editor", "compliance_reviewer", "project_owner")),
):
    """验证草稿是否可进入 Publish Ready 状态"""
    result = await db.execute(select(ContentDraft).where(ContentDraft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Content draft not found")

    task_result = await db.execute(select(ContentTask).where(ContentTask.id == draft.task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Content task not found")

    # 获取当前项目下所有事实，用于识别未确认/受限/过期事实是否被引用。
    facts_result = await db.execute(
        select(BrandFact)
        .join(Brand, BrandFact.brand_id == Brand.id)
        .where(Brand.project_id == task.project_id)
    )
    brand_facts = list(facts_result.scalars().all())

    agent = ProductionAgent()
    validation = agent.validate_publish_ready(draft, brand_facts)
    issues = validation.get("issues", [])
    check = ComplianceCheck(
        draft_id=draft.id,
        check_type="publish_ready",
        result="passed" if validation.get("can_publish") else "failed",
        issues=json.dumps(issues, ensure_ascii=False),
        checked_at=datetime.now(timezone.utc),
    )
    db.add(check)
    if validation.get("can_publish"):
        draft.status = "publish_ready"
    elif draft.status == "publish_ready":
        draft.status = "review"
    await db.commit()
    return validation
