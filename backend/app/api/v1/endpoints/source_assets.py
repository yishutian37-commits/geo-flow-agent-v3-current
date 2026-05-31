from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.project import Project
from app.models.source_asset import SourceAsset
from app.schemas.source_asset import SourceAssetCreate, SourceAssetUpdate

router = APIRouter()


def _asset_to_dict(asset: SourceAsset) -> dict:
    return {
        "id": str(asset.id),
        "project_id": str(asset.project_id),
        "source_type": asset.source_type,
        "platform": asset.platform,
        "url": asset.url,
        "authority_level": asset.authority_level,
        "crawlability": asset.crawlability,
        "status": asset.status,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


async def _project_exists(db: AsyncSession, project_id: UUID) -> bool:
    result = await db.execute(select(Project.id).where(Project.id == project_id))
    return result.scalar_one_or_none() is not None


@router.get("")
async def list_source_assets(
    project_id: Optional[UUID] = Query(None),
    source_type: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """查询项目可被 AI 引用/检索的公开信源资产。"""
    filters = []
    if project_id:
        filters.append(SourceAsset.project_id == project_id)
    if source_type:
        filters.append(SourceAsset.source_type == source_type)
    if platform:
        filters.append(SourceAsset.platform == platform)
    if status:
        filters.append(SourceAsset.status == status)

    query = select(SourceAsset)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(SourceAsset.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return [_asset_to_dict(item) for item in result.scalars().all()]


@router.post("")
async def create_source_asset(
    data: SourceAssetCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建信源资产，例如官网页面、资质公示页、案例页、媒体报道或百科词条。"""
    if not await _project_exists(db, data.project_id):
        raise HTTPException(status_code=400, detail="信源资产必须绑定已存在的项目")

    asset = SourceAsset(**data.model_dump())
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return _asset_to_dict(asset)


@router.get("/{asset_id}")
async def get_source_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SourceAsset).where(SourceAsset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Source asset not found")
    return _asset_to_dict(asset)


@router.put("/{asset_id}")
async def update_source_asset(
    asset_id: UUID,
    data: SourceAssetUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SourceAsset).where(SourceAsset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Source asset not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(asset, field, value)

    await db.commit()
    await db.refresh(asset)
    return _asset_to_dict(asset)


@router.delete("/{asset_id}")
async def delete_source_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SourceAsset).where(SourceAsset.id == asset_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Source asset not found")
    await db.delete(asset)
    await db.commit()
    return {"message": "Deleted"}
