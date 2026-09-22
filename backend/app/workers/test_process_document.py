"""Integration test for the document processing pipeline.

Uses real PostgreSQL. Mocks MinIO, OpenAI, and Redis.

Requires: docker compose up -d postgres
"""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.base import AuditEvent, DocumentChunk, DocumentVersion, ProcessingJob
from app.workers.main import process_document

_TXT_CONTENT = (
    b"Hello KnowledgeGuard. This is the first paragraph about company policies.\n\n"
    b"Second paragraph with more details about annual leave and expense procedures.\n\n"
    b"Third paragraph covering health and safety guidelines for all employees."
)
_FAKE_EMBEDDING = [0.1] * 1536


@pytest.fixture(autouse=True)
def _fake_embeddings():
    """Return a fake embedding for every text chunk passed to generate_embeddings."""

    async def _generate(texts):
        return [_FAKE_EMBEDDING[:] for _ in texts]

    with patch("app.workers.main.generate_embeddings", side_effect=_generate):
        yield


async def test_process_document_pipeline(auth_client, db):
    """Upload → worker processes → ACTIVE version, chunks, embeddings, FTS, audit."""

    # ── 1. Upload document ────────────────────────────────────────────────────
    with patch("app.services.storage.upload_bytes"):
        response = await auth_client.post(
            "/documents",
            files={"file": ("policy.txt", _TXT_CONTENT, "text/plain")},
            data={"title": "Company Policies"},
        )
    assert response.status_code == 202
    doc_id = uuid.UUID(response.json()["id"])

    # ── 2. Verify initial DB state ────────────────────────────────────────────
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == doc_id)
    )
    version = result.scalar_one()
    assert version.status == "PROCESSING"
    version_id = version.id

    result = await db.execute(
        select(ProcessingJob).where(ProcessingJob.document_version_id == version_id)
    )
    job = result.scalar_one()
    assert job.status in ("QUEUED", "DISPATCHED")

    # ── 3. Run worker directly (bypassing Redis) ──────────────────────────────
    with patch("app.workers.main.storage.download_bytes", return_value=_TXT_CONTENT):
        await process_document({}, str(version_id))

    # ── 4. Verify version is ACTIVE ───────────────────────────────────────────
    db.expire_all()
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == version_id)
    )
    version = result.scalar_one()
    assert version.status == "ACTIVE"

    # ── 5. Verify chunks exist with correct embeddings ────────────────────────
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

    # Chunk indices are sequential starting from 0.
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    # ── 6. Verify full-text search vector populated ───────────────────────────
    assert version.search_vector is not None

    # ── 7. Verify INDEX_UPDATED audit event ───────────────────────────────────
    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.event_type == "INDEX_UPDATED")
        .where(AuditEvent.document_id == doc_id)
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.version_id == version_id

    # ── 8. Verify processing job is COMPLETE ─────────────────────────────────
    result = await db.execute(
        select(ProcessingJob).where(ProcessingJob.document_version_id == version_id)
    )
    job = result.scalar_one()
    assert job.status == "COMPLETE"
    assert job.attempts == 1


async def test_process_document_previous_active_superseded(auth_client, db, test_user):
    """When a second version is processed, the first ACTIVE version is superseded."""

    # Upload and process first version.
    with patch("app.services.storage.upload_bytes"):
        r1 = await auth_client.post(
            "/documents",
            files={"file": ("v1.txt", b"Version one content.", "text/plain")},
            data={"title": "Doc"},
        )
    assert r1.status_code == 202
    doc_id = uuid.UUID(r1.json()["id"])

    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == doc_id)
    )
    v1 = result.scalar_one()

    v1_id = v1.id
    user_id = test_user.id
    with patch("app.workers.main.storage.download_bytes", return_value=b"Version one content."):
        await process_document({}, str(v1_id))

    db.expire_all()
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == v1_id)
    )
    v1 = result.scalar_one()
    assert v1.status == "ACTIVE"

    # Manually insert a second DocumentVersion to simulate a re-upload.
    from app.services.documents import compute_hash, generate_storage_key

    v2 = DocumentVersion(
        document_id=doc_id,
        version_number=2,
        status="PROCESSING",
        content_hash=compute_hash(b"Version two content."),
        storage_key=generate_storage_key(),
        created_by=user_id,
    )
    db.add(v2)
    await db.flush()

    job2 = ProcessingJob(document_version_id=v2.id, status="QUEUED")
    db.add(job2)
    await db.commit()
    v2_id = v2.id

    with patch("app.workers.main.storage.download_bytes", return_value=b"Version two content."):
        await process_document({}, str(v2_id))

    db.expire_all()

    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == v1_id)
    )
    v1_after = result.scalar_one()
    assert v1_after.status == "SUPERSEDED"

    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == v2_id)
    )
    v2_after = result.scalar_one()
    assert v2_after.status == "ACTIVE"


async def test_process_document_empty_file(auth_client, db):
    """An uploaded file with extractable but empty text still activates the version."""
    # Minimal text (single space) — chunker returns [].
    empty_content = b"   "

    with patch("app.services.storage.upload_bytes"):
        response = await auth_client.post(
            "/documents",
            files={"file": ("blank.txt", b"x", "text/plain")},  # must be non-empty to pass upload validation
            data={"title": "Blank Doc"},
        )
    assert response.status_code == 202
    doc_id = uuid.UUID(response.json()["id"])

    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == doc_id)
    )
    version = result.scalar_one()

    version_id = version.id
    # Worker receives effectively empty text.
    with patch("app.workers.main.storage.download_bytes", return_value=empty_content):
        await process_document({}, str(version_id))

    db.expire_all()
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == version_id)
    )
    version = result.scalar_one()
    assert version.status == "ACTIVE"

    result = await db.execute(
        select(DocumentChunk).where(DocumentChunk.document_version_id == version_id)
    )
    chunks = result.scalars().all()
    assert len(chunks) == 0
