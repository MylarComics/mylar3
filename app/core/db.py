from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from app.core.config import settings

# Create async engine for Postgres connection pooling
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True
)

def run_alembic_migrations(connection):
    from sqlalchemy import inspect
    from alembic.config import Config
    from alembic import command
    from app.core.logger import logger

    inspector = inspect(connection)
    tables = inspector.get_table_names()

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.attributes['connection'] = connection

    if "comic" in tables and "alembic_version" not in tables:
        logger.info("[DB] Database exists but is not versioned by Alembic. Stamping with head.")
        command.stamp(alembic_cfg, "head")
    else:
        logger.info("[DB] Running database migrations...")
        command.upgrade(alembic_cfg, "head")

async def init_db():
    async with engine.begin() as conn:
        # Import models here so SQLModel metadata is registered
        try:
            from app.models.comic import Comic
            from app.models.issue import Issue
            from app.models.settings import SystemSettings
            from app.models.weekly import WeeklyPullList
            from app.models.failed_release import FailedRelease
        except ImportError:
            pass
        await conn.run_sync(run_alembic_migrations)

async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
