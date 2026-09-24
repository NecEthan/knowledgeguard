from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Document, DocumentChunk, DocumentVersion
from app.schemas.query import Citation, LLMAnswer


async def fetch_context_chunks(
    db: AsyncSession, top_chunk_ids: list
) -> tuple[list, dict[tuple, tuple]]:
    """Fetch chunk rows from DB in RRF order. Returns (ordered_chunks, metadata_by_key)."""
    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.content,
            DocumentVersion.version_number,
            DocumentVersion.status,
            DocumentVersion.created_at.label("version_created_at"),
            Document.title.label("document_title"),
        )
        .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
        .where(DocumentChunk.id.in_(top_chunk_ids))
    )
    rows_map = {row.id: row for row in (await db.execute(stmt)).all()}
    ordered_chunks = [rows_map[cid] for cid in top_chunk_ids if cid in rows_map]

    metadata_by_key: dict[tuple, tuple] = {}
    for row in ordered_chunks:
        key = (row.document_title, row.version_number)
        if key not in metadata_by_key:
            metadata_by_key[key] = (row.status, row.version_created_at)

    return ordered_chunks, metadata_by_key


def build_context_text(ordered_chunks: list) -> str:
    """Format chunks into a single context string for the LLM prompt."""
    return "\n\n".join(
        f"[Source: {row.document_title} v{row.version_number}]\n{row.content}"
        for row in ordered_chunks
    )


def build_citations(
    llm_answer: LLMAnswer, metadata_by_key: dict[tuple, tuple]
) -> list[Citation]:
    """Build validated citations backed by retrieved context chunks."""
    citations: list[Citation] = []
    seen: set[tuple] = set()
    for llm_citation in llm_answer.citations:
        key = (llm_citation.document_title, llm_citation.version_number)
        if key in metadata_by_key and key not in seen:
            status, version_created_at = metadata_by_key[key]
            citations.append(
                Citation(
                    document_title=llm_citation.document_title,
                    version_number=llm_citation.version_number,
                    status=status,
                    updated_at=version_created_at,
                )
            )
            seen.add(key)
    return citations
