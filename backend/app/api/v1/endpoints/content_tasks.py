import json
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete, update
from sqlalchemy.orm import selectinload

from app.core.auth import require_roles
from app.core.database import get_db
from app.models.approval import Approval
from app.models.content_draft import ContentDraft
from app.models.content_task import ContentTask
from app.models.corpus_item import CorpusItem
from app.models.publish_record import PublishRecord
from app.models.project import Project
from app.models.question import Question, QuestionGroup
from app.models.writing_memory import ContentFeedback
from app.models.user import User
from app.schemas.content_task import ContentTaskCreate, ContentTaskUpdate, ContentTaskOut, ContentTaskTransition
from app.services.state_machine import StateMachine, StateMachineError, TaskStatus

router = APIRouter()


def _encode_knowledge_asset_ids(values: Optional[List[UUID]]) -> Optional[str]:
    ids = []
    for value in values or []:
        text = str(value)
        if text not in ids:
            ids.append(text)
    return json.dumps(ids, ensure_ascii=False) if ids else None


def _decode_knowledge_asset_ids(value: Optional[str]) -> List[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = []
    if not isinstance(parsed, list):
        return []
    ids = []
    for item in parsed:
        text = str(item).strip()
        if text and text not in ids:
            ids.append(text)
    return ids


def _knowledge_asset_to_dict(item: CorpusItem) -> dict:
    return {
        "id": str(item.id),
        "title": item.title,
        "content_preview": (item.content or "")[:240],
        "knowledge_layer": item.knowledge_layer,
        "business_use": item.business_use,
        "evidence_level": item.evidence_level,
        "reusable_scope": item.reusable_scope,
        "source_type": item.source_type,
        "source_url": item.source_url,
        "tags": item.tags,
    }


KNOWLEDGE_RECOMMEND_TERMS = [
    "资质",
    "证书",
    "编号",
    "合规",
    "认证",
    "案例",
    "客户",
    "口碑",
    "评价",
    "地址",
    "电话",
    "联系",
    "价格",
    "费用",
    "流程",
    "售后",
    "产品",
    "服务",
    "参数",
    "对比",
    "竞品",
    "优势",
    "场景",
    "人群",
    "痛点",
]


def _recommendation_terms_for_question(
    question: Optional[Question],
    group: Optional[QuestionGroup],
    content_type: Optional[str],
    layer: Optional[str],
) -> List[str]:
    parts = [
        question.question_text if question else "",
        question.tags if question else "",
        question.keyword_layer if question else "",
        question.knowledge_need if question else "",
        question.search_asset_type if question else "",
        question.evidence_support if question else "",
        question.content_actionability if question else "",
        group.intent_name if group else "",
        group.representative_question if group else "",
        content_type or "",
        layer or "",
    ]
    text = " ".join(str(part or "") for part in parts)
    terms = [term for term in KNOWLEDGE_RECOMMEND_TERMS if term and term in text]
    if question and question.keyword_layer == "proof":
        terms.extend(["资质", "证书", "编号", "案例"])
    if question and question.keyword_layer == "conversion":
        terms.extend(["价格", "地址", "联系", "流程"])
    if question and question.keyword_layer == "comparison":
        terms.extend(["对比", "竞品", "优势", "案例"])
    if question and question.keyword_layer == "scenario":
        terms.extend(["场景", "人群", "痛点", "案例"])
    seen = []
    for term in terms:
        if term not in seen:
            seen.append(term)
    return seen


def _score_knowledge_asset(item: CorpusItem, terms: List[str], question: Optional[Question]) -> int:
    haystack = " ".join([
        item.title or "",
        item.content or "",
        item.tags or "",
        item.knowledge_layer or "",
        item.business_use or "",
        item.source_type or "",
    ])
    score = 0
    for term in terms:
        if term and term in haystack:
            score += 5
    if item.business_use in {"content_writing", "general"}:
        score += 3
    if item.evidence_level in {"official", "verified"}:
        score += 2
    if question:
        if question.keyword_layer == "proof" and item.knowledge_layer in {"basic_info", "content_material"}:
            score += 3
        if question.keyword_layer == "comparison" and item.knowledge_layer in {"competitor_feedback", "judgment", "story"}:
            score += 3
        if question.keyword_layer == "scenario" and item.knowledge_layer in {"story", "judgment", "content_material"}:
            score += 3
        if question.keyword_layer == "conversion" and item.knowledge_layer in {"basic_info", "content_material"}:
            score += 3
    if item.knowledge_layer == "review_data":
        score -= 6
    if item.business_use == "monitoring_review":
        score -= 6
    if item.evidence_level == "internal":
        score -= 4
    if "无关" in haystack:
        score -= 8
    return score


def _parse_task_status(value: str) -> TaskStatus:
    try:
        return TaskStatus(value)
    except ValueError as exc:
        allowed = [status.value for status in TaskStatus]
        raise HTTPException(status_code=400, detail=f"未知任务状态: {value}. 可用状态: {allowed}") from exc


async def _approval_map(db: AsyncSession, task_id: UUID) -> dict[str, str]:
    result = await db.execute(
        select(Approval).where(
            Approval.object_type == "content_task",
            Approval.object_id == task_id,
        )
    )
    return {item.step: item.decision for item in result.scalars().all()}


async def _ensure_approval(db: AsyncSession, task_id: UUID, step: str, comment: str) -> None:
    result = await db.execute(
        select(Approval).where(
            Approval.object_type == "content_task",
            Approval.object_id == task_id,
            Approval.step == step,
        )
    )
    approval = result.scalar_one_or_none()
    if approval:
        return
    db.add(Approval(
        object_type="content_task",
        object_id=task_id,
        step=step,
        decision="pending",
        comment=comment,
    ))


async def _has_publish_ready_draft(db: AsyncSession, task_id: UUID) -> bool:
    result = await db.execute(
        select(ContentDraft.id).where(
            ContentDraft.task_id == task_id,
            ContentDraft.status == "publish_ready",
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _validate_transition_guards(db: AsyncSession, task: ContentTask, target: TaskStatus) -> None:
    approvals = await _approval_map(db, task.id)
    if target == TaskStatus.APPROVED:
        missing = [
            label for step, label in [
                ("compliance_review", "合规审核"),
                ("project_owner_review", "项目负责人终审"),
            ]
            if approvals.get(step) != "approved"
        ]
        if missing:
            raise HTTPException(status_code=400, detail=f"不能进入已通过：{', '.join(missing)}尚未通过")

    if target == TaskStatus.PUBLISH_READY:
        if approvals.get("client_review") != "approved":
            raise HTTPException(status_code=400, detail="不能进入待发布：客户复核尚未通过")
        if not await _has_publish_ready_draft(db, task.id):
            raise HTTPException(status_code=400, detail="不能进入待发布：当前任务没有通过发布校验的草稿")


async def _create_transition_approvals(db: AsyncSession, task_id: UUID, target: TaskStatus) -> None:
    if target == TaskStatus.REVIEW:
        await _ensure_approval(db, task_id, "compliance_review", "进入待审核时自动创建的合规审核记录")
        await _ensure_approval(db, task_id, "project_owner_review", "进入待审核时自动创建的项目负责人终审记录")
    if target == TaskStatus.CLIENT_REVIEW:
        await _ensure_approval(db, task_id, "client_review", "进入客户复核时自动创建的客户确认记录")


def _task_to_dict(
    task: ContentTask,
    project: Optional[Project] = None,
    group: Optional[QuestionGroup] = None,
    question: Optional[Question] = None,
    knowledge_assets: Optional[List[CorpusItem]] = None,
) -> dict:
    linked_question_text = question.question_text if question else None
    knowledge_asset_ids = _decode_knowledge_asset_ids(task.knowledge_asset_ids)
    return {
        "id": str(task.id),
        "project_id": str(task.project_id),
        "project_name": project.name if project else None,
        "project_industry": project.industry if project else None,
        "project_region": project.region if project else None,
        "group_id": str(task.group_id) if task.group_id else None,
        "question_id": str(task.question_id) if task.question_id else None,
        "group_layer": group.layer if group else None,
        "group_intent_name": group.intent_name if group else None,
        "group_representative_question": group.representative_question if group else None,
        "representative_question": linked_question_text or (group.representative_question if group else None),
        "question_text": linked_question_text,
        "question_type": question.question_type if question else None,
        "question_priority": question.priority if question else None,
        "knowledge_asset_ids": knowledge_asset_ids,
        "knowledge_assets": [
            _knowledge_asset_to_dict(item)
            for item in (knowledge_assets or [])
        ],
        "content_type": task.content_type,
        "layer": task.layer,
        "priority": task.priority,
        "assignee": str(task.assignee) if task.assignee else None,
        "status": task.status,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "estimated_token_cost": float(task.estimated_token_cost) if task.estimated_token_cost else None,
        "actual_token_cost": float(task.actual_token_cost) if task.actual_token_cost else None,
        "estimated_api_cost": float(task.estimated_api_cost) if task.estimated_api_cost else None,
        "actual_api_cost": float(task.actual_api_cost) if task.actual_api_cost else None,
        "estimated_labor_minutes": float(task.estimated_labor_minutes) if task.estimated_labor_minutes else None,
        "actual_labor_minutes": float(task.actual_labor_minutes) if task.actual_labor_minutes else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


async def _get_project_or_400(db: AsyncSession, project_id: UUID) -> Project:
    result = await db.execute(select(Project).where(Project.id == str(project_id)))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=400,
            detail="内容任务必须绑定一个已存在的项目，请先选择真实项目后再创建任务",
        )
    return project


async def _get_group_for_project(
    db: AsyncSession,
    group_id: Optional[UUID],
    project_id: UUID,
) -> Optional[QuestionGroup]:
    if not group_id:
        return None
    result = await db.execute(select(QuestionGroup).where(QuestionGroup.id == str(group_id)))
    group = result.scalar_one_or_none()
    if not group or str(group.project_id) != str(project_id):
        raise HTTPException(
            status_code=400,
            detail="内容任务关联的问题组不存在，或不属于当前项目",
        )
    return group


async def _get_question_for_project(
    db: AsyncSession,
    question_id: Optional[UUID],
    project_id: UUID,
    group_id: Optional[UUID] = None,
) -> Optional[Question]:
    if not question_id:
        return None
    result = await db.execute(
        select(Question)
        .where(Question.id == str(question_id))
        .options(selectinload(Question.group))
    )
    question = result.scalar_one_or_none()
    if not question or not question.group or str(question.group.project_id) != str(project_id):
        raise HTTPException(
            status_code=400,
            detail="内容任务关联的问题不存在，或不属于当前项目",
        )
    if group_id and str(question.group_id) != str(group_id):
        raise HTTPException(
            status_code=400,
            detail="内容任务关联的问题不属于所选问题组",
        )
    return question


async def _get_knowledge_assets_for_project(
    db: AsyncSession,
    knowledge_asset_ids: Optional[List[UUID] | List[str]],
    project_id: UUID,
) -> List[CorpusItem]:
    ids = []
    for value in knowledge_asset_ids or []:
        text = str(value)
        if text and text not in ids:
            ids.append(text)
    if not ids:
        return []
    result = await db.execute(
        select(CorpusItem).where(
            CorpusItem.id.in_(ids),
            CorpusItem.project_id == str(project_id),
        )
    )
    assets_by_id: Dict[str, CorpusItem] = {
        str(item.id): item for item in result.scalars().all()
    }
    missing = [item_id for item_id in ids if item_id not in assets_by_id]
    if missing:
        raise HTTPException(
            status_code=400,
            detail="内容任务关联的知识资产不存在，或不属于当前项目",
        )
    return [assets_by_id[item_id] for item_id in ids]


async def _recommend_knowledge_assets_for_task(
    db: AsyncSession,
    *,
    project_id: UUID,
    question: Optional[Question],
    group: Optional[QuestionGroup],
    content_type: Optional[str],
    layer: Optional[str],
    limit: int = 6,
) -> List[CorpusItem]:
    terms = _recommendation_terms_for_question(question, group, content_type, layer)
    if not terms:
        return []
    result = await db.execute(
        select(CorpusItem)
        .where(CorpusItem.project_id == str(project_id))
        .order_by(CorpusItem.created_at.desc())
        .limit(120)
    )
    scored = []
    for item in result.scalars().all():
        score = _score_knowledge_asset(item, terms, question)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda row: row[0], reverse=True)
    return [item for _, item in scored[:limit]]


@router.get("")
async def list_content_tasks(
    project_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    layer: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db)
):
    """获取内容任务列表"""
    query = select(ContentTask)
    filters = []
    if project_id:
        filters.append(ContentTask.project_id == project_id)
    if status:
        filters.append(ContentTask.status == status)
    if layer:
        filters.append(ContentTask.layer == layer)
    if filters:
        query = query.where(and_(*filters))
    query = query.offset(skip).limit(limit).order_by(ContentTask.created_at.desc())
    result = await db.execute(query)
    tasks = result.scalars().all()
    project_ids = sorted({str(task.project_id) for task in tasks if task.project_id})
    projects_by_id = {}
    if project_ids:
        projects_result = await db.execute(select(Project).where(Project.id.in_(project_ids)))
        projects_by_id = {str(project.id): project for project in projects_result.scalars().all()}
    question_ids = sorted({str(task.question_id) for task in tasks if task.question_id})
    questions_by_id = {}
    question_group_ids = set()
    if question_ids:
        questions_result = await db.execute(
            select(Question)
            .where(Question.id.in_(question_ids))
            .options(selectinload(Question.group))
        )
        questions_by_id = {str(question.id): question for question in questions_result.scalars().all()}
        question_group_ids = {str(question.group_id) for question in questions_by_id.values() if question.group_id}
    group_ids = sorted({str(task.group_id) for task in tasks if task.group_id} | question_group_ids)
    groups_by_id = {}
    if group_ids:
        groups_result = await db.execute(select(QuestionGroup).where(QuestionGroup.id.in_(group_ids)))
        groups_by_id = {str(group.id): group for group in groups_result.scalars().all()}
    knowledge_asset_ids = sorted({
        asset_id
        for task in tasks
        for asset_id in _decode_knowledge_asset_ids(task.knowledge_asset_ids)
    })
    knowledge_assets_by_id = {}
    if knowledge_asset_ids:
        assets_result = await db.execute(select(CorpusItem).where(CorpusItem.id.in_(knowledge_asset_ids)))
        knowledge_assets_by_id = {str(item.id): item for item in assets_result.scalars().all()}
    return [
        _task_to_dict(
            task,
            projects_by_id.get(str(task.project_id)),
            groups_by_id.get(str(task.group_id)) if task.group_id else None,
            questions_by_id.get(str(task.question_id)) if task.question_id else None,
            [
                knowledge_assets_by_id[asset_id]
                for asset_id in _decode_knowledge_asset_ids(task.knowledge_asset_ids)
                if asset_id in knowledge_assets_by_id
            ],
        )
        for task in tasks
    ]


@router.post("")
async def create_content_task(
    data: ContentTaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("strategist", "project_owner")),
):
    """创建内容任务"""
    project = await _get_project_or_400(db, data.project_id)
    question = await _get_question_for_project(db, data.question_id, data.project_id, data.group_id)
    group_id = data.group_id or (question.group_id if question else None)
    group = await _get_group_for_project(db, group_id, data.project_id)
    if data.knowledge_asset_ids:
        knowledge_assets = await _get_knowledge_assets_for_project(db, data.knowledge_asset_ids, data.project_id)
    else:
        knowledge_assets = await _recommend_knowledge_assets_for_task(
            db,
            project_id=data.project_id,
            question=question,
            group=group,
            content_type=data.content_type,
            layer=data.layer,
        )
    knowledge_asset_ids = [item.id for item in knowledge_assets]
    task = ContentTask(
        project_id=data.project_id,
        group_id=group_id,
        question_id=data.question_id,
        knowledge_asset_ids=_encode_knowledge_asset_ids(knowledge_asset_ids),
        content_type=data.content_type,
        layer=data.layer,
        priority=data.priority,
        status=data.status,
        due_date=data.due_date,
        estimated_token_cost=data.estimated_token_cost,
        estimated_api_cost=data.estimated_api_cost,
        estimated_labor_minutes=data.estimated_labor_minutes,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return _task_to_dict(task, project, group, question, knowledge_assets)


@router.get("/{task_id}")
async def get_content_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """获取内容任务详情"""
    result = await db.execute(select(ContentTask).where(ContentTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Content task not found")
    project = await _get_project_or_400(db, task.project_id)
    group = await _get_group_for_project(db, task.group_id, task.project_id)
    question = await _get_question_for_project(db, task.question_id, task.project_id, task.group_id)
    knowledge_assets = await _get_knowledge_assets_for_project(
        db,
        _decode_knowledge_asset_ids(task.knowledge_asset_ids),
        task.project_id,
    )
    return _task_to_dict(task, project, group, question, knowledge_assets)


@router.put("/{task_id}")
async def update_content_task(
    task_id: UUID,
    data: ContentTaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("strategist", "editor", "project_owner")),
):
    """更新内容任务"""
    result = await db.execute(select(ContentTask).where(ContentTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Content task not found")

    update_data = data.model_dump(exclude_unset=True)
    knowledge_assets = None
    if "knowledge_asset_ids" in update_data:
        requested_asset_ids = update_data.pop("knowledge_asset_ids") or []
        knowledge_assets = await _get_knowledge_assets_for_project(db, requested_asset_ids, task.project_id)
        task.knowledge_asset_ids = _encode_knowledge_asset_ids(requested_asset_ids)
    changed_target_status = None
    if "status" in update_data and update_data["status"] and update_data["status"] != task.status:
        target_status = _parse_task_status(update_data["status"])
        await _validate_transition_guards(db, task, target_status)
        try:
            transition = StateMachine.transition(
                _parse_task_status(task.status),
                target_status,
                context={},
                skip_block_check=True,
            )
        except StateMachineError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        update_data["status"] = transition["new_status"]
        changed_target_status = _parse_task_status(transition["new_status"])
    for field, value in update_data.items():
        setattr(task, field, value)
    if "question_id" in update_data or "group_id" in update_data:
        question = await _get_question_for_project(db, task.question_id, task.project_id, task.group_id)
        if question and not task.group_id:
            task.group_id = question.group_id
        await _get_group_for_project(db, task.group_id, task.project_id)
    if changed_target_status:
        await _create_transition_approvals(db, task.id, changed_target_status)

    await db.commit()
    await db.refresh(task)
    project = await _get_project_or_400(db, task.project_id)
    group = await _get_group_for_project(db, task.group_id, task.project_id)
    question = await _get_question_for_project(db, task.question_id, task.project_id, task.group_id)
    if knowledge_assets is None:
        knowledge_assets = await _get_knowledge_assets_for_project(
            db,
            _decode_knowledge_asset_ids(task.knowledge_asset_ids),
            task.project_id,
        )
    return _task_to_dict(task, project, group, question, knowledge_assets)


@router.post("/{task_id}/transition")
async def transition_content_task(
    task_id: UUID,
    data: ContentTaskTransition,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("editor", "project_owner")),
):
    """按统一状态机推进内容任务状态，并返回可审计的流转结果。"""
    result = await db.execute(select(ContentTask).where(ContentTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Content task not found")

    try:
        target_status = _parse_task_status(data.target_status)
        await _validate_transition_guards(db, task, target_status)
        transition = StateMachine.transition(
            _parse_task_status(task.status),
            target_status,
            context=data.context,
            skip_block_check=data.skip_block_check,
        )
    except StateMachineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not transition["success"]:
        return {
            **transition,
            "task": _task_to_dict(task),
        }

    task.status = transition["new_status"]
    await _create_transition_approvals(db, task.id, _parse_task_status(transition["new_status"]))
    await db.commit()
    await db.refresh(task)
    project = await _get_project_or_400(db, task.project_id)
    group = await _get_group_for_project(db, task.group_id, task.project_id)
    question = await _get_question_for_project(db, task.question_id, task.project_id, task.group_id)
    return {
        **transition,
        "task": _task_to_dict(task, project, group, question),
    }


@router.delete("/{task_id}")
async def delete_content_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("strategist", "project_owner")),
):
    """删除内容任务"""
    result = await db.execute(select(ContentTask).where(ContentTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Content task not found")

    draft_ids = select(ContentDraft.id).where(ContentDraft.task_id == task_id)
    await db.execute(
        update(ContentFeedback)
        .where(ContentFeedback.draft_id.in_(draft_ids))
        .values(draft_id=None)
        .execution_options(synchronize_session=False)
    )
    await db.execute(
        delete(PublishRecord)
        .where(PublishRecord.task_id == task_id)
        .execution_options(synchronize_session=False)
    )
    await db.execute(
        delete(Approval)
        .where(
            Approval.object_type == "content_task",
            Approval.object_id == task_id,
        )
        .execution_options(synchronize_session=False)
    )

    await db.delete(task)
    await db.commit()
    return {"message": "Deleted"}
