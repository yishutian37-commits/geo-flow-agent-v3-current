from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_, select, text
from sqlalchemy.sql.schema import Column
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, async_engine, Base
from app.core.security import get_password_hash
from app.api.v1.router import api_router
from app.llm.registry import get_model_registry
from app.models.user import User

settings = get_settings()


def _email_uses_reserved_local_domain(email: str | None) -> bool:
    if not email or "@" not in email:
        return False
    domain = email.rsplit("@", 1)[-1].lower()
    return domain == "local" or domain.endswith(".local")


def _replacement_email_for_reserved_local(
    email: str,
    username: str | None = None,
    user_id: str | None = None,
    occupied_emails: set[str] | None = None,
) -> str:
    local_part, domain = email.rsplit("@", 1)
    domain_lower = domain.lower()
    if domain_lower.endswith(".local"):
        new_domain = domain[: -len(".local")] + ".app"
    else:
        new_domain = "local.app"

    occupied = occupied_emails or set()
    candidate = f"{local_part}@{new_domain}"
    if candidate.lower() not in occupied:
        return candidate

    safe_name = (username or local_part or "user").lower().replace("@", ".").replace(" ", ".")
    candidate = f"{safe_name}@geoflow.app"
    if candidate.lower() not in occupied:
        return candidate

    suffix = (str(user_id)[:8] if user_id else "account").lower()
    return f"{safe_name}.{suffix}@geoflow.app"


DEFAULT_PROJECT_OWNER_USERNAME = os.getenv("GEO_DEFAULT_PROJECT_OWNER_USERNAME", "pm01")
_RAW_DEFAULT_PROJECT_OWNER_EMAIL = os.getenv("GEO_DEFAULT_PROJECT_OWNER_EMAIL", "pm01@geoflow.app")
DEFAULT_PROJECT_OWNER_EMAIL = (
    _replacement_email_for_reserved_local(_RAW_DEFAULT_PROJECT_OWNER_EMAIL, DEFAULT_PROJECT_OWNER_USERNAME)
    if _email_uses_reserved_local_domain(_RAW_DEFAULT_PROJECT_OWNER_EMAIL)
    else _RAW_DEFAULT_PROJECT_OWNER_EMAIL
)
DEFAULT_PROJECT_OWNER_PASSWORD = os.getenv("GEO_DEFAULT_PROJECT_OWNER_PASSWORD", "Pm@20260529")
DEFAULT_PROJECT_OWNER_FULL_NAME = os.getenv("GEO_DEFAULT_PROJECT_OWNER_FULL_NAME", "项目负责人")


def _quote_sqlite_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sqlite_literal(value) -> str | None:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def _sqlite_column_definition(column: Column, dialect) -> str | None:
    if column.primary_key:
        return None
    try:
        column_type = column.type.compile(dialect=dialect)
    except Exception:
        column_type = "TEXT"

    parts = [_quote_sqlite_identifier(column.name), column_type]
    default_value = None
    if column.default is not None and not column.default.is_callable and not column.default.is_sequence:
        default_value = _sqlite_literal(column.default.arg)
    if default_value is not None:
        parts.append(f"DEFAULT {default_value}")
    if not column.nullable and default_value is not None:
        parts.append("NOT NULL")
    return " ".join(parts)


async def ensure_sqlite_model_columns(conn) -> None:
    """Add missing SQLite columns from SQLAlchemy models for older desktop databases."""
    tables = (await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))).fetchall()
    existing_tables = {row[0] for row in tables}
    dialect = conn.dialect

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        columns = (await conn.execute(text(f"PRAGMA table_info({_sqlite_literal(table.name)})"))).fetchall()
        existing_columns = {row[1] for row in columns}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            definition = _sqlite_column_definition(column, dialect)
            if not definition:
                continue
            await conn.execute(
                text(
                    f"ALTER TABLE {_quote_sqlite_identifier(table.name)} "
                    f"ADD COLUMN {definition}"
                )
            )
            existing_columns.add(column.name)


