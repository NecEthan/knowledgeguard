"""Version lifecycle tests.

Covers: superseding on re-upload, previous version protected when new version fails.
"""

import pytest
from arq import Retry
from sqlalchemy import select
from unittest.mock import patch

from app.models.base import DocumentVersion
from app.workers.main import process_document
from tests.helpers.processing import (
    get_version,
    insert_version,
    run_worker,
    upload_doc,
)


async def test_process_document_previous_active_superseded(auth_client, db, test_user):
    """When a second version is processed, the first ACTIVE version is superseded."""
    doc_id = await upload_doc(auth_client, "Doc", b"Version one content.", "v1.txt")
    v1_id = (await get_version(db, doc_id)).id

    await run_worker(v1_id, b"Version one content.")

    db.expire_all()
    result = await db.execute(select(DocumentVersion).where(DocumentVersion.id == v1_id))
    assert result.scalar_one().status == "ACTIVE"

    v2 = await insert_version(db, doc_id, 2, b"Version two content.", test_user.id)
    await run_worker(v2.id, b"Version two content.")

    db.expire_all()
    result = await db.execute(select(DocumentVersion).where(DocumentVersion.id == v1_id))
    assert result.scalar_one().status == "SUPERSEDED"

    result = await db.execute(select(DocumentVersion).where(DocumentVersion.id == v2.id))
    assert result.scalar_one().status == "ACTIVE"


async def test_previous_version_protected_on_failure(auth_client, db, test_user):
    """Failing v2 leaves v1 ACTIVE; successfully processing v3 supersedes v1."""
    doc_id = await upload_doc(auth_client, "Protected Doc", b"Version one content.", "v1.txt")
    v1_id = (await get_version(db, doc_id)).id

    await run_worker(v1_id, b"Version one content.")

    db.expire_all()
    result = await db.execute(select(DocumentVersion).where(DocumentVersion.id == v1_id))
    assert result.scalar_one().status == "ACTIVE"

    v2 = await insert_version(db, doc_id, 2, b"Version two content.", test_user.id)
    error = RuntimeError("extraction failed")
    for attempt in (1, 2):
        with patch("app.workers.main.storage.download_bytes", side_effect=error):
            with pytest.raises(Retry):
                await process_document({"job_try": attempt}, str(v2.id))
    with patch("app.workers.main.storage.download_bytes", side_effect=error):
        with pytest.raises(RuntimeError):
            await process_document({"job_try": 3}, str(v2.id))

    db.expire_all()
    result = await db.execute(select(DocumentVersion).where(DocumentVersion.id == v1_id))
    assert result.scalar_one().status == "ACTIVE"
    result = await db.execute(select(DocumentVersion).where(DocumentVersion.id == v2.id))
    assert result.scalar_one().status == "FAILED"

    v3 = await insert_version(db, doc_id, 3, b"Version three content.", test_user.id)
    await run_worker(v3.id, b"Version three content.")

    db.expire_all()
    result = await db.execute(select(DocumentVersion).where(DocumentVersion.id == v3.id))
    assert result.scalar_one().status == "ACTIVE"
    result = await db.execute(select(DocumentVersion).where(DocumentVersion.id == v1_id))
    assert result.scalar_one().status == "SUPERSEDED"
