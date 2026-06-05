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

async def init_db():
    async with engine.begin() as conn:
        # Import models here so SQLModel metadata is registered
        # We will create these model files next
        try:
            from app.models.comic import Comic
            from app.models.issue import Issue
        except ImportError:
            pass
        await conn.run_sync(SQLModel.metadata.create_all)

async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
