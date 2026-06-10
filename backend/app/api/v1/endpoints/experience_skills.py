import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles
from app.core.database import get_db
from app.models.experience_skill import ExperienceSkill, ExperienceSkillSuggestion, ExperienceSkillVersion
from app.models.project import Project
from app.models.user import User

router = APIRouter()


def _loads(value: Optional[str]) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _dumps(value: Optional[dict]) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


class ExperienceSkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    scope: str = Field(default="project", max_length=50)
    project_id: Optional[UUID] = None
    industry: Optional[str] = Field(default=None, max_length=100)
    trigger_scene: str = Field(default="article_writing", max_length=100)
    skill_type: str = Field(default="rule", max_length=100)
    source_type: Optional[str] = Field(default="manual", max_length=100)
    source_refs: Optional[dict] = None
    confidence: Optional[float] = Field(default=0.6, ge=0, le=1)
    status: str = Field(default="active", max_length=50)


class ExperienceSkillUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    content: Optional[str] = Field(default=None, min_length=1)
    scope: Optional[str] = Field(default=None, max_length=50)
    project_id: Optional[UUID] = None
    industry: Optional[str] = Field(default=None, max_length=100)
    trigger_scene: Optional[str] = Field(default=None, max_length=100)
    skill_type: Optional[str] = Field(default=None, max_length=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    status: Optional[str] = Field(default=None, max_length=50)


class ExperienceSkillRevision(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    content: Optional[str] = Field(default=None, min_length=1)
    scope: Optional[str] = Field(default=None, max_length=50)
    project_id: Optional[UUID] = None
    industry: Optional[str] = Field(default=None, max_length=100)
    trigger_scene: Optional[str] = Field(default=None, max_length=100)
    skill_type: Optional[str] = Field(default=None, max_length=100)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    status: Optional[str] = Field(default=None, max_length=50)
    revision_reason: str = Field(default="手动修订", max_length=1000)
    change_type: str = Field(default="revise", max_length=100)


def _skill_to_dict(item: ExperienceSkill) -> dict:
    return {
        "id": str(item.id),
        "name": item.name,
        "scope": item.scope,
        "project_id": str(item.project_id) if item.project_id else None,
        "industry": item.industry,
        "trigger_scene": item.trigger_scene,
        "skill_type": item.skill_type,
        "content": item.content,
        "source_type": item.source_type,
        "source_refs": _loads(item.source_refs_json),
        "confidence": float(item.confidence) if item.confidence is not None else None,
        "usage_count": item.usage_count,
        "success_count": item.success_count,
        "current_version": item.current_version,
        "version": item.current_version,
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _version_to_dict(item: ExperienceSkillVersion) -> dict:
    return {
        "id": str(item.id),
        "skill_id": str(item.skill_id),
        "version": item.version,
        "name": item.name,
        "scope": item.scope,
        "project_id": str(item.project_id) if item.project_id else None,
        "industry": item.industry,
        "trigger_scene": item.trigger_scene,
        "skill_type": item.skill_type,
        "content": item.content,
        "status": item.status,
        "confidence": float(item.confidence) if item.confidence is not None else None,
        "change_type": item.change_type,
        "revision_reason": item.revision_reason,
        "source_refs": _loads(item.source_refs_json),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _suggestion_to_dict(item: ExperienceSkillSuggestion) -> dict:
    return {
        "id": str(item.id),
        "project_id": str(item.project_id) if item.project_id else None,
        "suggested_scope": item.suggested_scope,
        "industry": item.industry,
        "trigger_scene": item.trigger_scene,
        "skill_type": item.skill_type,
        "name": item.name,
        "suggestion_text": item.suggestion_text,
        "reason": item.reason,
        "evidence": item.evidence,
        "risk_note": item.risk_note,
        "source_type": item.source_type,
        "source_refs": _loads(item.source_refs_json),
        "confidence": float(item.confidence) if item.confidence is not None else None,
        "status": item.status,
        "approved_skill_id": str(item.approved_skill_id) if item.approved_skill_id else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


async def _get_project(db: AsyncSession, project_id: Optional[UUID]) -> Optional[Project]:
    if not project_id:
        return None
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _get_skill_or_404(db: AsyncSession, skill_id: UUID) -> ExperienceSkill:
    result = await db.execute(select(ExperienceSkill).where(ExperienceSkill.id == skill_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Experience skill not found")
    return item


def _snapshot_version(
    item: ExperienceSkill,
    *,
    version: Optional[int] = None,
    change_type: str = "revise",
    revision_reason: Optional[str] = None,
) -> ExperienceSkillVersion:
    target_version = version if version is not None else int(item.current_version or 1)
    return ExperienceSkillVersion(
        skill_id=item.id,
        version=target_version,
        name=item.name,
        scope=item.scope,
        project_id=item.project_id,
        industry=item.industry,
        trigger_scene=item.trigger_scene,
        skill_type=item.skill_type,
        content=item.content,
        status=item.status,
        confidence=item.confidence,
        change_type=change_type,
        revision_reason=revision_reason,
        source_refs_json=item.source_refs_json,
    )


async def _create_skill_version(
    db: AsyncSession,
    item: ExperienceSkill,
    *,
    change_type: str,
    revision_reason: Optional[str],
) -> None:
    db.add(
        _snapshot_version(
            item,
            version=int(item.current_version or 1),
            change_type=change_type,
            revision_reason=revision_reason,
        )
    )


async def _apply_revision(
    db: AsyncSession,
    item: ExperienceSkill,
    update_data: dict,
    *,
    change_type: str,
    revision_reason: str,
) -> ExperienceSkill:
    for key, value in update_data.items():
        setattr(item, key, value)
    item.current_version = int(item.current_version or 1) + 1
    await db.flush()
    await _create_skill_version(
        db,
        item,
        change_type=change_type,
        revision_reason=revision_reason,
    )
    return item


@router.get("")
async def list_skills(
    project_id: Optional[UUID] = Query(None),
    scope: Optional[str] = Query(None),
    trigger_scene: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("admin", "project_owner", "strategist", "editor")),
):
    filters = []
    project = await _get_project(db, project_id) if project_id else None
    if project_id:
        if scope == "project":
            filters.append(ExperienceSkill.project_id == project_id)
        elif scope == "industry":
            filters.append(ExperienceSkill.industry == project.industry if project else ExperienceSkill.project_id == project_id)
        elif scope == "global":
            filters.append(ExperienceSkill.scope == "global")
        else:
            filters.append(
                or_(
                    ExperienceSkill.project_id == project_id,
                    and_(ExperienceSkill.scope == "industry", ExperienceSkill.industry == project.industry) if project and project.industry else false(),
                    ExperienceSkill.scope == "global",
                )
            )
    if scope:
        filters.append(ExperienceSkill.scope == scope)
    if trigger_scene:
        filters.append(ExperienceSkill.trigger_scene == trigger_scene)
    if status:
        filters.append(ExperienceSkill.status == status)
    query = select(ExperienceSkill)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(ExperienceSkill.updated_at.desc(), ExperienceSkill.created_at.desc())
    result = await db.execute(query)
    return [_skill_to_dict(item) for item in result.scalars().all()]


@router.post("")
async def create_skill(
    data: ExperienceSkillCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "project_owner", "strategist")),
):
    project = await _get_project(db, data.project_id)
    industry = data.industry or (project.industry if project else None)
    item = ExperienceSkill(
        name=data.name,
        content=data.content,
        scope=data.scope,
        project_id=data.project_id,
        industry=industry,
        trigger_scene=data.trigger_scene,
        skill_type=data.skill_type,
        source_type=data.source_type,
        source_refs_json=_dumps(data.source_refs),
        confidence=data.confidence,
        status=data.status,
        current_version=1,
    )
    db.add(item)
    await db.flush()
    await _create_skill_version(db, item, change_type="create", revision_reason="创建技能")
    await db.commit()
    await db.refresh(item)
    return _skill_to_dict(item)


@router.put("/{skill_id}")
async def update_skill(
    skill_id: UUID,
    data: ExperienceSkillUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "project_owner", "strategist")),
):
    item = await _get_skill_or_404(db, skill_id)
    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        await _apply_revision(
            db,
            item,
            update_data,
            change_type="update",
            revision_reason="手动编辑",
        )
    await db.commit()
    await db.refresh(item)
    return _skill_to_dict(item)


@router.post("/{skill_id}/revise")
async def revise_skill(
    skill_id: UUID,
    data: ExperienceSkillRevision,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "project_owner", "strategist")),
):
    item = await _get_skill_or_404(db, skill_id)
    update_data = data.model_dump(exclude_unset=True, exclude={"revision_reason", "change_type"})
    if not update_data:
        raise HTTPException(status_code=400, detail="No revision fields provided")
    await _apply_revision(
        db,
        item,
        update_data,
        change_type=data.change_type or "revise",
        revision_reason=data.revision_reason,
    )
    await db.commit()
    await db.refresh(item)
    return _skill_to_dict(item)


