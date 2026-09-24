"""Version activation logic for the document processing pipeline."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import AuditEvent, DocumentVersion, ProcessingJob


async def activate_version(
    db: AsyncSession,
    version_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    """Supersede existing ACTIVE version, activate new version, mark job COMPLETE.

    Must supersede before activating to satisfy the
    one_active_version_per_document partial unique index.
    """
    # Capture the current active version so we can emit VERSION_SUPERSEDED.
    result = await db.execute(
        select(DocumentVersion.id)
        .where(DocumentVersion.document_id == document_id)
        .where(DocumentVersion.status == "ACTIVE")
    )
    superseded_id = result.scalar_one_or_none()

    if superseded_id is not None:
        await db.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id == superseded_id)
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

    if superseded_id is not None:
        db.add(
            AuditEvent(
                event_type="VERSION_SUPERSEDED",
                document_id=document_id,
                version_id=superseded_id,
            )
        )
