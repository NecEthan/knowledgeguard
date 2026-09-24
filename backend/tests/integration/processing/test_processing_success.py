"""Happy-path processing tests.

Covers: full pipeline, empty-file edge case.
"""

from sqlalchemy import select

from app.models.base import AuditEvent, DocumentChunk, DocumentVersion, ProcessingJob
from tests.helpers.processing import TXT_CONTENT, get_version, run_worker, upload_doc


async def test_process_document_pipeline(auth_client, db):
    """Upload → worker processes → ACTIVE version, chunks, embeddings, FTS, audit."""

    doc_id = await upload_doc(auth_client, "Company Policies", TXT_CONTENT, "policy.txt")
    version = await get_version(db, doc_id)
    assert version.status == "PROCESSING"
    version_id = version.id

    result = await db.execute(
        select(ProcessingJob).where(ProcessingJob.document_version_id == version_id)
    )
    job = result.scalar_one()
    assert job.status in ("QUEUED", "DISPATCHED")

    await run_worker(version_id, TXT_CONTENT)

    db.expire_all()
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == version_id)
    )
    version = result.scalar_one()
    assert version.status == "ACTIVE"

    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_version_id == version_id)
        .order_by(DocumentChunk.chunk_index)
    )
    chunks = result.scalars().all()
    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk.embedding is not None
        assert len(chunk.embedding) == 1536
        assert chunk.token_count > 0
        assert chunk.content.strip()
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    assert version.search_vector is not None

    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.event_type == "INDEX_UPDATED")
        .where(AuditEvent.document_id == doc_id)
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.version_id == version_id

    result = await db.execute(
        select(ProcessingJob).where(ProcessingJob.document_version_id == version_id)
    )
    job = result.scalar_one()
    assert job.status == "COMPLETE"
    assert job.attempts == 1


async def test_process_document_empty_file(auth_client, db):
    """Extractable but empty text still activates the version with zero chunks."""
    doc_id = await upload_doc(auth_client, "Blank Doc", b"x", "blank.txt")
    version = await get_version(db, doc_id)
    version_id = version.id

    await run_worker(version_id, b"   ")

    db.expire_all()
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == version_id)
    )
    assert result.scalar_one().status == "ACTIVE"

    result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.document_version_id == version_id)
    )
    assert len(result.scalars().all()) == 0
