"""Fixtures for worker integration tests — reuses the same fixture modules as routers."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings


@pytest.fixture(autouse=True)
async def _worker_db_nullpool():
    """Patch AsyncSessionLocal in workers/main with a NullPool factory.

    The module-level engine in database.py uses asyncpg's default pool.
    Across function-scoped test event loops that pool can deliver connections
    already held by the test's db session, causing
    'another operation is in progress' errors.  NullPool creates a fresh
    connection per session call, matching what the db fixture already does.
    """
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    with patch("app.workers.main.AsyncSessionLocal", factory), \
         patch("app.workers.persistence.AsyncSessionLocal", factory):
        yield
    await engine.dispose()
