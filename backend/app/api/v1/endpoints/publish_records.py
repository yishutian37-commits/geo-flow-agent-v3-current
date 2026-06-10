from datetime import datetime, timezone
import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles
from app.core.database import get_db
from app.models.channel_account import ChannelAccount
from app.models.brand import Brand
from app.models.brand_fact import BrandFact
from app.models.compliance_check import ComplianceCheck
from app.models.content_draft import ContentDraft
from app.models.content_task import ContentTask
from app.models.experience_skill import ExperienceSkillSuggestion
from app.models.project import Project
from app.models.publish_record import PublishRecord
from app.models.user import User
from app.schemas.publish_record import PublishRecordCreate, PublishRecordUpdate, PublishWebBridgeAssistRequest
from app.services.webbridge_service import DEFAULT_PUBLISHER_URLS, WebBridgeError, WebBridgeService
from app.agents.production_agent import ProductionAgent

router = APIRouter()


@router.get("")
async def list_publish_records(
    project_id: Optional[UUID] = Query(None),
    task_id: Optional[UUID] = Query(None),
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """获取发布记录列表"""
    query = select(PublishRecord)
    filters = []
    if project_id:
        query = query.join(ContentTask, PublishRecord.task_id == ContentTask.id)
        filters.append(ContentTask.project_id == project_id)
    if task_id:
        filters.append(PublishRecord.task_id == task_id)
    if platform:
        filters.append(PublishRecord.platform == platform)
    if status:
        filters.append(PublishRecord.status == status)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(PublishRecord.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    records = result.scalars().all()
    return await _records_to_dicts(db, records)


@router.post("")
async def create_publish_record(
    data: PublishRecordCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("publisher", "project_owner")),
):
    """创建发布记录。记录人工发布结果，作为后续检测和报告依据。"""
    task = await _get_task_or_404(db, data.task_id)
    account = await _get_account_or_400(db, data.channel_account_id)
    draft = await _get_draft_for_task_or_400(db, data.draft_id, data.task_id)

    if data.status == "published":
        if not draft:
            raise HTTPException(status_code=400, detail="记录已发布内容时必须绑定具体草稿版本")
        validation = await _validate_and_record_publish_check(db, draft, task)
        if not validation.get("can_publish") and not data.force_save:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "草稿未通过发布检查，是否仍然保存发布记录？",
                    "issues": validation.get("issues", []),
                    "can_force_save": True,
                },
            )

    published_at = data.published_at
    if data.status == "published" and not published_at:
        published_at = datetime.now(timezone.utc)

    record = PublishRecord(
        task_id=data.task_id,
        draft_id=data.draft_id,
        draft_version=draft.version if draft else None,
        channel_account_id=data.channel_account_id,
        platform=data.platform,
        url=data.url,
        title=data.title,
        content_type=data.content_type or task.content_type,
        published_at=published_at,
        publisher_id=user.id,
        status=data.status,
        is_indexed=data.is_indexed,
        first_indexed_at=data.first_indexed_at,
        related_content_task_id=data.task_id,
        related_question_group_id=data.related_question_group_id or task.group_id,
    )
    db.add(record)

    if data.status == "published":
        task.status = "published"
        if draft:
            draft.status = "published"
        if account:
            account.last_publish_at = published_at or datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(record)
    return (await _records_to_dicts(db, [record]))[0]


