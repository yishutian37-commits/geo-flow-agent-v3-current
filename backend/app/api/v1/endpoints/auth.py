from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import BootstrapAdminRequest, TokenOut, UserLogin, UserOut

router = APIRouter()


def _user_to_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


async def _token_for_user(user: User) -> TokenOut:
    settings = get_settings()
    token = create_access_token(
        {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        },
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenOut(access_token=token, user=_user_to_out(user))


@router.get("/bootstrap/status")
async def get_bootstrap_status(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(func.count(User.id)))
    user_count = int(result.scalar() or 0)
    return {
        "user_count": user_count,
        "needs_bootstrap": user_count == 0,
    }


@router.post("/bootstrap-admin", response_model=TokenOut)
async def bootstrap_admin(
    data: BootstrapAdminRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(func.count(User.id)))
    user_count = int(result.scalar() or 0)
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Admin bootstrap is only allowed before the first user is created",
        )

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name,
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return await _token_for_user(user)


@router.post("/login", response_model=TokenOut)
async def login(
    data: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(or_(User.username == data.username, User.email == data.username))
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")
    return await _token_for_user(user)


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    return _user_to_out(user)