@router.get("/{skill_id}/versions")
async def list_skill_versions(
    skill_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("admin", "project_owner", "strategist", "editor")),
):
    await _get_skill_or_404(db, skill_id)
    result = await db.execute(
        select(ExperienceSkillVersion)
        .where(ExperienceSkillVersion.skill_id == skill_id)
        .order_by(ExperienceSkillVersion.version.desc())
    )
    return [_version_to_dict(item) for item in result.scalars().all()]


@router.post("/{skill_id}/versions/{version}/rollback")
async def rollback_skill_version(
    skill_id: UUID,
    version: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "project_owner", "strategist")),
):
    item = await _get_skill_or_404(db, skill_id)
    result = await db.execute(
        select(ExperienceSkillVersion).where(
            ExperienceSkillVersion.skill_id == skill_id,
            ExperienceSkillVersion.version == version,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Experience skill version not found")
    rollback_data = {
        "name": target.name,
        "scope": target.scope,
        "project_id": target.project_id,
        "industry": target.industry,
        "trigger_scene": target.trigger_scene,
        "skill_type": target.skill_type,
        "content": target.content,
        "confidence": target.confidence,
        "status": target.status,
    }
    item.source_refs_json = target.source_refs_json
    await _apply_revision(
        db,
        item,
        rollback_data,
        change_type="rollback",
        revision_reason=f"回滚到 v{version}",
    )
    await db.commit()
    await db.refresh(item)
    return _skill_to_dict(item)


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "project_owner", "strategist")),
):
    item = await _get_skill_or_404(db, skill_id)
    await db.delete(item)
    await db.commit()
    return {"message": "Deleted"}


