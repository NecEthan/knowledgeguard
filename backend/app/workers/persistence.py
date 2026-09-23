"""DB persistence for the document processing pipeline."""

import uuid

from sqlalchemy import delete, func, update

from app.database import AsyncSessionLocal
from app.models.base import AuditEvent, DocumentChunk, DocumentVersion
from app.services.chunker import estimate_tokens
from app.workers.activation import activate_version


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

        await activate_version(db, version_id, document_id)

        # Emit INDEX_UPDATED audit event.
        db.add(
            AuditEvent(
                event_type="INDEX_UPDATED",
                document_id=document_id,
                version_id=version_id,
            )
        )

        await db.commit()