@router.post("/webbridge-assist")
async def assist_publish_with_webbridge(
    data: PublishWebBridgeAssistRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("publisher", "project_owner")),
):
    """打开发布平台编辑页并预填草稿内容；不自动点击最终发布。"""
    draft = await _get_draft_or_404(db, data.draft_id)
    task = await _get_task_or_404(db, draft.task_id)
    account = await _get_account_or_400(db, data.channel_account_id)
    platform = data.platform or (account.platform if account else None) or "other"
    page_url = data.publisher_url or (account.publisher_url if account else None) or DEFAULT_PUBLISHER_URLS.get(platform)

    facts_result = await db.execute(
        select(BrandFact)
        .join(Brand, BrandFact.brand_id == Brand.id)
        .where(Brand.project_id == task.project_id)
    )
    brand_facts = list(facts_result.scalars().all())
    validation = ProductionAgent().validate_publish_ready(draft, brand_facts)
    content_package = {
        "task_id": str(task.id),
        "draft_id": str(draft.id),
        "draft_version": draft.version,
        "platform": platform,
        "channel_account_id": str(account.id) if account else None,
        "channel_account_name": account.account_name if account else None,
        "title": draft.title or "",
        "body": draft.body or "",
        "content_type": task.content_type,
    }

    response = {
        "can_publish": bool(validation.get("can_publish")),
        "issues": validation.get("issues", []),
        "content_package": content_package,
        "publisher_url": page_url,
        "webbridge": {
            "attempted": False,
            "ok": False,
            "message": None,
        },
        "next_step": "请人工核对页面内容，确认无误后在平台内点击发布，并回到系统保存发布记录。",
    }

    if not validation.get("can_publish"):
        response["webbridge"]["message"] = "草稿未通过发布检查，已停止打开发布页。"
        return response
    if not page_url:
        response["webbridge"]["message"] = "发布渠道未配置编辑页 URL，已返回可复制的标题和正文。"
        return response

    try:
        bridge_result = await WebBridgeService().open_publish_page(
            page_url=page_url,
            title=draft.title or "",
            body=draft.body or "",
            session=f"geo-publish-{draft.id}",
            title_selector=data.title_selector or (account.title_selector if account else None),
            body_selector=data.body_selector or (account.body_selector if account else None),
        )
        response["webbridge"] = {
            "attempted": True,
            "ok": bool(bridge_result.get("ok")),
            "title_filled": bool(bridge_result.get("title_filled")),
            "body_filled": bool(bridge_result.get("body_filled")),
            "page_url": bridge_result.get("page_url"),
            "provider": bridge_result.get("bridge_provider"),
            "warning": bridge_result.get("warning") or bridge_result.get("status_warning"),
            "message": "发布页已打开，请人工检查后发布。",
        }
    except WebBridgeError as exc:
        response["webbridge"] = {
            "attempted": True,
            "ok": False,
            "message": f"WebBridge 打开或预填失败：{exc}",
        }
    return response


