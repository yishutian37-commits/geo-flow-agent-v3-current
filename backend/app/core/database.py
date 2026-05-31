from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import get_settings

settings = get_settings()


def _is_sqlite_url(url: str) -> bool:
    return (url or "").lower().startswith("sqlite")


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()

# Async engine for FastAPI
# SQLite compat: check_same_thread=False for sync, future=True for both
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    future=True,
)

# Sync engine for Alembic / Celery / scripts
# Must point to the SAME database file as async_engine, just with sync driver
sync_db_url = (
    settings.DATABASE_URL
    .replace("+aiosqlite", "")
    .replace("+asyncpg", "+psycopg2")
)
sync_engine = create_engine(
    sync_db_url,
    echo=settings.DATABASE_ECHO,
    future=True,
    connect_args={"check_same_thread": False} if _is_sqlite_url(sync_db_url) else {},
)

if _is_sqlite_url(settings.DATABASE_URL):
    event.listen(async_engine.sync_engine, "connect", _enable_sqlite_foreign_keys)

if _is_sqlite_url(sync_db_url):
    event.listen(sync_engine, "connect", _enable_sqlite_foreign_keys)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
