import asyncio
import logging

from arq.connections import ArqRedis
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.base import ProcessingJob
from app.reaper import reap_stale_processing_jobs

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 30


async def _dispatch_stale_jobs(pool: ArqRedis) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ProcessingJob).where(ProcessingJob.status == "QUEUED")
        )
        jobs = result.scalars().all()
        if not jobs:
            return
        for job in jobs:
            # If error occurs after job is enqueued, the job status will not be set to DISPATCHED
            # resulting in a job being enqueued twice
            # enqueue job internally checks if a job with the same _job_id already exists
            # if does then returns None
            await pool.enqueue_job(
                "process_document",
                str(job.document_version_id),
                _job_id=f"process_document:{job.document_version_id}",
            )
            job.status = "DISPATCHED"
        await db.commit()
        logger.info("dispatched %d queued job(s) to Redis", len(jobs))


async def run_poller(pool: ArqRedis) -> None:
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            await reap_stale_processing_jobs()
            await _dispatch_stale_jobs(pool)
        except Exception:
            logger.exception("poller error")
