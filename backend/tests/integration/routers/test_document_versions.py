"""Integration tests for the document versions router.

Tests POST/GET /documents/:id/versions and GET /documents/:id/versions/:vid.
Requires postgres running. MinIO and Redis are mocked.
"""

import uuid
from unittest.mock import patch

from sqlalchemy import select

from app.models.base import AuditEvent, DocumentVersion, ProcessingJob


def _txt_file(name: str = "v2.txt") -> dict:
    return {"file": (name, b"Version two content", "text/plain")}


async def _upload_doc(auth_client) -> str:
    """Upload a first document and return its id."""
    with patch("app.services.storage.upload_bytes"):
        response = await auth_client.post(
            "/documents",
            files={"file": ("v1.txt", b"Version one content", "text/plain")},
            data={"title": "Versioned Doc", "sensitivity": "STANDARD"},
        )
    assert response.status_code == 202
    return response.json()["id"]


async def test_upload_version_requires_auth(client):
    doc_id = uuid.uuid4()
    response = await client.post(f"/documents/{doc_id}/versions", files=_txt_file())
    assert response.status_code == 401


async def test_upload_version_not_found(auth_client):
    with patch("app.services.storage.upload_bytes"):
        response = await auth_client.post(
            f"/documents/{uuid.uuid4()}/versions",
            files=_txt_file(),
        )
    assert response.status_code == 404


async def test_upload_new_version_creates_db_records(auth_client, db, test_user):
    doc_id = await _upload_doc(auth_client)

    with (
        patch("app.services.storage.upload_bytes"),
        patch("app.services.storage.delete_object"),
    ):
        response = await auth_client.post(
            f"/documents/{doc_id}/versions",
            files=_txt_file(),
        )

    assert response.status_code == 202
    data = response.json()
    assert data["document_id"] == doc_id
    assert data["version_number"] == 2
    assert data["status"] == "accepted"

    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == uuid.UUID(doc_id))
        .where(DocumentVersion.version_number == 2)
    )
    v2 = result.scalar_one_or_none()
    assert v2 is not None
    assert v2.status == "PROCESSING"

    result = await db.execute(
        select(ProcessingJob).where(ProcessingJob.document_version_id == v2.id)
    )
    job = result.scalar_one_or_none()
    assert job is not None
    assert job.status in ("QUEUED", "DISPATCHED")


async def test_upload_new_version_increments_version_number(auth_client, db, test_user):
    doc_id = await _upload_doc(auth_client)

    with (
        patch("app.services.storage.upload_bytes"),
        patch("app.services.storage.delete_object"),
    ):
        r2 = await auth_client.post(f"/documents/{doc_id}/versions", files=_txt_file())
        r3 = await auth_client.post(f"/documents/{doc_id}/versions", files=_txt_file())

    assert r2.json()["version_number"] == 2
    assert r3.json()["version_number"] == 3


async def test_upload_new_version_emits_version_created_audit(
    auth_client, db, test_user
):
    doc_id = await _upload_doc(auth_client)

    with (
        patch("app.services.storage.upload_bytes"),
        patch("app.services.storage.delete_object"),
    ):
        response = await auth_client.post(
            f"/documents/{doc_id}/versions",
            files=_txt_file(),
        )
    assert response.status_code == 202
    version_id = response.json()["id"]

    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.event_type == "VERSION_CREATED")
        .where(AuditEvent.document_id == uuid.UUID(doc_id))
        .where(AuditEvent.version_id == uuid.UUID(version_id))
    )
    assert result.scalar_one_or_none() is not None


async def test_list_versions_requires_auth(client):
    doc_id = uuid.uuid4()
    response = await client.get(f"/documents/{doc_id}/versions")
    assert response.status_code == 401


async def test_list_versions_not_found(auth_client):
    response = await auth_client.get(f"/documents/{uuid.uuid4()}/versions")
    assert response.status_code == 404


async def test_list_versions(auth_client, db, test_user):
    doc_id = await _upload_doc(auth_client)

    with (
        patch("app.services.storage.upload_bytes"),
        patch("app.services.storage.delete_object"),
    ):
        await auth_client.post(f"/documents/{doc_id}/versions", files=_txt_file())

    response = await auth_client.get(f"/documents/{doc_id}/versions")
    assert response.status_code == 200
    versions = response.json()
    assert len(versions) == 2
    # ordered newest first
    assert versions[0]["version_number"] == 2
    assert versions[1]["version_number"] == 1
    assert versions[0]["document_id"] == doc_id


async def test_get_version_requires_auth(client):
    response = await client.get(f"/documents/{uuid.uuid4()}/versions/{uuid.uuid4()}")
    assert response.status_code == 401


async def test_get_version(auth_client, db, test_user):
    doc_id = await _upload_doc(auth_client)

    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == uuid.UUID(doc_id))
    )
    v1 = result.scalar_one()

    response = await auth_client.get(f"/documents/{doc_id}/versions/{v1.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["version_number"] == 1
    assert data["id"] == str(v1.id)
    assert data["document_id"] == doc_id


async def test_get_version_not_found(auth_client):
    # Document doesn't exist → 404
    response = await auth_client.get(
        f"/documents/{uuid.uuid4()}/versions/{uuid.uuid4()}"
    )
    assert response.status_code == 404


async def test_get_version_wrong_document(auth_client, db, test_user):
    """Version ID exists but belongs to a different document → 404."""
    doc_id = await _upload_doc(auth_client)
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == uuid.UUID(doc_id))
    )
    v1 = result.scalar_one()

    other_doc_id = uuid.uuid4()
    response = await auth_client.get(f"/documents/{other_doc_id}/versions/{v1.id}")
    assert response.status_code == 404
