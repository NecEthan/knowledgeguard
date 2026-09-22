"""ARQ worker — document processing jobs."""

import asyncio
import logging
import uuid

from arq.connections import RedisSettings
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.base import DocumentVersion, ProcessingJob
from app.services import storage
from app.services.chunker import chunk_text
from app.services.documents import detect_content_type
from app.services.embedder import generate_embeddings
from app.services.extractor import extract_text
from app.workers.persistence import persist_results

logger = logging.getLogger(__name__)


async def noop(ctx: dict) -> None:
    """Placeholder — not used in production."""


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

    # ── Phase 1: load version, mark job PROCESSING ────────────────────────────
    async with AsyncSessionLocal() as db:
        version_result = await db.execute(
            select(DocumentVersion).where(DocumentVersion.id == version_id)
        )
        version = version_result.scalar_one()
        document_id = version.document_id
        storage_key = version.storage_key

        job_result = await db.execute(
            select(ProcessingJob)
            .where(ProcessingJob.document_version_id == version_id)
            .limit(1)
        )
        job = job_result.scalar_one()
        job.status = "PROCESSING"
        job.attempts += 1
        await db.commit()

    logger.info("Processing document version %s", version_id)

    # ── Phase 2: download + extract ───────────────────────────────────────────
    loop = asyncio.get_running_loop()
    raw_content = await loop.run_in_executor(None, storage.download_bytes, storage_key)

    content_type = detect_content_type(raw_content)
    text = extract_text(raw_content, content_type)

    # ── Phase 3: chunk + embed ────────────────────────────────────────────────
    raw_chunks = chunk_text(text)
    embeddings = await generate_embeddings(raw_chunks) if raw_chunks else []

    # ── Phase 4: persist results atomically ───────────────────────────────────
    await persist_results(version_id, document_id, raw_chunks, embeddings)

    logger.info(
        "Document version %s processed: %d chunk(s)", version_id, len(raw_chunks)
    )


class WorkerSettings:
    """arq worker configuration."""

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [noop, process_document]
