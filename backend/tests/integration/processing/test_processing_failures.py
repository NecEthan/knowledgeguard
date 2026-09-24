"""Retry and permanent failure tests."""

import pytest
from arq import Retry
from sqlalchemy import select
from unittest.mock import patch

from app.models.base import AuditEvent, DocumentVersion, ProcessingJob
from app.workers.main import process_document
from tests.helpers.processing import TXT_CONTENT, get_version, run_worker, upload_doc


async def test_process_document_retry_then_success(auth_client, db):
    """Transient failure on attempt 1 raises Retry; attempt 2 succeeds."""
    doc_id = await upload_doc(auth_client, "Retry Doc", TXT_CONTENT, "policy.txt")
    version = await get_version(db, doc_id)
    version_id = version.id

    with patch(
        "app.workers.main.storage.download_bytes",
        side_effect=RuntimeError("connection reset"),
    ):
        with pytest.raises(Retry):
            await process_document({"job_try": 1}, str(version_id))

    db.expire_all()
    result = await db.execute(
        select(ProcessingJob).where(ProcessingJob.document_version_id == version_id)
    )
    assert result.scalar_one().attempts == 1

    await run_worker(version_id, TXT_CONTENT, job_try=2)

    db.expire_all()
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == version_id)
    )
    assert result.scalar_one().status == "ACTIVE"

    result = await db.execute(
        select(ProcessingJob).where(ProcessingJob.document_version_id == version_id)
    )
    job = result.scalar_one()
    assert job.status == "COMPLETE"
    assert job.attempts == 2


async def test_process_document_permanent_failure(auth_client, db):
    """All 3 attempts fail → version=FAILED, job=FAILED, audit event emitted."""
    doc_id = await upload_doc(auth_client, "Permanent Failure Doc", TXT_CONTENT, "policy.txt")
    version = await get_version(db, doc_id)
    version_id = version.id

    error = RuntimeError("disk full")
    for attempt in (1, 2):
        with patch("app.workers.main.storage.download_bytes", side_effect=error):
            with pytest.raises(Retry):
                await process_document({"job_try": attempt}, str(version_id))

    with patch("app.workers.main.storage.download_bytes", side_effect=error):
        with pytest.raises(RuntimeError):
            await process_document({"job_try": 3}, str(version_id))

    db.expire_all()
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == version_id)
    )
    assert result.scalar_one().status == "FAILED"

    result = await db.execute(
        select(ProcessingJob).where(ProcessingJob.document_version_id == version_id)
    )
    job = result.scalar_one()
    assert job.status == "FAILED"
    assert "disk full" in job.last_error

    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.event_type == "PROCESSING_FAILED")
        .where(AuditEvent.document_id == doc_id)
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.version_id == version_id
