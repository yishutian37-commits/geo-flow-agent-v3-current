from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.channel_account import ChannelAccount
from app.schemas.channel_account import ChannelAccountCreate, ChannelAccountUpdate

router = APIRouter()


@router.get("")
async def list_channel_accounts(
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    publish_permission: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """获取发布渠道账号列表"""
    query = select(ChannelAccount)
    filters = []
    if platform:
        filters.append(ChannelAccount.platform == platform)
    if status:
        filters.append(ChannelAccount.status == status)
    if publish_permission is not None:
        filters.append(ChannelAccount.publish_permission == publish_permission)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(ChannelAccount.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return [_account_to_dict(item) for item in result.scalars().all()]


@router.post("")
async def create_channel_account(
    data: ChannelAccountCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建发布渠道账号"""
    tenant_id = data.tenant_id or UUID("00000000-0000-0000-0000-000000000000")
    account = ChannelAccount(
        tenant_id=tenant_id,
        platform=data.platform,
        account_name=data.account_name,
        account_type=data.account_type,
        owner_tenant_id=data.owner_tenant_id,
        login_required=data.login_required,
        publish_permission=data.publish_permission,
        publisher_url=data.publisher_url,
        title_selector=data.title_selector,
        body_selector=data.body_selector,
        risk_level=data.risk_level,
        status=data.status,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return _account_to_dict(account)


@router.get("/{account_id}")
async def get_channel_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取渠道账号详情"""
    result = await db.execute(select(ChannelAccount).where(ChannelAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Channel account not found")
    return _account_to_dict(account)


@router.put("/{account_id}")
async def update_channel_account(
    account_id: UUID,
    data: ChannelAccountUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新发布渠道账号"""
    result = await db.execute(select(ChannelAccount).where(ChannelAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Channel account not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(account, field, value)

    await db.commit()
    await db.refresh(account)
    return _account_to_dict(account)


@router.delete("/{account_id}")
async def delete_channel_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """删除发布渠道账号"""
    result = await db.execute(select(ChannelAccount).where(ChannelAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Channel account not found")
    await db.delete(account)
    await db.commit()
    return {"message": "Deleted"}


def _account_to_dict(account: ChannelAccount) -> dict:
    return {
        "id": str(account.id),
        "tenant_id": str(account.tenant_id),
        "platform": account.platform,
        "account_name": account.account_name,
        "account_type": account.account_type,
        "owner_tenant_id": str(account.owner_tenant_id) if account.owner_tenant_id else None,
        "login_required": account.login_required,
        "publish_permission": account.publish_permission,
        "publisher_url": account.publisher_url,
        "title_selector": account.title_selector,
        "body_selector": account.body_selector,
        "risk_level": account.risk_level,
        "last_publish_at": account.last_publish_at.isoformat() if account.last_publish_at else None,
        "status": account.status,
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "updated_at": account.updated_at.isoformat() if account.updated_at else None,
    }
