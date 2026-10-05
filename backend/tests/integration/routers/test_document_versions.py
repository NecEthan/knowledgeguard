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


# ---------------------------------------------------------------------------
# Activate endpoint helpers
# ---------------------------------------------------------------------------


async def _upload_and_setup_versions(auth_client, db):
    """Upload two versions and manually set v1=ACTIVE, v2=SUPERSEDED.

    Returns (doc_id_str, v1_id, v2_id).
    """
    doc_id = await _upload_doc(auth_client)

    with (
        patch("app.services.storage.upload_bytes"),
        patch("app.services.storage.delete_object"),
    ):
        r2 = await auth_client.post(
            f"/documents/{doc_id}/versions",
            files=_txt_file("v2.txt"),
        )
    assert r2.status_code == 202
    v2_id = uuid.UUID(r2.json()["id"])

    # Fetch both versions.
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == uuid.UUID(doc_id))
        .order_by(DocumentVersion.version_number)
    )
    versions = result.scalars().all()
    v1, v2 = versions[0], versions[1]

    # Simulate post-processing state: v1 ACTIVE, v2 SUPERSEDED.
    from sqlalchemy import update as sa_update

    await db.execute(
        sa_update(DocumentVersion)
        .where(DocumentVersion.id == v1.id)
        .values(status="ACTIVE")
    )
    await db.execute(
        sa_update(DocumentVersion)
        .where(DocumentVersion.id == v2.id)
        .values(status="SUPERSEDED")
    )
    await db.commit()

    return doc_id, v1.id, v2_id


# ---------------------------------------------------------------------------
# Activate endpoint tests
# ---------------------------------------------------------------------------


async def test_activate_superseded_version(auth_client, db, test_user):
    doc_id, v1_id, v2_id = await _upload_and_setup_versions(auth_client, db)

    # v2 is SUPERSEDED — activate it.
    response = await auth_client.patch(
        f"/documents/{doc_id}/versions/{v2_id}/activate"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ACTIVE"
    assert data["id"] == str(v2_id)


async def test_previous_active_becomes_superseded(auth_client, db, test_user):
    doc_id, v1_id, v2_id = await _upload_and_setup_versions(auth_client, db)

    await auth_client.patch(f"/documents/{doc_id}/versions/{v2_id}/activate")

    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == v1_id)
    )
    await db.refresh(result.scalar_one())
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == v1_id)
    )
    v1 = result.scalar_one()
    assert v1.status == "SUPERSEDED"


async def test_activate_emits_audit_events(auth_client, db, test_user):
    doc_id, v1_id, v2_id = await _upload_and_setup_versions(auth_client, db)

    await auth_client.patch(f"/documents/{doc_id}/versions/{v2_id}/activate")

    activated = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.event_type == "VERSION_ACTIVATED")
        .where(AuditEvent.document_id == uuid.UUID(doc_id))
        .where(AuditEvent.version_id == v2_id)
    )
    assert activated.scalar_one_or_none() is not None

    superseded = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.event_type == "VERSION_SUPERSEDED")
        .where(AuditEvent.document_id == uuid.UUID(doc_id))
        .where(AuditEvent.version_id == v1_id)
    )
    assert superseded.scalar_one_or_none() is not None


async def test_activate_requires_auth(client):
    response = await client.patch(
        f"/documents/{uuid.uuid4()}/versions/{uuid.uuid4()}/activate"
    )
    assert response.status_code == 401


async def test_activate_403_wrong_owner(auth_client, admin_client, db, test_user, admin_user):
    """Admin uploads doc; regular user cannot activate its versions."""
    with patch("app.services.storage.upload_bytes"):
        r = await admin_client.post(
            "/documents",
            files={"file": ("doc.txt", b"admin doc", "text/plain")},
            data={"title": "Admin Doc", "sensitivity": "STANDARD"},
        )
    assert r.status_code == 202
    doc_id = r.json()["id"]

    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == uuid.UUID(doc_id))
    )
    v1 = result.scalar_one()

    response = await auth_client.patch(
        f"/documents/{doc_id}/versions/{v1.id}/activate"
    )
    assert response.status_code == 403


async def test_activate_404_document_not_found(auth_client, test_user):
    response = await auth_client.patch(
        f"/documents/{uuid.uuid4()}/versions/{uuid.uuid4()}/activate"
    )
    assert response.status_code == 404


async def test_activate_404_version_not_found(auth_client, db, test_user):
    doc_id = await _upload_doc(auth_client)
    response = await auth_client.patch(
        f"/documents/{doc_id}/versions/{uuid.uuid4()}/activate"
    )
    assert response.status_code == 404


async def _make_version_with_status(db, doc_id: str, status: str) -> uuid.UUID:
    """Insert a DocumentVersion with arbitrary status directly in DB."""
    from sqlalchemy import update as sa_update

    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == uuid.UUID(doc_id))
        .order_by(DocumentVersion.version_number.desc())
    )
    latest = result.scalar_one()

    version = DocumentVersion(
        document_id=uuid.UUID(doc_id),
        version_number=latest.version_number + 1,
        status=status,
        content_hash="abc123",
        storage_key="test/key",
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version.id


async def test_activate_422_processing_status(auth_client, db, test_user):
    doc_id = await _upload_doc(auth_client)
    ver_id = await _make_version_with_status(db, doc_id, "PROCESSING")
    response = await auth_client.patch(
        f"/documents/{doc_id}/versions/{ver_id}/activate"
    )
    assert response.status_code == 422


async def test_activate_422_failed_status(auth_client, db, test_user):
    doc_id = await _upload_doc(auth_client)
    ver_id = await _make_version_with_status(db, doc_id, "FAILED")
    response = await auth_client.patch(
        f"/documents/{doc_id}/versions/{ver_id}/activate"
    )
    assert response.status_code == 422


async def test_activate_422_deleted_status(auth_client, db, test_user):
    doc_id = await _upload_doc(auth_client)
    ver_id = await _make_version_with_status(db, doc_id, "DELETED")
    response = await auth_client.patch(
        f"/documents/{doc_id}/versions/{ver_id}/activate"
    )
    assert response.status_code == 422
