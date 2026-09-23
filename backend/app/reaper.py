"""Stale job reaper — recovers PROCESSING jobs abandoned by hard-crashed workers."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models.base import AuditEvent, DocumentVersion, ProcessingJob
from app.services import storage

logger = logging.getLogger(__name__)

_STALE_THRESHOLD = timedelta(minutes=10)
_MAX_ATTEMPTS = 3


async def reap_stale_processing_jobs() -> None:
    """Reset jobs stuck in PROCESSING due to hard crashes (SIGKILL, power loss).

    A job is considered stale when updated_at has not changed for longer than
    _STALE_THRESHOLD — meaning the worker died without committing a terminal state.
    Jobs under the attempt limit are reset to QUEUED so the poller re-dispatches
    them. Exhausted jobs are marked FAILED.
    """
    threshold = datetime.now(UTC) - _STALE_THRESHOLD
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ProcessingJob, DocumentVersion.document_id, DocumentVersion.storage_key)
            .join(DocumentVersion, ProcessingJob.document_version_id == DocumentVersion.id)
            .where(ProcessingJob.status == "PROCESSING")
            .where(ProcessingJob.updated_at < threshold)
        )
        rows = result.all()
        if not rows:
            return

        keys_to_delete: list[str] = []
        for job, document_id, storage_key in rows:
            if job.attempts < _MAX_ATTEMPTS:
                job.status = "QUEUED"
                logger.warning(
                    "Reaped stale job for version %s (attempts=%d) — reset to QUEUED",
                    job.document_version_id,
                    job.attempts,
                )
            else:
                job.status = "FAILED"
                job.last_error = "Job exceeded max attempts after stale recovery"
                await db.execute(
                    update(DocumentVersion)
                    .where(DocumentVersion.id == job.document_version_id)
                    .values(status="FAILED")
                )
                db.add(
                    AuditEvent(
                        event_type="PROCESSING_FAILED",
                        document_id=document_id,
                        version_id=job.document_version_id,
                    )
                )
                keys_to_delete.append(storage_key)
                logger.error(
                    "Reaped stale job for version %s — max attempts exhausted, marked FAILED",
                    job.document_version_id,
                )

        await db.commit()
        logger.info("Reaped %d stale PROCESSING job(s)", len(rows))

    loop = asyncio.get_running_loop()
    for key in keys_to_delete:
        await loop.run_in_executor(None, storage.delete_object, key)