async def ensure_runtime_schema(conn):
    """Small SQLite migrations for desktop/dev databases created before model updates."""
    if "sqlite" not in settings.DATABASE_URL.lower():
        return
    tables = (await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))).fetchall()
    table_names = {row[0] for row in tables}
    if "publish_records" in table_names:
        columns = (await conn.execute(text("PRAGMA table_info(publish_records)"))).fetchall()
        column_names = {row[1] for row in columns}
        if "draft_id" not in column_names:
            await conn.execute(text("ALTER TABLE publish_records ADD COLUMN draft_id VARCHAR(36)"))
        if "draft_version" not in column_names:
            await conn.execute(text("ALTER TABLE publish_records ADD COLUMN draft_version VARCHAR(20)"))
    if "model_targets" in table_names:
        columns = (await conn.execute(text("PRAGMA table_info(model_targets)"))).fetchall()
        column_names = {row[1] for row in columns}
        for column_name, column_type in [
            ("web_url", "VARCHAR(1000)"),
            ("input_selector", "VARCHAR(500)"),
            ("submit_selector", "VARCHAR(500)"),
            ("response_selector", "VARCHAR(500)"),
            ("recognition_mode", "VARCHAR(50) NOT NULL DEFAULT 'text'"),
        ]:
            if column_name not in column_names:
                await conn.execute(text(f"ALTER TABLE model_targets ADD COLUMN {column_name} {column_type}"))
    if "channel_accounts" in table_names:
        columns = (await conn.execute(text("PRAGMA table_info(channel_accounts)"))).fetchall()
        column_names = {row[1] for row in columns}
        for column_name, column_type in [
            ("publisher_url", "VARCHAR(1000)"),
            ("title_selector", "VARCHAR(500)"),
            ("body_selector", "VARCHAR(500)"),
        ]:
            if column_name not in column_names:
                await conn.execute(text(f"ALTER TABLE channel_accounts ADD COLUMN {column_name} {column_type}"))
    if "monitoring_samples" in table_names:
        columns = (await conn.execute(text("PRAGMA table_info(monitoring_samples)"))).fetchall()
        column_names = {row[1] for row in columns}
        if "sources_json" not in column_names:
            await conn.execute(text("ALTER TABLE monitoring_samples ADD COLUMN sources_json TEXT"))
        if "analysis_json" not in column_names:
            await conn.execute(text("ALTER TABLE monitoring_samples ADD COLUMN analysis_json TEXT"))
    if "questions" in table_names:
        columns = (await conn.execute(text("PRAGMA table_info(questions)"))).fetchall()
        column_names = {row[1] for row in columns}
        for column_name, column_type in [
            ("question_type", "VARCHAR(100) NOT NULL DEFAULT 'brand_reputation'"),
            ("tags", "TEXT"),
            ("enabled", "BOOLEAN NOT NULL DEFAULT 1"),
            ("focus", "BOOLEAN NOT NULL DEFAULT 0"),
        ]:
            if column_name not in column_names:
                await conn.execute(text(f"ALTER TABLE questions ADD COLUMN {column_name} {column_type}"))
    await ensure_sqlite_model_columns(conn)


async def repair_reserved_local_user_emails(db: AsyncSession) -> int:
    """Repair old seeded `.local` user emails that strict EmailStr refuses to serialize."""
    result = await db.execute(select(User))
    users = list(result.scalars().all())
    occupied = {str(user.email).lower(): str(user.id) for user in users if user.email}
    changed = 0
    now = datetime.now(timezone.utc)

    for user in users:
        current_email = str(user.email or "")
        if not _email_uses_reserved_local_domain(current_email):
            continue

        occupied.pop(current_email.lower(), None)
        new_email = _replacement_email_for_reserved_local(
            current_email,
            username=user.username,
            user_id=str(user.id),
            occupied_emails=set(occupied.keys()),
        )
        user.email = new_email
        user.updated_at = now
        occupied[new_email.lower()] = str(user.id)
        changed += 1

    if changed:
        await db.commit()
        print(f"[Auth] Repaired {changed} reserved .local user email(s)")
    return changed


