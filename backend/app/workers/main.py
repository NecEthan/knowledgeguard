"""ARQ worker — document processing jobs."""

import asyncio
import time
import uuid

import structlog
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
from app.workers.activation import DocumentDeletedError
from app.workers.constants import MAX_TRIES
from app.workers.persistence import persist_results

logger = structlog.get_logger(__name__)


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
    start = time.monotonic()

    # Bind job context so all log entries within this run share version_id + attempt.
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        service="worker",
        version_id=str(version_id),
        attempt=job_try,
    )

    # ── Phase 1: mark job PROCESSING, load version ────────────────────────────
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.document_version_id == version_id)
            .values(status="PROCESSING", attempts=ProcessingJob.attempts + 1)
        )
        version_result = await db.execute(
            select(DocumentVersion).where(DocumentVersion.id == version_id)
        )
        version = version_result.scalar_one_or_none()
        if version is None:
            # Document was deleted before the worker started — nothing to do.
            logger.info("job_skipped", reason="version_not_found")
            return
        document_id = version.document_id
        storage_key = version.storage_key
        await db.commit()

    logger.info("job_start", max_tries=MAX_TRIES)

    raw_chunks: list[str] = []
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

    except DocumentDeletedError:
        # Document was deleted mid-processing — abort cleanly without retry.
        logger.info("job_aborted", reason="document_deleted")
        async with AsyncSessionLocal() as cleanup_db:
            await cleanup_db.execute(
                update(ProcessingJob)
                .where(ProcessingJob.document_version_id == version_id)
                .where(ProcessingJob.status == "PROCESSING")
                .values(status="FAILED", last_error="Document deleted")
            )
            await cleanup_db.commit()
        return

    except Exception as exc:
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        logger.warning(
            "job_failure",
            error_type=type(exc).__name__,
            duration_ms=duration_ms,
            max_tries=MAX_TRIES,
        )
        await handle_process_job_error(
            exc,
            version_id,
            document_id,
            job_try,
            MAX_TRIES,
        )

    duration_ms = round((time.monotonic() - start) * 1000, 1)
    logger.info(
        "job_complete",
        chunk_count=len(raw_chunks),
        duration_ms=duration_ms,
    )


class WorkerSettings:
    """arq worker configuration."""

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [process_document]
    max_tries = MAX_TRIES
