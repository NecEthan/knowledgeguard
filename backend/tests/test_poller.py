"""Unit tests for app/poller.py.

Verifies _dispatch_stale_jobs passes the deterministic _job_id so ARQ
deduplication prevents double-enqueue when the poller retries a job that
was already enqueued but whose status was never updated to DISPATCHED.
"""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.poller import _dispatch_stale_jobs


def _make_job(document_version_id: uuid.UUID | None = None) -> MagicMock:
    job = MagicMock()
    job.document_version_id = document_version_id or uuid.uuid4()
    job.status = "QUEUED"
    return job


@pytest.fixture
def mock_arq_pool():
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    return pool


async def test_dispatch_uses_deterministic_job_id(mock_arq_pool):
    """enqueue_job must receive _job_id=f'process_document:{version_id}'."""
    version_id = uuid.uuid4()
    job = _make_job(version_id)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [job]))
    )
    mock_db.commit = AsyncMock()

    @asynccontextmanager
    async def fake_session():
        yield mock_db

    with patch("app.poller.AsyncSessionLocal", fake_session):
        await _dispatch_stale_jobs(mock_arq_pool)

    mock_arq_pool.enqueue_job.assert_called_once_with(
        "process_document",
        str(version_id),
        _job_id=f"process_document:{version_id}",
    )


async def test_dispatch_marks_job_dispatched(mock_arq_pool):
    """Job status set to DISPATCHED after successful enqueue."""
    job = _make_job()

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [job]))
    )
    mock_db.commit = AsyncMock()

    @asynccontextmanager
    async def fake_session():
        yield mock_db

    with patch("app.poller.AsyncSessionLocal", fake_session):
        await _dispatch_stale_jobs(mock_arq_pool)

    assert job.status == "DISPATCHED"
    mock_db.commit.assert_called_once()


async def test_dispatch_no_jobs_skips_enqueue(mock_arq_pool):
    """No QUEUED jobs — enqueue_job never called, no commit."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: []))
    )
    mock_db.commit = AsyncMock()

    @asynccontextmanager
    async def fake_session():
        yield mock_db

    with patch("app.poller.AsyncSessionLocal", fake_session):
        await _dispatch_stale_jobs(mock_arq_pool)

    mock_arq_pool.enqueue_job.assert_not_called()
    mock_db.commit.assert_not_called()


async def test_dispatch_multiple_jobs_each_get_unique_job_id(mock_arq_pool):
    """Each job enqueued with its own deterministic _job_id."""
    version_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    jobs = [_make_job(vid) for vid in version_ids]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: jobs))
    )
    mock_db.commit = AsyncMock()

    @asynccontextmanager
    async def fake_session():
        yield mock_db

    with patch("app.poller.AsyncSessionLocal", fake_session):
        await _dispatch_stale_jobs(mock_arq_pool)

    assert mock_arq_pool.enqueue_job.call_count == 3
    calls = mock_arq_pool.enqueue_job.call_args_list
    for i, vid in enumerate(version_ids):
        assert calls[i].kwargs["_job_id"] == f"process_document:{vid}"
