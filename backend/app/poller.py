import asyncio
import logging

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.base import ProcessingJob

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 30

async def _dispatch_stale_jobs() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ProcessingJob)
            .where(ProcessingJob.status == "QUEUED")
        )
        jobs = result.scalars().all()
        if not jobs:
            return
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        for job in jobs:
            await pool.enqueue_job("process_document", str(job.document_version_id))
            job.status = "DISPATCHED"
        await pool.aclose()
        await db.commit()
        logger.info("dispatched %d stale job(s) to Redis", len(jobs))


async def run_poller() -> None:
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            await _dispatch_stale_jobs()
        except Exception:
            logger.exception("poller error")
