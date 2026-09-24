"""Query router — POST /query implements the full RAG pipeline.

Pipeline:
  1. Authentication (get_current_user dependency)
  2. Permission filtering  — documents owned by or shared with the user
  3. Version filtering     — ACTIVE only (current) or ACTIVE+SUPERSEDED (historical)
  4. Hybrid retrieval      — pgvector cosine similarity + PostgreSQL FTS
  5. Reciprocal Rank Fusion
  6. Context assembly
  7. LLM generation (OpenAI chat completion, JSON mode)
  8. Structured response validation
  9. Audit event (QUERY_EXECUTED)
"""

import logging

import openai
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.base import AuditEvent, User
from app.schemas.query import QueryRequest, QueryResponse
from app.services.context_builder import build_citations, build_context_text, fetch_context_chunks
from app.services.embedder import generate_embeddings
from app.services.fts_search import fts_search
from app.services.llm import generate_answer
from app.services.permissions import build_permitted_doc_ids
from app.services.rrf import rrf_combine
from app.services.vector_search import vector_search

logger = logging.getLogger(__name__)
router = APIRouter(tags=["query"])

_VECTOR_LIMIT = 20
_FTS_VERSION_LIMIT = 10
_CONTEXT_CHUNKS = 10


@router.post("/query", response_model=QueryResponse)
async def run_query(
    body: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueryResponse:
    question = body.question.strip()
    mode = body.mode
    allowed_statuses = ["ACTIVE"] if mode == "current" else ["ACTIVE", "SUPERSEDED"]

    # 1. Generate query embedding
    try:
        embeddings = await generate_embeddings([question])
    except openai.OpenAIError as exc:
        logger.warning("OpenAI embedding error: %s", exc)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    query_embedding = embeddings[0]

    # 2. Permission subquery — enforced at DB level
    permitted_doc_ids = build_permitted_doc_ids(current_user)

    # 3. Vector search
    vector_chunk_ranks = await vector_search(
        db, query_embedding, permitted_doc_ids, allowed_statuses, limit=_VECTOR_LIMIT
    )

    # 4. Full-text search
    fts_chunk_ranks = await fts_search(
        db, question, permitted_doc_ids, allowed_statuses, version_limit=_FTS_VERSION_LIMIT
    )

    # 5. Reciprocal Rank Fusion
    combined = rrf_combine(vector_chunk_ranks, fts_chunk_ranks)
    top_chunk_ids = [chunk_id for chunk_id, _ in combined[:_CONTEXT_CHUNKS]]

    if not top_chunk_ids:
        db.add(
            AuditEvent(
                event_type="QUERY_EXECUTED",
                user_id=current_user.id,
                metadata_={"mode": mode, "result_count": 0},
            )
        )
        await db.commit()
        return QueryResponse(
            answer="I don't have enough information to answer that question.",
            citations=[],
        )

    # 6. Fetch context chunks from DB
    ordered_chunks, metadata_by_key = await fetch_context_chunks(db, top_chunk_ids)

    # 7. LLM generation
    context_text = build_context_text(ordered_chunks)
    llm_answer = await generate_answer(question, context_text)

    # 8. Build citations
    citations = build_citations(llm_answer, metadata_by_key)

    # 9. Audit
    db.add(
        AuditEvent(
            event_type="QUERY_EXECUTED",
            user_id=current_user.id,
            metadata_={"mode": mode, "result_count": len(citations)},
        )
    )
    await db.commit()

    return QueryResponse(answer=llm_answer.answer, citations=citations)