@router.get("/suggestions")
async def list_skill_suggestions(
    project_id: Optional[UUID] = Query(None),
    scope: Optional[str] = Query(None),
    trigger_scene: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("admin", "project_owner", "strategist", "editor")),
):
    filters = []
    project = await _get_project(db, project_id) if project_id else None
    if project_id:
        if scope == "project":
            filters.append(ExperienceSkillSuggestion.project_id == project_id)
        elif scope == "industry":
            filters.append(ExperienceSkillSuggestion.industry == project.industry if project else ExperienceSkillSuggestion.project_id == project_id)
        elif scope == "global":
            filters.append(ExperienceSkillSuggestion.suggested_scope == "global")
        else:
            filters.append(
                or_(
                    ExperienceSkillSuggestion.project_id == project_id,
                    and_(ExperienceSkillSuggestion.suggested_scope == "industry", ExperienceSkillSuggestion.industry == project.industry) if project and project.industry else false(),
                    ExperienceSkillSuggestion.suggested_scope == "global",
                )
            )
    if scope:
        filters.append(ExperienceSkillSuggestion.suggested_scope == scope)
    if trigger_scene:
        filters.append(ExperienceSkillSuggestion.trigger_scene == trigger_scene)
    if status:
        filters.append(ExperienceSkillSuggestion.status == status)
    query = select(ExperienceSkillSuggestion)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(ExperienceSkillSuggestion.created_at.desc())
    result = await db.execute(query)
    return [_suggestion_to_dict(item) for item in result.scalars().all()]


@router.post("/suggestions/{suggestion_id}/approve")
async def approve_skill_suggestion(
    suggestion_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "project_owner", "strategist")),
):
    result = await db.execute(select(ExperienceSkillSuggestion).where(ExperienceSkillSuggestion.id == suggestion_id))
    suggestion = result.scalar_one_or_none()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Experience skill suggestion not found")
    if suggestion.status == "approved" and suggestion.approved_skill_id:
        skill_result = await db.execute(select(ExperienceSkill).where(ExperienceSkill.id == suggestion.approved_skill_id))
        skill = skill_result.scalar_one_or_none()
        return {"suggestion": _suggestion_to_dict(suggestion), "skill": _skill_to_dict(skill) if skill else None}

    project = await _get_project(db, suggestion.project_id)
    name = suggestion.name or f"{suggestion.trigger_scene}经验技能"
    skill = ExperienceSkill(
        name=name[:200],
        scope=suggestion.suggested_scope,
        project_id=suggestion.project_id,
        industry=suggestion.industry or (project.industry if project else None),
        trigger_scene=suggestion.trigger_scene,
        skill_type=suggestion.skill_type,
        content=suggestion.suggestion_text,
        source_type=suggestion.source_type,
        source_refs_json=suggestion.source_refs_json,
        confidence=suggestion.confidence,
        status="active",
        current_version=1,
    )
    db.add(skill)
    await db.flush()
    await _create_skill_version(db, skill, change_type="create", revision_reason="确认建议")
    suggestion.status = "approved"
    suggestion.approved_skill_id = skill.id
    await db.commit()
    await db.refresh(skill)
    await db.refresh(suggestion)
    return {"suggestion": _suggestion_to_dict(suggestion), "skill": _skill_to_dict(skill)}
