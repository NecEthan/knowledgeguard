import logging
import uuid

from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import ProcessingJob

logger = logging.getLogger(__name__)


async def enqueue_processing_job(
    arq_pool: ArqRedis,
    db: AsyncSession,
    job: ProcessingJob,
    version_id: uuid.UUID,
) -> None:
    """Enqueue a process_document job. If Redis is down, job stays QUEUED and
    the background poller will re-enqueue it once Redis recovers."""
    try:
        await arq_pool.enqueue_job(
            "process_document",
            str(version_id),
            _job_id=f"process_document:{version_id}",
        )
        job.status = "DISPATCHED"
        await db.commit()
    except Exception:
        logger.exception(
            "failed to enqueue job for version %s — poller will retry", version_id
        )
