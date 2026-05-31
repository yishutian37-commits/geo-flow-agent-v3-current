from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.baseline_run import BaselineRun
from app.models.model_target import ModelTarget
from app.models.monitoring import MonitoringRun
from app.models.project import Project
from app.schemas.model_target import ModelTargetCreate, ModelTargetUpdate

router = APIRouter()


def _normalize_recognition_mode(value: Optional[str]) -> str:
    return "vision" if str(value or "").strip().lower() == "vision" else "text"


def _target_to_dict(target: ModelTarget) -> dict:
    return {
        "id": str(target.id),
        "project_id": str(target.project_id),
        "product_name": target.product_name,
        "supported_mechanisms": target.supported_mechanisms,
        "search_backend": target.search_backend,
        "search_backend_confidence": target.search_backend_confidence,
        "search_backend_evidence": target.search_backend_evidence,
        "last_verified_at": target.last_verified_at.isoformat() if target.last_verified_at else None,
        "api_available": target.api_available,
        "access_method": target.access_method,
        "recognition_mode": _normalize_recognition_mode(target.recognition_mode),
        "web_url": target.web_url,
        "input_selector": target.input_selector,
        "submit_selector": target.submit_selector,
        "response_selector": target.response_selector,
        "notes": target.notes,
        "created_at": target.created_at.isoformat() if target.created_at else None,
    }


async def _project_exists(db: AsyncSession, project_id: UUID) -> bool:
    result = await db.execute(select(Project.id).where(Project.id == project_id))
    return result.scalar_one_or_none() is not None


@router.get("")
async def list_model_targets(
    project_id: Optional[UUID] = Query(None),
    mechanism_type: Optional[str] = Query(None),
    api_available: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """查询项目检测平台。"""
    filters = []
    if project_id:
        filters.append(ModelTarget.project_id == project_id)
    if mechanism_type:
        filters.append(ModelTarget.supported_mechanisms.ilike(f"%{mechanism_type}%"))
    if api_available is not None:
        filters.append(ModelTarget.api_available == api_available)

    query = select(ModelTarget)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(ModelTarget.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return [_target_to_dict(item) for item in result.scalars().all()]


@router.post("")
async def create_model_target(
    data: ModelTargetCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建检测平台及其回答机制/检索后端信息。"""
    if not await _project_exists(db, data.project_id):
        raise HTTPException(status_code=400, detail="检测平台必须绑定已存在的项目")

    payload = data.model_dump()
    payload["recognition_mode"] = _normalize_recognition_mode(payload.get("recognition_mode"))
    target = ModelTarget(**payload)
    db.add(target)
    await db.commit()
    await db.refresh(target)
    return _target_to_dict(target)


@router.get("/{target_id}")
async def get_model_target(
    target_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ModelTarget).where(ModelTarget.id == target_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Model target not found")
    return _target_to_dict(target)


@router.put("/{target_id}")
async def update_model_target(
    target_id: UUID,
    data: ModelTargetUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ModelTarget).where(ModelTarget.id == target_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Model target not found")

    payload = data.model_dump(exclude_unset=True)
    if "recognition_mode" in payload:
        payload["recognition_mode"] = _normalize_recognition_mode(payload.get("recognition_mode"))
    for field, value in payload.items():
        setattr(target, field, value)

    await db.commit()
    await db.refresh(target)
    return _target_to_dict(target)


@router.delete("/{target_id}")
async def delete_model_target(
    target_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ModelTarget).where(ModelTarget.id == target_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Model target not found")

    monitoring_ref = await db.execute(
        select(MonitoringRun.id).where(MonitoringRun.model_target_id == target_id).limit(1)
    )
    baseline_ref = await db.execute(
        select(BaselineRun.id).where(BaselineRun.model_target_id == target_id).limit(1)
    )
    if monitoring_ref.scalar_one_or_none() or baseline_ref.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="该检测平台已被检测记录或基线记录引用，请先删除相关检测记录/基线记录后再删除。",
        )

    await db.delete(target)
    await db.commit()
    return {"message": "Deleted"}
