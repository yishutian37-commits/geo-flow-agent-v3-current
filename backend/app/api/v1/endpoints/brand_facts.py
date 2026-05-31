import json
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_roles
from app.core.database import get_db
from app.models.user import User
from app.schemas.brand_fact import (
    BrandFactCreate,
    BrandFactOut,
    BrandFactUpdate,
    BrandFactEventOut,
    ExtractFromCorpusRequest,
    ExtractFromTextRequest,
    BrandFactConfirmRequest,
)
from app.services.brand_fact_service import BrandFactService

router = APIRouter()


def _event_to_out(event) -> BrandFactEventOut:
    snapshot = None
    if event.snapshot_json:
        try:
            snapshot = json.loads(event.snapshot_json)
        except json.JSONDecodeError:
            snapshot = {"raw": event.snapshot_json}
    return BrandFactEventOut(
        id=event.id,
        fact_id=event.fact_id,
        action=event.action,
        actor_id=event.actor_id,
        previous_status=event.previous_status,
        new_status=event.new_status,
        snapshot=snapshot,
        note=event.note,
        created_at=event.created_at,
    )


@router.get("", response_model=List[BrandFactOut])
async def list_brand_facts(
    brand_id: Optional[UUID] = Query(None),
    project_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    fact_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db)
):
    """获取品牌事实列表
    支持通过 project_id 跨品牌筛选
    """
    service = BrandFactService(db)
    facts = await service.list_facts(
        brand_id=brand_id,
        project_id=project_id,
        status=status,
        fact_type=fact_type,
        skip=skip,
        limit=limit
    )
    return facts


@router.post("", response_model=BrandFactOut)
async def create_brand_fact(
    data: BrandFactCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("collector", "project_owner")),
):
    """创建品牌事实（初始状态为 draft）"""
    service = BrandFactService(db)
    try:
        return await service.create_fact(data, actor_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{fact_id}", response_model=BrandFactOut)
async def get_brand_fact(
    fact_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """获取事实详情"""
    service = BrandFactService(db)
    fact = await service.get_fact(fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail="Brand fact not found")
    return fact


@router.put("/{fact_id}", response_model=BrandFactOut)
async def update_brand_fact(
    fact_id: UUID,
    data: BrandFactUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("collector", "project_owner", "compliance_reviewer")),
):
    service = BrandFactService(db)
    fact = await service.update_fact(fact_id, data.model_dump(exclude_unset=True), actor_id=user.id)
    if not fact:
        raise HTTPException(status_code=404, detail="Brand fact not found")
    return fact


@router.get("/{fact_id}/history", response_model=List[BrandFactEventOut])
async def list_brand_fact_history(
    fact_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    service = BrandFactService(db)
    fact = await service.get_fact(fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail="Brand fact not found")
    events = await service.list_events(fact_id, skip=skip, limit=limit)
    return [_event_to_out(event) for event in events]


@router.post("/{fact_id}/confirm")
async def confirm_brand_fact(
    fact_id: UUID,
    req: BrandFactConfirmRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("client", "project_owner", "compliance_reviewer")),
):
    """确认品牌事实（draft → confirmed）"""
    service = BrandFactService(db)
    try:
        fact = await service.confirm_fact(
            fact_id,
            user.id,
            req.public_wording,
            confirmation_note=req.confirmation_note,
            evidence_file_url=req.evidence_file_url,
            evidence_type=req.evidence_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not fact:
        raise HTTPException(status_code=404, detail="Brand fact not found")
    return fact


@router.post("/{fact_id}/dispute")
async def dispute_brand_fact(
    fact_id: UUID,
    reason: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("client", "project_owner", "compliance_reviewer")),
):
    """标记事实为争议状态"""
    service = BrandFactService(db)
    fact = await service.dispute_fact(fact_id, reason, actor_id=user.id)
    if not fact:
        raise HTTPException(status_code=404, detail="Brand fact not found")
    return fact


@router.post("/{fact_id}/expire")
async def expire_brand_fact(
    fact_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("client", "project_owner", "compliance_reviewer")),
):
    """标记事实为过期"""
    service = BrandFactService(db)
    fact = await service.expire_fact(fact_id, actor_id=user.id)
    if not fact:
        raise HTTPException(status_code=404, detail="Brand fact not found")
    return fact


@router.post("/check-for-publish")
async def check_facts_for_publish(
    fact_ids: List[UUID] = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """检查事实列表是否可用于发布"""
    service = BrandFactService(db)
    result = await service.check_facts_for_publish(fact_ids)
    return result


@router.post("/extract-from-corpus")
async def extract_from_corpus(
    req: ExtractFromCorpusRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("collector", "project_owner")),
):
    """从语料库提取事实候选"""
    service = BrandFactService(db)
    try:
        facts = await service.extract_from_corpus(req.corpus_item_id, req.suggested_facts, actor_id=user.id)
        return facts
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/extract-from-text", response_model=List[BrandFactOut])
async def extract_from_text(
    req: ExtractFromTextRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("collector", "project_owner")),
):
    """从整段企业资料中调用 AI 批量提取品牌事实候选。"""
    service = BrandFactService(db)
    try:
        return await service.extract_from_text(
            brand_id=req.brand_id,
            content=req.content,
            source=req.source or "pasted_enterprise_material",
            model_id=req.model_id,
            max_facts=req.max_facts,
            actor_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
