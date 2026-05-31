from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.models.corpus_item import CorpusItem

router = APIRouter()


def _corpus_to_dict(item: CorpusItem) -> dict:
    return {
        "id": str(item.id),
        "project_id": str(item.project_id),
        "title": item.title,
        "content": item.content,
        "source_type": item.source_type,
        "tags": item.tags,
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
    if filters:
        query = query.where(and_(*filters))
    query = query.offset(skip).limit(limit).order_by(CorpusItem.created_at.desc())
    result = await db.execute(query)
    items = result.scalars().all()
    return [_corpus_to_dict(item) for item in items]


@router.post("")
async def create_corpus_item(
    project_id: UUID,
    content: str,
    title: Optional[str] = None,
    source_type: Optional[str] = None,
    tags: Optional[str] = None,
    contains_factual_claim: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """创建语料条目"""
    item = CorpusItem(
        project_id=project_id,
        title=title,
        content=content,
        source_type=source_type,
        tags=tags,
        contains_factual_claim=contains_factual_claim,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _corpus_to_dict(item)


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
    title: Optional[str] = None,
    content: Optional[str] = None,
    source_type: Optional[str] = None,
    tags: Optional[str] = None,
    contains_factual_claim: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """更新语料条目"""
    result = await db.execute(select(CorpusItem).where(CorpusItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Corpus item not found")

    if title is not None:
        item.title = title
    if content is not None:
        item.content = content
    if source_type is not None:
        item.source_type = source_type
    if tags is not None:
        item.tags = tags
    if contains_factual_claim is not None:
        item.contains_factual_claim = contains_factual_claim

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
