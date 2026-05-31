from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.models.brand import Brand
from app.models.project import Project
from app.schemas.brand import BrandCreate, BrandOut

router = APIRouter()


def _brand_to_dict(brand: Brand) -> dict:
    return {
        "id": str(brand.id),
        "project_id": str(brand.project_id),
        "brand_name": brand.brand_name,
        "company_name": brand.company_name,
        "aliases": brand.aliases,
        "official_site": brand.official_site,
        "description": brand.description,
        "created_at": brand.created_at.isoformat() if brand.created_at else None,
        "updated_at": brand.updated_at.isoformat() if brand.updated_at else None,
    }


@router.get("")
async def list_brands(
    project_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """获取品牌列表"""
    query = select(Brand)
    if project_id:
        query = query.where(Brand.project_id == project_id)
    query = query.order_by(Brand.created_at.desc())
    result = await db.execute(query)
    brands = result.scalars().all()
    return [_brand_to_dict(b) for b in brands]


@router.post("", response_model=BrandOut)
async def create_brand(
    data: BrandCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建品牌"""
    project_result = await db.execute(select(Project.id).where(Project.id == data.project_id))
    if project_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail="品牌必须绑定已存在的项目")

    brand = Brand(
        project_id=data.project_id,
        brand_name=data.brand_name,
        company_name=data.company_name,
        aliases=data.aliases,
        official_site=data.official_site,
        description=data.description,
    )
    db.add(brand)
    await db.commit()
    await db.refresh(brand)
    return brand


@router.get("/{brand_id}")
async def get_brand(
    brand_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """获取品牌详情"""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    return _brand_to_dict(brand)
