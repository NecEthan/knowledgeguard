"""Shared helpers and constants for processing integration tests."""

import uuid
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import DocumentVersion, ProcessingJob
from app.services.documents import compute_hash, generate_storage_key
from app.workers.main import process_document

TXT_CONTENT = (
    b"Hello KnowledgeGuard. This is the first paragraph about company policies.\n\n"
    b"Second paragraph with more details about annual leave and expense procedures.\n\n"
    b"Third paragraph covering health and safety guidelines for all employees."
)
FAKE_EMBEDDING = [0.1] * 1536


async def upload_doc(
    auth_client, title: str, content: bytes, filename: str = "doc.txt"
) -> uuid.UUID:
    """Upload a document via the API and return its document id."""
    with patch("app.services.storage.upload_bytes"): # mock file upload to minio without returning anything
        response = await auth_client.post(
            "/documents",
            files={"file": (filename, content, "text/plain")},
            data={"title": title, "sensitivity": "STANDARD"},
        )
    assert response.status_code == 202
    return uuid.UUID(response.json()["id"])


async def get_version(db: AsyncSession, doc_id: uuid.UUID) -> DocumentVersion:
    """Fetch the single DocumentVersion for a document."""
    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == doc_id)
    )
    return result.scalar_one()


async def insert_version(
    db: AsyncSession,
    doc_id: uuid.UUID,
    version_number: int,
    content: bytes,
    user_id: uuid.UUID,
) -> DocumentVersion:
    """Insert a new DocumentVersion + QUEUED ProcessingJob."""
    version = DocumentVersion(
        document_id=doc_id,
        version_number=version_number,
        status="PROCESSING",
        content_hash=compute_hash(content),
        storage_key=generate_storage_key(),
        created_by=user_id,
    )
    db.add(version)
    await db.flush()
    db.add(ProcessingJob(document_version_id=version.id, status="QUEUED"))
    await db.commit()
    return version


async def run_worker(
    version_id: uuid.UUID, content: bytes, job_try: int | None = None
) -> None:
    """Run the worker directly with mocked MinIO download."""
    ctx = {"job_try": job_try} if job_try is not None else {}
    with patch("app.workers.main.storage.download_bytes", return_value=content):
        await process_document(ctx, str(version_id))
