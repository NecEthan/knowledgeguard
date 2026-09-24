"""PostgreSQL full-text search over document versions."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Document, DocumentChunk, DocumentVersion


async def fts_search(
    db: AsyncSession,
    question: str,
    permitted_doc_ids,
    allowed_statuses: list[str],
    version_limit: int = 10,
) -> list[tuple[uuid.UUID, int]]:
    """Return (chunk_id, rank) pairs from full-text search.

    Matches at the DocumentVersion level using the pre-built search_vector
    (TSVECTOR column populated from all chunk text at index time). All chunks
    belonging to a matching version inherit that version's FTS rank.

    Args:
        permitted_doc_ids: Scalar subquery of document IDs the user may access.
        allowed_statuses:  Version statuses to include (e.g. ['ACTIVE']).
        version_limit:     Maximum versions to consider.

    Returns:
        1-based ranked list — rank 1 belongs to the highest-scoring version.
    """
    tsquery = func.plainto_tsquery("english", question)

    version_stmt = (
        select(
            DocumentVersion.id.label("version_id"),
            func.ts_rank(DocumentVersion.search_vector, tsquery).label("rank"),
        )
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(Document.id.in_(permitted_doc_ids))
        .where(DocumentVersion.status.in_(allowed_statuses))
        .where(DocumentVersion.search_vector.op("@@")(tsquery))
        .order_by(func.ts_rank(DocumentVersion.search_vector, tsquery).desc())
        .limit(version_limit)
    )
    version_rows = (await db.execute(version_stmt)).all()

    if not version_rows:
        return []

    version_rank_map = {row.version_id: i + 1 for i, row in enumerate(version_rows)}
    fts_version_ids = list(version_rank_map.keys())

    chunks_stmt = select(
        DocumentChunk.id, DocumentChunk.document_version_id
    ).where(DocumentChunk.document_version_id.in_(fts_version_ids))
    chunk_rows = (await db.execute(chunks_stmt)).all()

    return [
        (row.id, version_rank_map[row.document_version_id])
        for row in chunk_rows
    ]
