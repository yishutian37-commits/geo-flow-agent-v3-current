from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_roles
from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.user import User
from app.schemas.user import UserCreate, UserOut, UserPasswordUpdate, UserUpdate

router = APIRouter()

ROLE_OPTIONS = [
    {"value": "admin", "label": "系统管理员", "description": "管理用户、系统配置和全部项目"},
    {"value": "project_owner", "label": "项目负责人", "description": "管理项目、内容矩阵、审批和发布闭环"},
    {"value": "collector", "label": "资料采集员", "description": "维护语料、事实候选和资料缺口"},
    {"value": "strategist", "label": "策略规划师", "description": "生成问题库、内容矩阵和诊断策略"},
    {"value": "editor", "label": "内容编辑", "description": "生成、修改和校验内容草稿"},
    {"value": "compliance_reviewer", "label": "合规审核", "description": "审核事实、风险表达和发布前检查"},
    {"value": "publisher", "label": "发布执行", "description": "维护渠道账号和发布记录"},
    {"value": "monitor", "label": "监测分析", "description": "执行复测、样本录入和指标分析"},
    {"value": "client", "label": "客户/品牌方", "description": "确认品牌事实和客户复核"},
    {"value": "viewer", "label": "只读查看", "description": "查看项目数据，不执行关键写操作"},
]
VALID_ROLES = {item["value"] for item in ROLE_OPTIONS}


def _user_to_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


async def _get_user_or_404(db: AsyncSession, user_id: UUID) -> User:
    result = await db.execute(select(User).where(User.id == str(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def _ensure_unique_identity(
    db: AsyncSession,
    username: str | None = None,
    email: str | None = None,
    exclude_user_id: UUID | str | None = None,
) -> None:
    filters = []
    if username:
        filters.append(User.username == username)
    if email:
        filters.append(User.email == email)
    if not filters:
        return
    query = select(User).where(or_(*filters))
    if exclude_user_id:
        query = query.where(User.id != str(exclude_user_id))
    result = await db.execute(query)
    existing = result.scalar_one_or_none()
    if existing:
        field = "username" if username and existing.username == username else "email"
        raise HTTPException(status_code=409, detail=f"User {field} already exists")


async def _active_admin_count(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(User.id)).where(User.role == "admin", User.is_active == True)  # noqa: E712
    )
    return int(result.scalar() or 0)


def _validate_role(role: str | None) -> None:
    if role and role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role}")


async def _ensure_not_last_active_admin(db: AsyncSession, user: User, update_data: dict) -> None:
    if user.role != "admin" or not user.is_active:
        return
    role_after = update_data.get("role", user.role)
    active_after = update_data.get("is_active", user.is_active)
    if role_after == "admin" and active_after:
        return
    if await _active_admin_count(db) <= 1:
        raise HTTPException(status_code=400, detail="At least one active admin must remain")


@router.get("/roles")
async def list_roles(current_user: User = Depends(require_roles("admin"))):
    return {"roles": ROLE_OPTIONS}


@router.get("", response_model=list[UserOut])
async def list_users(
    role: str | None = Query(None),
    is_active: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    query = select(User)
    if role:
        _validate_role(role)
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    query = query.order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return [_user_to_out(user) for user in result.scalars().all()]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    _validate_role(data.role)
    await _ensure_unique_identity(db, username=data.username, email=str(data.email))
    user = User(
        username=data.username,
        email=str(data.email),
        full_name=data.full_name,
        role=data.role,
        is_active=data.is_active,
        hashed_password=get_password_hash(data.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _user_to_out(user)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    return _user_to_out(await _get_user_or_404(db, user_id))


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    user = await _get_user_or_404(db, user_id)
    update_data = data.model_dump(exclude_unset=True)
    _validate_role(update_data.get("role"))
    await _ensure_not_last_active_admin(db, user, update_data)
    if "email" in update_data and update_data["email"]:
        await _ensure_unique_identity(db, email=str(update_data["email"]), exclude_user_id=user.id)
        update_data["email"] = str(update_data["email"])
    for field, value in update_data.items():
        setattr(user, field, value)
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return _user_to_out(user)


@router.post("/{user_id}/reset-password", response_model=UserOut)
async def reset_user_password(
    user_id: UUID,
    data: UserPasswordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    user = await _get_user_or_404(db, user_id)
    user.hashed_password = get_password_hash(data.password)
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return _user_to_out(user)


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Role 'admin' is required for this operation")
    if str(current_user.id) == str(user_id):
        raise HTTPException(status_code=400, detail="Current user cannot deactivate itself")
    user = await _get_user_or_404(db, user_id)
    await _ensure_not_last_active_admin(db, user, {"is_active": False})
    user.is_active = False
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "User deactivated", "id": str(user_id)}
