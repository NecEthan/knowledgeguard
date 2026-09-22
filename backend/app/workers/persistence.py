"""DB persistence for the document processing pipeline."""

import uuid

from sqlalchemy import func, update

from app.database import AsyncSessionLocal
from app.models.base import AuditEvent, DocumentChunk, DocumentVersion, ProcessingJob
from app.services.chunker import estimate_tokens


async def persist_results(
    version_id: uuid.UUID,
    document_id: uuid.UUID,
    raw_chunks: list[str],
    embeddings: list[list[float]],
) -> None:
    """Atomically write chunks, activate version, and emit audit event."""
    async with AsyncSessionLocal() as db:
        # Insert chunks with embeddings.
        for i, (chunk_content, embedding) in enumerate(zip(raw_chunks, embeddings)):
            db.add(
                DocumentChunk(
                    document_version_id=version_id,
                    chunk_index=i,
                    content=chunk_content,
                    embedding=embedding,
                    token_count=estimate_tokens(chunk_content),
                )
            )
        await db.flush()

        # Update full-text search vector from concatenated chunk text.
        combined_text = " ".join(raw_chunks)
        if combined_text.strip():
            await db.execute(
                update(DocumentVersion)
                .where(DocumentVersion.id == version_id)
                .values(search_vector=func.to_tsvector("english", combined_text))
            )

        # Supersede the existing ACTIVE version for this document (if any).
        # Must happen before activating the new version to satisfy the
        # one_active_version_per_document partial unique index.
        await db.execute(
            update(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .where(DocumentVersion.status == "ACTIVE")
            .values(status="SUPERSEDED")
        )

        # Activate the new version.
        await db.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id == version_id)
            .values(status="ACTIVE")
        )

        # Mark the processing job complete.
        await db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.document_version_id == version_id)
            .where(ProcessingJob.status == "PROCESSING")
            .values(status="COMPLETE")
        )

        # Emit INDEX_UPDATED audit event.
        db.add(
            AuditEvent(
                event_type="INDEX_UPDATED",
                document_id=document_id,
                version_id=version_id,
            )
        )

        await db.commit()
