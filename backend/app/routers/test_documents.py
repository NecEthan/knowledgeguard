"""Integration tests for the documents router.

Fixtures are in fixtures/. Requires postgres (docker compose up -d postgres).
MinIO and Redis are mocked — no external services needed beyond the DB.
"""

import uuid
from unittest.mock import patch

from sqlalchemy import select

from app.models.base import Document, DocumentVersion, ProcessingJob


def _txt_file(name: str = "test.txt") -> dict:
    return {"file": (name, b"Hello KnowledgeGuard", "text/plain")}


async def test_upload_requires_auth(client):
    response = await client.post(
        "/documents", files=_txt_file(), data={"title": "Doc"}
    )
    assert response.status_code == 401


async def test_upload_unsupported_file_type(auth_client):
    response = await auth_client.post(
        "/documents",
        files={"file": ("evil.exe", b"\x4d\x5a\x00\x00", "application/octet-stream")},
        data={"title": "Bad file"},
    )
    assert response.status_code == 415


async def test_upload_creates_db_records(auth_client, db, test_user):
    with patch("app.services.storage.upload_bytes"), patch(
        "app.services.storage.delete_object"
    ):
        response = await auth_client.post(
            "/documents",
            files=_txt_file(),
            data={"title": "My Doc"},
        )

    assert response.status_code == 202
    doc_id = response.json()["id"]

    result = await db.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
    doc = result.scalar_one_or_none()
    assert doc is not None
    assert doc.title == "My Doc"
    assert doc.owner_id == test_user.id

    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
    )
    version = result.scalar_one_or_none()
    assert version is not None
    assert version.status == "PROCESSING"

    result = await db.execute(
        select(ProcessingJob).where(ProcessingJob.document_version_id == version.id)
    )
    job = result.scalar_one_or_none()
    assert job is not None
    assert job.status in ("QUEUED", "DISPATCHED")


async def test_upload_enqueues_job(auth_client, mock_pool):
    with patch("app.services.storage.upload_bytes"), patch(
        "app.services.storage.delete_object"
    ):
        response = await auth_client.post(
            "/documents",
            files=_txt_file(),
            data={"title": "Enqueue test"},
        )

    assert response.status_code == 202
    mock_pool.enqueue_job.assert_called_once()
    assert mock_pool.enqueue_job.call_args.args[0] == "process_document"


async def test_list_documents(auth_client):
    with patch("app.services.storage.upload_bytes"), patch(
        "app.services.storage.delete_object"
    ):
        await auth_client.post(
            "/documents",
            files=_txt_file(),
            data={"title": "Listed Doc"},
        )

    response = await auth_client.get("/documents")
    assert response.status_code == 200
    titles = [d["title"] for d in response.json()]
    assert "Listed Doc" in titles


async def test_delete_document(auth_client, db):
    with patch("app.services.storage.upload_bytes"), patch(
        "app.services.storage.delete_object"
    ):
        upload = await auth_client.post(
            "/documents",
            files=_txt_file(),
            data={"title": "To Delete"},
        )
    doc_id = upload.json()["id"]

    response = await auth_client.delete(f"/documents/{doc_id}")
    assert response.status_code == 204

    db.expire_all()
    result = await db.execute(
        select(Document).where(Document.id == uuid.UUID(doc_id))
    )
    doc = result.scalar_one_or_none()
    assert doc is not None
    assert doc.deleted_at is not None