@router.get("/{record_id}")
async def get_publish_record(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取发布记录详情"""
    result = await db.execute(select(PublishRecord).where(PublishRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Publish record not found")
    return (await _records_to_dicts(db, [record]))[0]


@router.put("/{record_id}")
async def update_publish_record(
    record_id: UUID,
    data: PublishRecordUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("publisher", "project_owner")),
):
    """更新发布记录"""
    result = await db.execute(select(PublishRecord).where(PublishRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Publish record not found")

    update_data = data.model_dump(exclude_unset=True)
    if "channel_account_id" in update_data:
        await _get_account_or_400(db, update_data["channel_account_id"])
    if "draft_id" in update_data:
        draft = await _get_draft_for_task_or_400(db, update_data["draft_id"], record.task_id)
        record.draft_version = draft.version if draft else None
    for field, value in update_data.items():
        setattr(record, field, value)

    if record.status == "published" and not record.published_at:
        record.published_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(record)
    return (await _records_to_dicts(db, [record]))[0]


@router.delete("/{record_id}")
async def delete_publish_record(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("publisher", "project_owner")),
):
    """删除发布记录"""
    result = await db.execute(select(PublishRecord).where(PublishRecord.id == record_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Publish record not found")
    await db.delete(record)
    await db.commit()
    return {"message": "Deleted"}


async def _get_task_or_404(db: AsyncSession, task_id: UUID) -> ContentTask:
    result = await db.execute(select(ContentTask).where(ContentTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Content task not found")
    return task


async def _get_draft_or_404(db: AsyncSession, draft_id: UUID) -> ContentDraft:
    result = await db.execute(select(ContentDraft).where(ContentDraft.id == draft_id))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Content draft not found")
    return draft


async def _get_account_or_400(db: AsyncSession, account_id: Optional[UUID]) -> Optional[ChannelAccount]:
    if not account_id:
        return None
    result = await db.execute(select(ChannelAccount).where(ChannelAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=400, detail="发布渠道账号不存在")
    return account


async def _get_draft_for_task_or_400(
    db: AsyncSession,
    draft_id: Optional[UUID],
    task_id: UUID,
) -> Optional[ContentDraft]:
    if not draft_id:
        return None
    result = await db.execute(
        select(ContentDraft).where(
            ContentDraft.id == draft_id,
            ContentDraft.task_id == task_id,
        )
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=400, detail="绑定的草稿不存在，或不属于当前内容任务")
    return draft


async def _validate_and_record_publish_check(
    db: AsyncSession,
    draft: ContentDraft,
    task: ContentTask,
) -> dict:
    facts_result = await db.execute(
        select(BrandFact)
        .join(Brand, BrandFact.brand_id == Brand.id)
        .where(Brand.project_id == task.project_id)
    )
    brand_facts = list(facts_result.scalars().all())
    validation = ProductionAgent().validate_publish_ready(draft, brand_facts)
    check = ComplianceCheck(
        draft_id=draft.id,
        check_type="publish_ready",
        result="passed" if validation.get("can_publish") else "failed",
        issues=json.dumps(validation.get("issues", []), ensure_ascii=False),
        checked_at=datetime.now(timezone.utc),
    )
    db.add(check)
    await db.flush()
    if validation.get("issues"):
        await _create_publish_check_skill_suggestion(db, draft, task, check, validation)
    return validation


async def _create_publish_check_skill_suggestion(
    db: AsyncSession,
    draft: ContentDraft,
    task: ContentTask,
    check: ComplianceCheck,
    validation: dict,
) -> None:
    existing_result = await db.execute(
        select(ExperienceSkillSuggestion).where(
            ExperienceSkillSuggestion.project_id == task.project_id,
            ExperienceSkillSuggestion.source_type == "publish_check",
            ExperienceSkillSuggestion.source_refs_json.contains(str(draft.id)),
        )
    )
    if existing_result.scalar_one_or_none():
        return

    project_result = await db.execute(select(Project).where(Project.id == task.project_id))
    project = project_result.scalar_one_or_none()
    issues = validation.get("issues") or []
    issue_messages = [
        str(item.get("message") or item.get("type") or item)
        for item in issues
        if item
    ]
    issue_summary = "；".join(issue_messages[:5]) or "存在发布检查风险"
    high_count = int(validation.get("high_severity_issues") or 0)
    warning_count = int(validation.get("warning_issues") or 0)
    source_refs = {
        "draft_id": str(draft.id),
        "task_id": str(task.id),
        "compliance_check_id": str(check.id),
        "platform": draft.platform,
    }
    db.add(
        ExperienceSkillSuggestion(
            project_id=task.project_id,
            suggested_scope="project",
            industry=(project.industry if project else None),
            trigger_scene="publish_check",
            skill_type="rule",
            name=f"发布检查经验：{draft.platform or '未知平台'}",
            suggestion_text=(
                f"平台「{draft.platform or '未知平台'}」发布前需要重点规避：{issue_summary}。"
                "后续同类稿件生成和检查时，应提前弱化高风险表达、补充人工审核提示或调整发布版本。"
            )[:4000],
            reason=f"发布检查发现 {high_count} 个高风险项、{warning_count} 个提醒项。",
            evidence=json.dumps(issues[:10], ensure_ascii=False),
            risk_note="来自发布检查结果，仅作为平台适配经验建议；确认前不要升级为行业或全局规则。",
            source_type="publish_check",
            source_refs_json=json.dumps(source_refs, ensure_ascii=False),
            confidence=0.6,
            status="pending",
        )
    )


async def _records_to_dicts(db: AsyncSession, records: list[PublishRecord]) -> list[dict]:
    task_ids = sorted({str(record.task_id) for record in records if record.task_id})
    channel_ids = sorted({str(record.channel_account_id) for record in records if record.channel_account_id})

    tasks_by_id = {}
    projects_by_id = {}
    if task_ids:
        task_result = await db.execute(select(ContentTask).where(ContentTask.id.in_(task_ids)))
        tasks = list(task_result.scalars().all())
        tasks_by_id = {str(task.id): task for task in tasks}
        project_ids = sorted({str(task.project_id) for task in tasks if task.project_id})
        if project_ids:
            project_result = await db.execute(select(Project).where(Project.id.in_(project_ids)))
            projects_by_id = {str(project.id): project for project in project_result.scalars().all()}

    channels_by_id = {}
    if channel_ids:
        channel_result = await db.execute(select(ChannelAccount).where(ChannelAccount.id.in_(channel_ids)))
        channels_by_id = {str(channel.id): channel for channel in channel_result.scalars().all()}

    return [
        _record_to_dict(
            record,
            tasks_by_id.get(str(record.task_id)),
            channels_by_id.get(str(record.channel_account_id)) if record.channel_account_id else None,
            projects_by_id,
        )
        for record in records
    ]


def _record_to_dict(
    record: PublishRecord,
    task: Optional[ContentTask],
    channel: Optional[ChannelAccount],
    projects_by_id: dict,
) -> dict:
    project = projects_by_id.get(str(task.project_id)) if task else None
    return {
        "id": str(record.id),
        "task_id": str(record.task_id),
        "draft_id": str(record.draft_id) if record.draft_id else None,
        "draft_version": record.draft_version,
        "project_id": str(task.project_id) if task else None,
        "project_name": project.name if project else None,
        "channel_account_id": str(record.channel_account_id) if record.channel_account_id else None,
        "channel_account_name": channel.account_name if channel else None,
        "platform": record.platform,
        "url": record.url,
        "title": record.title,
        "content_type": record.content_type,
        "published_at": record.published_at.isoformat() if record.published_at else None,
        "publisher_id": str(record.publisher_id) if record.publisher_id else None,
        "status": record.status,
        "is_indexed": record.is_indexed,
        "first_indexed_at": record.first_indexed_at.isoformat() if record.first_indexed_at else None,
        "related_content_task_id": str(record.related_content_task_id) if record.related_content_task_id else None,
        "related_question_group_id": str(record.related_question_group_id) if record.related_question_group_id else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }
