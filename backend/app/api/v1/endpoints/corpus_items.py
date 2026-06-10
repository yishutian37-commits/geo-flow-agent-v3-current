from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.models.corpus_item import CorpusItem
from app.services.project_knowledge_service import ProjectKnowledgeService

router = APIRouter()


class CorpusItemCreate(BaseModel):
    project_id: UUID
    content: str = Field(..., min_length=1)
    title: Optional[str] = None
    source_type: Optional[str] = None
    source_url: Optional[str] = Field(default=None, max_length=1000)
    tags: Optional[str] = None
    knowledge_layer: str = Field(default="basic_info", max_length=100)
    business_use: str = Field(default="general", max_length=100)
    evidence_level: str = Field(default="unverified", max_length=100)
    reusable_scope: str = Field(default="project", max_length=100)
    contains_factual_claim: bool = False


class CorpusItemUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = Field(default=None, min_length=1)
    source_type: Optional[str] = None
    source_url: Optional[str] = Field(default=None, max_length=1000)
    tags: Optional[str] = None
    knowledge_layer: Optional[str] = Field(default=None, max_length=100)
    business_use: Optional[str] = Field(default=None, max_length=100)
    evidence_level: Optional[str] = Field(default=None, max_length=100)
    reusable_scope: Optional[str] = Field(default=None, max_length=100)
    contains_factual_claim: Optional[bool] = None


class CorpusIngestRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    project_id: UUID
    title: Optional[str] = Field(default=None, max_length=500)
    content: str = Field(..., min_length=10)
    source_type: Optional[str] = Field(default="other", max_length=100)
    source_url: Optional[str] = Field(default=None, max_length=1000)
    max_items: int = Field(default=20, ge=1, le=50)
    model_id: Optional[str] = Field(default=None, max_length=200)


def _corpus_to_dict(item: CorpusItem) -> dict:
    return {
        "id": str(item.id),
        "project_id": str(item.project_id),
        "title": item.title,
        "content": item.content,
        "source_type": item.source_type,
        "source_url": item.source_url,
        "tags": item.tags,
        "knowledge_layer": item.knowledge_layer or "basic_info",
        "business_use": item.business_use or "general",
        "evidence_level": item.evidence_level or "unverified",
        "reusable_scope": item.reusable_scope or "project",
        "contains_factual_claim": item.contains_factual_claim,
        "confidence": float(item.confidence) if item.confidence else None,
        "source_fact_candidate": str(item.source_fact_candidate) if item.source_fact_candidate else None,
        "created_by": str(item.created_by) if item.created_by else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.get("")
async def list_corpus_items(
    project_id: Optional[UUID] = Query(None),
    contains_factual_claim: Optional[bool] = Query(None),
    source_type: Optional[str] = Query(None),
    knowledge_layer: Optional[str] = None,
    business_use: Optional[str] = None,
    evidence_level: Optional[str] = None,
    reusable_scope: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db)
):
    """获取语料库列表"""
    query = select(CorpusItem)
    filters = []
    if project_id:
        filters.append(CorpusItem.project_id == project_id)
    if contains_factual_claim is not None:
        filters.append(CorpusItem.contains_factual_claim == contains_factual_claim)
    if source_type:
        filters.append(CorpusItem.source_type == source_type)
    if knowledge_layer:
        filters.append(CorpusItem.knowledge_layer == knowledge_layer)
    if business_use:
        filters.append(CorpusItem.business_use == business_use)
    if evidence_level:
        filters.append(CorpusItem.evidence_level == evidence_level)
    if reusable_scope:
        filters.append(CorpusItem.reusable_scope == reusable_scope)
    if filters:
        query = query.where(and_(*filters))
    query = query.offset(skip).limit(limit).order_by(CorpusItem.created_at.desc())
    result = await db.execute(query)
    items = result.scalars().all()
    return [_corpus_to_dict(item) for item in items]


@router.post("")
async def create_corpus_item(
    payload: CorpusItemCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建语料条目"""
    item = CorpusItem(
        project_id=payload.project_id,
        title=payload.title,
        content=payload.content,
        source_type=payload.source_type,
        source_url=payload.source_url,
        tags=payload.tags,
        knowledge_layer=payload.knowledge_layer,
        business_use=payload.business_use,
        evidence_level=payload.evidence_level,
        reusable_scope=payload.reusable_scope,
        contains_factual_claim=payload.contains_factual_claim,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _corpus_to_dict(item)


@router.post("/ingest")
async def ingest_corpus_items(
    payload: CorpusIngestRequest,
    db: AsyncSession = Depends(get_db)
):
    """调用 AI 将长资料拆分为多条项目知识资产。"""
    service = ProjectKnowledgeService(db)
    try:
        items = await service.ingest_material(
            project_id=payload.project_id,
            title=payload.title,
            content=payload.content,
            source_type=payload.source_type,
            source_url=payload.source_url,
            max_items=payload.max_items,
            model_id=payload.model_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "created": len(items),
        "items": [_corpus_to_dict(item) for item in items],
    }


@router.get("/{item_id}")
async def get_corpus_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """获取语料详情"""
    result = await db.execute(select(CorpusItem).where(CorpusItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Corpus item not found")
    return _corpus_to_dict(item)


@router.put("/{item_id}")
async def update_corpus_item(
    item_id: UUID,
    payload: CorpusItemUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新语料条目"""
    result = await db.execute(select(CorpusItem).where(CorpusItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Corpus item not found")

    if payload.title is not None:
        item.title = payload.title
    if payload.content is not None:
        item.content = payload.content
    if payload.source_type is not None:
        item.source_type = payload.source_type
    if payload.source_url is not None:
        item.source_url = payload.source_url
    if payload.tags is not None:
        item.tags = payload.tags
    if payload.knowledge_layer is not None:
        item.knowledge_layer = payload.knowledge_layer
    if payload.business_use is not None:
        item.business_use = payload.business_use
    if payload.evidence_level is not None:
        item.evidence_level = payload.evidence_level
    if payload.reusable_scope is not None:
        item.reusable_scope = payload.reusable_scope
    if payload.contains_factual_claim is not None:
        item.contains_factual_claim = payload.contains_factual_claim

    await db.commit()
    await db.refresh(item)
    return _corpus_to_dict(item)


@router.delete("/{item_id}")
async def delete_corpus_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """删除语料条目"""
    result = await db.execute(select(CorpusItem).where(CorpusItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Corpus item not found")
    await db.delete(item)
    await db.commit()
    return {"message": "Deleted"}
