"""Idempotency and crash recovery tests."""

from unittest.mock import patch

from sqlalchemy import select

from app.models.base import DocumentChunk, DocumentVersion
from app.workers.main import process_document
from tests.helpers.processing import (
    FAKE_EMBEDDING,
    TXT_CONTENT,
    get_version,
    run_worker,
    upload_doc,
)


async def test_process_document_idempotency(auth_client, db):
    """Processing an already-ACTIVE version is a no-op; chunk count unchanged."""
    doc_id = await upload_doc(auth_client, "Idempotency Doc", TXT_CONTENT, "policy.txt")
    version = await get_version(db, doc_id)
    version_id = version.id

    await run_worker(version_id, TXT_CONTENT)

    db.expire_all()
    result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.document_version_id == version_id)
    )
    first_count = len(result.scalars().all())
    assert first_count > 0

    # Second run — early-exit because status=ACTIVE; download never called.
    with patch(
        "app.workers.main.storage.download_bytes", return_value=TXT_CONTENT
    ) as mock_dl:
        await process_document({}, str(version_id))
        mock_dl.assert_not_called()

    db.expire_all()
    result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.document_version_id == version_id)
    )
    assert len(result.scalars().all()) == first_count

    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc_id)
        .where(DocumentVersion.status == "ACTIVE")
    )
    assert len(result.scalars().all()) == 1


async def test_crash_recovery_no_duplicate_chunks(auth_client, db):
    """Stale chunks from a partial crash are replaced, not duplicated."""
    doc_id = await upload_doc(auth_client, "Crash Recovery Doc", TXT_CONTENT, "policy.txt")
    version = await get_version(db, doc_id)
    version_id = version.id

    # Simulate partial crash: insert 5 stale chunks.
    for i in range(5):
        db.add(
            DocumentChunk(
                document_version_id=version_id,
                chunk_index=i,
                content=f"stale chunk {i}",
                embedding=FAKE_EMBEDDING[:],
                token_count=3,
            )
        )
    await db.commit()

    await run_worker(version_id, TXT_CONTENT, job_try=2)

    db.expire_all()
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_version_id == version_id)
        .order_by(DocumentChunk.chunk_index)
    )
    chunks = result.scalars().all()
    assert [c for c in chunks if c.content.startswith("stale chunk")] == []
    assert len(chunks) > 0
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == version_id)
    )
    assert result.scalar_one().status == "ACTIVE"
