"""ARQ worker — document processing jobs."""

import asyncio
import logging
import uuid

import openai
from arq.connections import RedisSettings
from sqlalchemy import select, update

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.base import DocumentVersion, ProcessingJob
from app.services import storage
from app.services.chunker import chunk_text
from app.services.documents import detect_content_type
from app.services.embedder import generate_embeddings
from app.services.extractor import extract_text
from app.utils.worker_errors import handle_process_job_error
from app.workers.persistence import persist_results

logger = logging.getLogger(__name__)

_MAX_TRIES = 3
_RETRY_DELAYS = [10, 60]  # seconds: delay

# Errors that will never succeed on retry — fail immediately.
_NON_RETRYABLE = (
    ValueError,                   # unsupported content type from extract_text
    openai.AuthenticationError,   # bad API key
    openai.BadRequestError,       # malformed request (e.g. input too large)
)


async def process_document(ctx: dict, document_version_id: str) -> None:
    """Process a document version end-to-end.

    1. Mark job PROCESSING.
    2. Download raw file from MinIO.
    3. Extract text (PDF/DOCX/TXT/Markdown; OCR if scanned PDF).
    4. Chunk text.
    5. Generate embeddings.
    6. Store chunks + embeddings.
    7. Update full-text search vector.
    8. Supersede any previous ACTIVE version; activate this version.
    9. Emit INDEX_UPDATED audit event.
    10. Mark job COMPLETE.
    """
    version_id = uuid.UUID(document_version_id)
    job_try: int = ctx.get("job_try", 1)

    # ── Phase 1: atomically claim job, load version ───────────────────────────
    async with AsyncSessionLocal() as db:
        # Atomic claim: only one worker wins when multiple pick up the same job.
        # UPDATE returns the row only if status is still claimable; 0 rows = another
        # worker already claimed it or the job reached a terminal state.
        claim_result = await db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.document_version_id == version_id)
            .where(ProcessingJob.status.in_(["QUEUED", "DISPATCHED"]))
            .values(status="PROCESSING", attempts=ProcessingJob.attempts + 1)
            .returning(ProcessingJob.document_version_id)
        )
        if claim_result.scalar_one_or_none() is None:
            logger.info("Job for version %s already claimed or terminal — skipping", version_id)
            return

        version_result = await db.execute(
            select(DocumentVersion).where(DocumentVersion.id == version_id)
        )
        version = version_result.scalar_one()
        document_id = version.document_id
        storage_key = version.storage_key
        await db.commit()

    logger.info(
        "Processing document version %s (attempt %d/%d)",
        version_id,
        job_try,
        _MAX_TRIES,
    )

    try:
        # ── Phase 2: download + extract ───────────────────────────────────────
        loop = asyncio.get_running_loop()
        raw_content = await loop.run_in_executor(
            None, storage.download_bytes, storage_key
        )

        content_type = detect_content_type(raw_content)
        text = extract_text(raw_content, content_type)

        # ── Phase 3: chunk + embed ────────────────────────────────────────────
        raw_chunks = chunk_text(text)
        embeddings = await generate_embeddings(raw_chunks) if raw_chunks else []

        # ── Phase 4: persist results atomically ──────────────────────────────
        await persist_results(version_id, document_id, raw_chunks, embeddings)

    except Exception as exc:
        await handle_process_job_error(
            exc,
            version_id,
            document_id,
            job_try,
            _MAX_TRIES,
            _RETRY_DELAYS,
            _NON_RETRYABLE,
        )

    logger.info(
        "Document version %s processed: %d chunk(s)", version_id, len(raw_chunks)
    )


class WorkerSettings:
    """arq worker configuration."""

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [process_document]
    max_tries = _MAX_TRIES
