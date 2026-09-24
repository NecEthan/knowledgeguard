"""Version lifecycle tests.

Covers: superseding on re-upload, previous version protected when new version fails.
"""

from unittest.mock import patch

import pytest
from arq import Retry
from sqlalchemy import select

from app.models.base import AuditEvent, DocumentVersion
from app.workers.main import process_document
from tests.helpers.processing import (
    get_version,
    insert_version,
    run_worker,
    upload_doc,
)


async def test_process_document_previous_active_superseded(auth_client, db, test_user):
    """When a second version is processed, the first ACTIVE version is superseded."""
    user_id = test_user.id  # capture before expire_all
    doc_id = await upload_doc(auth_client, "Doc", b"Version one content.", "v1.txt")
    v1_id = (await get_version(db, doc_id)).id

    await run_worker(v1_id, b"Version one content.")

    db.expire_all()
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == v1_id)
    )
    assert result.scalar_one().status == "ACTIVE"

    v2 = await insert_version(db, doc_id, 2, b"Version two content.", user_id)
    v2_id = v2.id  # capture before expire_all
    await run_worker(v2_id, b"Version two content.")

    db.expire_all()
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == v1_id)
    )
    assert result.scalar_one().status == "SUPERSEDED"

    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == v2_id)
    )
    assert result.scalar_one().status == "ACTIVE"


async def test_previous_version_protected_on_failure(auth_client, db, test_user):
    """Failing v2 leaves v1 ACTIVE; successfully processing v3 supersedes v1."""
    user_id = test_user.id  # capture before expire_all
    doc_id = await upload_doc(
        auth_client, "Protected Doc", b"Version one content.", "v1.txt"
    )
    v1_id = (await get_version(db, doc_id)).id

    await run_worker(v1_id, b"Version one content.")

    db.expire_all()
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == v1_id)
    )
    assert result.scalar_one().status == "ACTIVE"

    v2 = await insert_version(db, doc_id, 2, b"Version two content.", user_id)
    v2_id = v2.id  # capture before expire_all
    error = RuntimeError("extraction failed")
    for attempt in (1, 2):
        with patch("app.workers.main.storage.download_bytes", side_effect=error):
            with pytest.raises(Retry):
                await process_document({"job_try": attempt}, str(v2_id))
    with patch("app.workers.main.storage.download_bytes", side_effect=error):
        with pytest.raises(RuntimeError):
            await process_document({"job_try": 3}, str(v2_id))

    db.expire_all()
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == v1_id)
    )
    assert result.scalar_one().status == "ACTIVE"
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == v2_id)
    )
    assert result.scalar_one().status == "FAILED"

    v3 = await insert_version(db, doc_id, 3, b"Version three content.", user_id)
    v3_id = v3.id  # capture before expire_all
    await run_worker(v3_id, b"Version three content.")

    db.expire_all()
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == v3_id)
    )
    assert result.scalar_one().status == "ACTIVE"
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.id == v1_id)
    )
    assert result.scalar_one().status == "SUPERSEDED"


async def test_version_superseded_audit_event_emitted(auth_client, db, test_user):
    """VERSION_SUPERSEDED audit event is emitted for the old ACTIVE version."""
    user_id = test_user.id  # capture before expire_all
    doc_id = await upload_doc(auth_client, "Audit Doc", b"Version one.", "v1.txt")
    v1 = await get_version(db, doc_id)
    v1_id = v1.id  # capture before expire_all
    await run_worker(v1.id, b"Version one.")

    v2 = await insert_version(db, doc_id, 2, b"Version two.", user_id)
    await run_worker(v2.id, b"Version two.")

    db.expire_all()
    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.event_type == "VERSION_SUPERSEDED")
        .where(AuditEvent.document_id == doc_id)
    )
    event = result.scalar_one_or_none()
    assert event is not None
    assert event.version_id == v1_id
