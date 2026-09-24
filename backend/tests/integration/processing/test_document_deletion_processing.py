"""Tests for the document deletion race condition (KG-010).

Verifies that a worker processing a document version does not activate it
if the document was deleted mid-processing.

Race condition scenario (concurrent transactions):
  1. Worker Phase 1 commits (job=PROCESSING, version in memory).
  2. Worker Phase 4 opens transaction, flushes chunks (FK passes — DELETE not yet committed).
  3. DELETE endpoint commits (document + all children hard-deleted).
  4. Worker calls activate_version → document no longer exists → DocumentDeletedError.
  5. Worker transaction rolls back — chunks discarded, version never ACTIVE.
"""

import uuid

import pytest
from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.models.base import Document, DocumentChunk, DocumentVersion, ProcessingJob
from app.services.documents import compute_hash, generate_storage_key
from app.workers.activation import DocumentDeletedError, activate_version
from tests.helpers.processing import TXT_CONTENT, run_worker


async def _create_document(db, user_id: uuid.UUID) -> tuple[Document, DocumentVersion]:
    """Create Document + DocumentVersion (PROCESSING) + ProcessingJob (QUEUED)."""
    doc = Document(
        title="Race Condition Doc",
        owner_id=user_id,
        source_type="upload",
        sensitivity="STANDARD",
    )
    db.add(doc)
    await db.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        status="PROCESSING",
        content_hash=compute_hash(TXT_CONTENT),
        storage_key=generate_storage_key(),
        created_by=user_id,
    )
    db.add(version)
    await db.flush()

    db.add(ProcessingJob(document_version_id=version.id, status="QUEUED"))
    await db.commit()
    return doc, version


async def _hard_delete(db, doc_id: uuid.UUID, version_id: uuid.UUID) -> None:
    """Delete document and all children in FK order."""
    await db.execute(
        sa_delete(ProcessingJob).where(
            ProcessingJob.document_version_id == version_id
        )
    )
    await db.execute(sa_delete(DocumentVersion).where(DocumentVersion.id == version_id))
    await db.execute(sa_delete(Document).where(Document.id == doc_id))
    await db.commit()


async def test_activate_version_raises_when_document_does_not_exist(db, test_user):
    """activate_version raises DocumentDeletedError when the document row is gone."""
    doc, version = await _create_document(db, test_user.id)
    version_id = version.id
    doc_id = doc.id

    await _hard_delete(db, doc_id, version_id)

    with pytest.raises(DocumentDeletedError):
        await activate_version(db, version_id, doc_id)


async def test_worker_produces_no_chunks_when_document_deleted(db, test_user):
    """Worker leaves no committed chunks when document is hard-deleted.

    Simulates the scenario where DELETE ran before the worker even starts.
    Phase 1 fails cleanly (version not found) and no chunks are produced.
    """
    doc, version = await _create_document(db, test_user.id)
    version_id = version.id
    doc_id = doc.id

    await _hard_delete(db, doc_id, version_id)

    # Worker handles missing version gracefully — no crash, no chunks.
    await run_worker(version_id, TXT_CONTENT)

    db.expire_all()
    result = await db.execute(
        select(DocumentChunk).where(
            DocumentChunk.document_version_id == version_id
        )
    )
    assert result.scalars().all() == []
