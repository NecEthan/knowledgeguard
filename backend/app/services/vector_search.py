"""pgvector cosine-similarity search over document chunks."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Document, DocumentChunk, DocumentVersion


async def vector_search(
    db: AsyncSession,
    query_embedding: list[float],
    permitted_doc_ids,
    allowed_statuses: list[str],
    limit: int = 20,
) -> list[tuple[uuid.UUID, int]]:
    """Return (chunk_id, rank) pairs ordered by cosine similarity.

    Args:
        permitted_doc_ids: Scalar subquery of document IDs the user may access.
        allowed_statuses:  Version statuses to include (e.g. ['ACTIVE']).
        limit:             Maximum chunks to return.

    Returns:
        1-based ranked list — rank 1 is closest to the query embedding.
    """
    stmt = (
        select(DocumentChunk.id)
        .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(Document.id.in_(permitted_doc_ids))
        .where(DocumentVersion.status.in_(allowed_statuses))
        .where(DocumentChunk.embedding.is_not(None))
        .order_by(DocumentChunk.embedding.op("<=>")(query_embedding))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [(row.id, i + 1) for i, row in enumerate(rows)]
