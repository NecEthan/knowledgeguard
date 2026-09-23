"""Version activation logic for the document processing pipeline."""

import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import DocumentVersion, ProcessingJob


async def activate_version(
    db: AsyncSession,
    version_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    """Supersede existing ACTIVE version, activate new version, mark job COMPLETE.

    Must supersede before activating to satisfy the
    one_active_version_per_document partial unique index.
    """
    await db.execute(
        update(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .where(DocumentVersion.status == "ACTIVE")
        .values(status="SUPERSEDED")
    )
    await db.execute(
        update(DocumentVersion)
        .where(DocumentVersion.id == version_id)
        .values(status="ACTIVE")
    )
    await db.execute(
        update(ProcessingJob)
        .where(ProcessingJob.document_version_id == version_id)
        .values(status="COMPLETE")
    )
