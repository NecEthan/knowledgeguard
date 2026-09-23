"""Failure persistence for the document processing pipeline."""

import asyncio
import uuid

from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models.base import AuditEvent, DocumentVersion, ProcessingJob
from app.services import storage


async def reset_job_for_retry(version_id: uuid.UUID) -> None:
    """Reset job status to QUEUED so the next attempt can claim it atomically."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.document_version_id == version_id)
            .values(status="QUEUED")
        )
        await db.commit()


async def persist_failure(
    version_id: uuid.UUID,
    document_id: uuid.UUID,
    error_msg: str,
) -> None:
    """Record permanent failure. Does NOT touch any existing ACTIVE version."""
    async with AsyncSessionLocal() as db:
        storage_key_result = await db.execute(
            select(DocumentVersion.storage_key).where(DocumentVersion.id == version_id)
        )
        storage_key = storage_key_result.scalar_one_or_none()

        await db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.document_version_id == version_id)
            .where(ProcessingJob.status == "PROCESSING")
            .values(status="FAILED", last_error=error_msg)
        )
        await db.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id == version_id)
            .values(status="FAILED")
        )
        db.add(
            AuditEvent(
                event_type="PROCESSING_FAILED",
                document_id=document_id,
                version_id=version_id,
            )
        )
        await db.commit()

    if storage_key:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, storage.delete_object, storage_key)
