from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.project import Project
from app.models.question import Question, QuestionGroup
from app.services.question_template_learning import record_question_template_feedback
from app.schemas.question import (
    QuestionCreate,
    QuestionUpdate,
    QuestionOut,
    QuestionGroupCreate,
    QuestionGroupUpdate,
    QuestionGroupOut,
)

router = APIRouter()


def _group_to_dict(group: QuestionGroup, include_questions: bool = True) -> dict:
    data = {
        "id": str(group.id),
        "project_id": str(group.project_id),
        "layer": group.layer,
        "intent_name": group.intent_name,
        "representative_question": group.representative_question,
        "priority": group.priority,
        "status": group.status,
        "created_at": group.created_at.isoformat() if group.created_at else None,
    }
    if include_questions:
        data["questions"] = [
            _question_to_dict(q)
            for q in sorted(
                group.questions,
                key=lambda item: (not bool(item.enabled), not bool(item.focus), -(item.priority or 0), item.created_at),
            )
        ]
    return data


def _question_to_dict(question: Question) -> dict:
    return {
        "id": str(question.id),
        "group_id": str(question.group_id),
        "question_text": question.question_text,
        "question_type": question.question_type,
        "tags": question.tags,
        "keyword_breakdown": question.keyword_breakdown,
        "question_formula": question.question_formula,
        "business_value": question.business_value,
        "evidence_support": question.evidence_support,
        "content_actionability": question.content_actionability,
        "recommended_platforms": question.recommended_platforms,
        "priority": question.priority,
        "sample_policy": question.sample_policy,
        "enabled": question.enabled,
        "focus": question.focus,
        "created_at": question.created_at.isoformat() if question.created_at else None,
    }


async def _project_for_group(db: AsyncSession, group: QuestionGroup) -> Optional[Project]:
    result = await db.execute(select(Project).where(Project.id == group.project_id))
    return result.scalar_one_or_none()


def _update_action(before: dict, after: dict) -> str:
    changed = {
        key
        for key in set(before.keys()) | set(after.keys())
        if before.get(key) != after.get(key)
    }
    if changed and changed <= {"enabled"}:
        return "toggle_enabled"
    if changed and changed <= {"focus"}:
        return "toggle_focus"
    return "update_question"


async def _record_question_learning_event(
    db: AsyncSession,
    *,
    project: Optional[Project],
    group_id: UUID,
    question_id: Optional[UUID],
    action: str,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
) -> None:
    if not project:
        return
    await record_question_template_feedback(
        db,
        project_id=str(project.id),
        industry=str(project.industry or "default"),
        group_id=str(group_id),
        question_id=str(question_id) if question_id else None,
        action=action,
        before_text=(before or {}).get("question_text"),
        after_text=(after or {}).get("question_text"),
        before_payload=before,
        after_payload=after,
    )


@router.get("/groups")
async def list_question_groups(
    project_id: Optional[UUID] = Query(None),
    layer: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """获取问题意图组列表"""
    query = select(QuestionGroup)
    filters = []
    if project_id:
        filters.append(QuestionGroup.project_id == project_id)
    if layer:
        filters.append(QuestionGroup.layer == layer)
    if status:
        filters.append(QuestionGroup.status == status)
    else:
        filters.append(QuestionGroup.status != "archived")
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(QuestionGroup.priority.desc(), QuestionGroup.created_at.desc())
    query = query.options(selectinload(QuestionGroup.questions))
    result = await db.execute(query)
    groups = result.scalars().all()
    return [_group_to_dict(g) for g in groups]


@router.post("/groups")
async def create_question_group(
    data: QuestionGroupCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建问题意图组"""
    project_result = await db.execute(select(Project.id).where(Project.id == data.project_id))
    if project_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail="问题组必须绑定已存在的项目")

    group = QuestionGroup(
        project_id=data.project_id,
        layer=data.layer,
        intent_name=data.intent_name,
        representative_question=data.representative_question,
        priority=data.priority,
        status=data.status,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return _group_to_dict(group, include_questions=False)


@router.get("/groups/{group_id}")
async def get_question_group(
    group_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """获取问题意图组详情（含问题列表）"""
    result = await db.execute(
        select(QuestionGroup)
        .where(QuestionGroup.id == group_id)
        .options(selectinload(QuestionGroup.questions))
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Question group not found")
    return _group_to_dict(group)


@router.put("/groups/{group_id}")
async def update_question_group(
    group_id: UUID,
    data: QuestionGroupUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新问题意图组"""
    result = await db.execute(select(QuestionGroup).where(QuestionGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Question group not found")

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(group, key, value)
    await db.commit()
    await db.refresh(group)
    return _group_to_dict(group, include_questions=False)


@router.post("/groups/{group_id}/questions")
async def create_question(
    group_id: UUID,
    data: QuestionCreate,
    db: AsyncSession = Depends(get_db)
):
    """在意图组下添加问题"""
    if data.group_id and str(data.group_id) != str(group_id):
        raise HTTPException(status_code=400, detail="请求体中的 group_id 与路径中的问题组不一致")

    result = await db.execute(select(QuestionGroup).where(QuestionGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Question group not found")
    project = await _project_for_group(db, group)

    question = Question(
        group_id=group_id,
        question_text=data.question_text,
        question_type=data.question_type,
        tags=data.tags,
        keyword_breakdown=data.keyword_breakdown,
        question_formula=data.question_formula,
        business_value=data.business_value,
        evidence_support=data.evidence_support,
        content_actionability=data.content_actionability,
        recommended_platforms=data.recommended_platforms,
        priority=data.priority,
        sample_policy=data.sample_policy,
        enabled=data.enabled,
        focus=data.focus,
    )
    db.add(question)
    await db.flush()
    after = _question_to_dict(question)
    await _record_question_learning_event(
        db,
        project=project,
        group_id=group_id,
        question_id=question.id,
        action="create_question",
        after=after,
    )
    await db.commit()
    await db.refresh(question)
    return _question_to_dict(question)


@router.get("")
async def list_questions(
    group_id: Optional[UUID] = Query(None),
    sample_policy: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """获取问题列表"""
    query = select(Question)
    filters = []
    if group_id:
        filters.append(Question.group_id == group_id)
    if sample_policy:
        filters.append(Question.sample_policy == sample_policy)
    if enabled is not None:
        filters.append(Question.enabled == enabled)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(Question.priority.desc(), Question.created_at.desc())
    result = await db.execute(query)
    questions = result.scalars().all()
    return [_question_to_dict(q) for q in questions]


@router.put("/{question_id}")
async def update_question(
    question_id: UUID,
    data: QuestionUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新问题"""
    result = await db.execute(
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.group))
    )
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    before = _question_to_dict(question)
    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(question, key, value)
    await db.flush()
    after = _question_to_dict(question)
    await _record_question_learning_event(
        db,
        project=await _project_for_group(db, question.group),
        group_id=question.group_id,
        question_id=question.id,
        action=_update_action(before, after),
        before=before,
        after=after,
    )
    await db.commit()
    await db.refresh(question)
    return _question_to_dict(question)


@router.delete("/{question_id}")
async def delete_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """删除问题"""
    result = await db.execute(
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.group))
    )
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    before = _question_to_dict(question)
    project = await _project_for_group(db, question.group)
    await _record_question_learning_event(
        db,
        project=project,
        group_id=question.group_id,
        question_id=question.id,
        action="delete_question",
        before=before,
    )
    await db.delete(question)
    await db.commit()
    return {"ok": True}