async def ensure_default_project_owner() -> None:
    """Ensure shared/local desktop installs have a ready project-owner login."""
    if not DEFAULT_PROJECT_OWNER_USERNAME or not DEFAULT_PROJECT_OWNER_PASSWORD:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(
                or_(
                    User.username == DEFAULT_PROJECT_OWNER_USERNAME,
                    User.email == DEFAULT_PROJECT_OWNER_EMAIL,
                )
            )
        )
        user = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if user:
            changed = False
            updates = {
                "username": DEFAULT_PROJECT_OWNER_USERNAME,
                "email": DEFAULT_PROJECT_OWNER_EMAIL,
                "full_name": DEFAULT_PROJECT_OWNER_FULL_NAME,
                "role": "project_owner",
                "is_active": True,
            }
            for field, value in updates.items():
                if getattr(user, field) != value:
                    setattr(user, field, value)
                    changed = True
            if changed:
                user.updated_at = now
                await db.commit()
                print(f"[Auth] Updated default project owner: {DEFAULT_PROJECT_OWNER_USERNAME}")
            return

        db.add(
            User(
                id=str(uuid.uuid4()),
                username=DEFAULT_PROJECT_OWNER_USERNAME,
                email=DEFAULT_PROJECT_OWNER_EMAIL,
                hashed_password=get_password_hash(DEFAULT_PROJECT_OWNER_PASSWORD),
                full_name=DEFAULT_PROJECT_OWNER_FULL_NAME,
                role="project_owner",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        await db.commit()
        print(f"[Auth] Created default project owner: {DEFAULT_PROJECT_OWNER_USERNAME}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db_url = settings.DATABASE_URL
    db_type = "SQLite" if "sqlite" in db_url.lower() else "PostgreSQL" if "postgres" in db_url.lower() else "Unknown"
    print(f"[DB] Using {db_type} database")
    if settings.ENVIRONMENT == "production" and db_type == "SQLite":
        print("[WARNING] Running production environment with SQLite is not recommended!")

    if settings.ENVIRONMENT == "development":
        async with async_engine.begin() as conn:
            # Create tables if they don't exist (dev only; use Alembic in production)
            await conn.run_sync(Base.metadata.create_all)
            await ensure_runtime_schema(conn)
            print("[DB] Auto-created tables (development mode)")
        async with AsyncSessionLocal() as db:
            await repair_reserved_local_user_emails(db)
        await ensure_default_project_owner()
    else:
        print("[DB] Skipping auto-create tables in production (use Alembic)")
    
    # Initialize LLM model registry
    registry = get_model_registry()
    print(f"[LLM] Loaded {len(registry.list_models(active_only=False))} models (presets + saved)")
    
    yield
    # Shutdown
    await async_engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ALLOW_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求参数验证错误"""
    return JSONResponse(
        status_code=422,
        content={
            "detail": "请求参数校验失败",
            "errors": exc.errors(),
            "body": exc.body if hasattr(exc, "body") else None,
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    """处理数据库错误"""
    error_msg = str(exc)
    # 生产环境不暴露详细SQL错误
    if not settings.DEBUG:
        error_msg = "数据库操作失败，请稍后重试"
    return JSONResponse(
        status_code=500,
        content={
            "detail": "数据库错误",
            "error": error_msg,
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """处理业务逻辑ValueError"""
    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """处理所有未捕获的异常"""
    import traceback
    error_msg = str(exc)
    stack_trace = traceback.format_exc()
    print(f"[ERROR] Unhandled exception: {error_msg}\n{stack_trace}")
    
    if not settings.DEBUG:
        error_msg = "服务器内部错误"
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": error_msg,
            "type": type(exc).__name__,
            "stack": stack_trace if settings.DEBUG else None,
        },
    )


# API Routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    """健康检查"""
    # 简单检查数据库连接
    try:
        from sqlalchemy import text
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "database": db_status,
        "debug": settings.DEBUG,
    }
