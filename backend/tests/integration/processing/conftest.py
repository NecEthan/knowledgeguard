"""Fixtures for processing integration tests."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from tests.helpers.processing import FAKE_EMBEDDING


@pytest.fixture(autouse=True)
def _fake_embeddings():
    """Return a fake embedding for every chunk — avoids real OpenAI calls."""

    async def _generate(texts):
        return [FAKE_EMBEDDING[:] for _ in texts]

    with patch("app.workers.main.generate_embeddings", side_effect=_generate):
        yield


@pytest.fixture(autouse=True)
def _mock_storage_delete():
    """Prevent storage.delete_object from reaching MinIO in processing tests."""
    with patch("app.services.storage.delete_object"):
        yield


@pytest.fixture(autouse=True)
async def _worker_db_nullpool():
    """Patch AsyncSessionLocal in workers with a NullPool factory.

    Prevents 'another operation is in progress' errors when the worker's
    module-level pool delivers connections already held by the test's db session.
    """
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    with (
        patch("app.workers.main.AsyncSessionLocal", factory),
        patch("app.workers.persistence.AsyncSessionLocal", factory),
        patch("app.workers.failure.AsyncSessionLocal", factory),
    ):
        yield
    await engine.dispose()
