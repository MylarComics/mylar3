"""
Synchronous SQLModel engine for use inside Celery tasks.

Celery workers run in a standard synchronous execution context — the async
asyncpg engine used by the FastAPI web server cannot be shared across them.
This module provides a psycopg2-backed sync engine and a session context manager
that Celery tasks can safely import and use.

The DATABASE_URL is derived from settings by replacing the `asyncpg` driver
specifier with `psycopg2`, keeping all other connection parameters identical.
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

# Derive a synchronous postgres URL from the async one
_sync_url: str = settings.DATABASE_URL.replace(
    "postgresql+asyncpg", "postgresql+psycopg2"
).replace(
    "postgresql+asyncpg", "postgresql"  # fallback if prefix differs
)

sync_engine = create_engine(
    _sync_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

_SyncSession = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    """
    Context manager returning a synchronous SQLModel/SQLAlchemy session.
    Commits on clean exit, rolls back on any exception.

    Usage inside a Celery task:
        with get_sync_session() as session:
            issues = session.exec(select(Issue).where(...)).all()
    """
    session: Session = _SyncSession()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
