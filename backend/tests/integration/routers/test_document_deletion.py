"""Integration tests for document deletion (KG-010).

Verifies that DELETE /documents/:id:
  - marks all versions DELETED
  - removes all DocumentChunks
  - cancels non-terminal ProcessingJobs
  - emits DOCUMENT_DELETED audit event
  - makes the document unreachable via all other endpoints
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from sqlalchemy import select, update

from app.models.base import (
    AuditEvent,
    Document,
    DocumentChunk,
    DocumentVersion,
    ProcessingJob,
)


def _txt_file(name: str = "test.txt") -> dict:
    return {"file": (name, b"Hello KnowledgeGuard", "text/plain")}


async def _upload(client, title: str = "Doc", sensitivity: str = "STANDARD") -> str:
    """Upload a document and return its id."""
    with (
        patch("app.services.storage.upload_bytes"),
        patch("app.services.storage.delete_object"),
    ):
        r = await client.post(
            "/documents",
            files=_txt_file(),
            data={"title": title, "sensitivity": sensitivity},
        )
    assert r.status_code == 202
    return r.json()["id"]


# ── Cascade effects ────────────────────────────────────────────────────────────


async def test_delete_removes_document(auth_client, db):
    doc_id = await _upload(auth_client)

    r = await auth_client.delete(f"/documents/{doc_id}")
    assert r.status_code == 204

    db.expire_all()
    result = await db.execute(
        select(Document).where(Document.id == uuid.UUID(doc_id))
    )
    assert result.scalar_one_or_none() is None


async def test_delete_removes_all_versions(auth_client, db):
    doc_id = await _upload(auth_client)

    r = await auth_client.delete(f"/documents/{doc_id}")
    assert r.status_code == 204

    db.expire_all()
    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == uuid.UUID(doc_id)
        )
    )
    assert result.scalars().all() == []


async def test_delete_removes_all_chunks(auth_client, db):
    doc_id = await _upload(auth_client)

    result = await db.execute(
        select(DocumentVersion.id).where(
            DocumentVersion.document_id == uuid.UUID(doc_id)
        )
    )
    version_id = result.scalar_one()

    # Insert a chunk so there is something to delete.
    db.add(
        DocumentChunk(
            document_version_id=version_id,
            chunk_index=0,
            content="Test chunk",
            embedding=[0.0] * 1536,
            token_count=3,
        )
    )
    await db.commit()

    r = await auth_client.delete(f"/documents/{doc_id}")
    assert r.status_code == 204

    db.expire_all()
    result = await db.execute(
        select(DocumentChunk).where(
            DocumentChunk.document_version_id == version_id
        )
    )
    assert result.scalars().all() == []


async def test_delete_removes_processing_jobs(auth_client, db):
    doc_id = await _upload(auth_client)

    result = await db.execute(
        select(DocumentVersion.id).where(
            DocumentVersion.document_id == uuid.UUID(doc_id)
        )
    )
    version_id = result.scalar_one()

    r = await auth_client.delete(f"/documents/{doc_id}")
    assert r.status_code == 204

    db.expire_all()
    result = await db.execute(
        select(ProcessingJob).where(
            ProcessingJob.document_version_id == version_id
        )
    )
    assert result.scalar_one_or_none() is None


async def test_delete_removes_completed_job(auth_client, db):
    doc_id = await _upload(auth_client)

    result = await db.execute(
        select(ProcessingJob.id)
        .join(DocumentVersion)
        .where(DocumentVersion.document_id == uuid.UUID(doc_id))
    )
    job_id = result.scalar_one()

    # Mark the job COMPLETE before deleting.
    await db.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .values(status="COMPLETE")
    )
    await db.commit()

    await auth_client.delete(f"/documents/{doc_id}")

    db.expire_all()
    result = await db.execute(
        select(ProcessingJob).where(ProcessingJob.id == job_id)
    )
    assert result.scalar_one_or_none() is None


async def test_delete_emits_audit_event(auth_client, db, test_user):
    doc_id = await _upload(auth_client)
    user_id = test_user.id  # capture before expire_all

    r = await auth_client.delete(f"/documents/{doc_id}")
    assert r.status_code == 204

    db.expire_all()
    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.document_id == uuid.UUID(doc_id))
        .where(AuditEvent.event_type == "DOCUMENT_DELETED")
    )
    event = result.scalar_one_or_none()
    assert event is not None
    assert event.user_id == user_id


# ── Endpoint visibility after deletion ────────────────────────────────────────


async def test_deleted_doc_not_in_list(auth_client):
    doc_id = await _upload(auth_client, title="ToHide")

    await auth_client.delete(f"/documents/{doc_id}")

    r = await auth_client.get("/documents")
    assert r.status_code == 200
    assert doc_id not in [d["id"] for d in r.json()]


async def test_deleted_doc_get_returns_404(auth_client):
    doc_id = await _upload(auth_client)
    await auth_client.delete(f"/documents/{doc_id}")

    r = await auth_client.get(f"/documents/{doc_id}")
    assert r.status_code == 404


async def test_deleted_doc_patch_returns_404(auth_client):
    doc_id = await _upload(auth_client)
    await auth_client.delete(f"/documents/{doc_id}")

    r = await auth_client.patch(f"/documents/{doc_id}", json={"title": "New"})
    assert r.status_code == 404


async def test_deleted_doc_second_delete_returns_404(auth_client):
    doc_id = await _upload(auth_client)
    await auth_client.delete(f"/documents/{doc_id}")

    r = await auth_client.delete(f"/documents/{doc_id}")
    assert r.status_code == 404


async def test_delete_unknown_doc_returns_404(auth_client):
    r = await auth_client.delete(f"/documents/{uuid.uuid4()}")
    assert r.status_code == 404


async def test_delete_requires_auth(client):
    r = await client.delete(f"/documents/{uuid.uuid4()}")
    assert r.status_code == 401


# ── Permission checks ──────────────────────────────────────────────────────────


async def test_user_cannot_delete_sensitive_doc(auth_client, admin_client):
    doc_id = await _upload(admin_client, sensitivity="SENSITIVE")

    # Non-admin cannot see (or delete) sensitive docs.
    r = await auth_client.delete(f"/documents/{doc_id}")
    assert r.status_code == 404


async def test_admin_can_delete_sensitive_doc(admin_client):
    doc_id = await _upload(admin_client, sensitivity="SENSITIVE")

    r = await admin_client.delete(f"/documents/{doc_id}")
    assert r.status_code == 204


# ── Multi-version document ─────────────────────────────────────────────────────


async def test_delete_removes_all_versions_and_chunks(auth_client, db):
    """Multiple versions: all marked DELETED, all chunks removed."""
    with (
        patch("app.services.storage.upload_bytes"),
        patch("app.services.storage.delete_object"),
    ):
        r = await auth_client.post(
            "/documents",
            files=_txt_file(),
            data={"title": "MultiVer", "sensitivity": "STANDARD"},
        )
        doc_id = r.json()["id"]

        # Upload a second version.
        r2 = await auth_client.post(
            f"/documents/{doc_id}/versions",
            files=_txt_file("v2.txt"),
        )
    assert r2.status_code == 202

    result = await db.execute(
        select(DocumentVersion.id).where(
            DocumentVersion.document_id == uuid.UUID(doc_id)
        )
    )
    version_ids = result.scalars().all()
    assert len(version_ids) == 2

    # Insert a chunk for each version.
    for vid in version_ids:
        db.add(
            DocumentChunk(
                document_version_id=vid,
                chunk_index=0,
                content="chunk",
                embedding=[0.0] * 1536,
                token_count=1,
            )
        )
    await db.commit()

    await auth_client.delete(f"/documents/{doc_id}")

    db.expire_all()
    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == uuid.UUID(doc_id)
        )
    )
    assert result.scalars().all() == []

    for vid in version_ids:
        result = await db.execute(
            select(DocumentChunk).where(
                DocumentChunk.document_version_id == vid
            )
        )
        assert result.scalars().all() == []
