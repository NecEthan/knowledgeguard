"""Error handling utilities for ARQ worker jobs."""

import logging
import uuid
from typing import NoReturn

from arq import Retry

from app.workers.failure import persist_failure, reset_job_for_retry

logger = logging.getLogger(__name__)


async def handle_process_job_error(
    exc: Exception,
    version_id: uuid.UUID,
    document_id: uuid.UUID,
    job_try: int,
    max_tries: int,
    retry_delays: list[int],
    non_retryable: tuple,
) -> NoReturn:
    """Log, classify, and dispatch job failure.

    - Known permanent error: persist failure immediately, no retry.
    - Transient / unknown error: retry if attempts remain, else persist failure.
    Always raises.
    """
    error_msg = f"{type(exc).__name__}: {exc}"[:500]
    logger.exception("Version %s failed (attempt %d/%d)", version_id, job_try, max_tries)

    if isinstance(exc, non_retryable):
        logger.error("Non-retryable error for version %s — failing immediately", version_id)
        await persist_failure(version_id, document_id, error_msg)
        raise exc

    if job_try < max_tries:
        delay = retry_delays[job_try - 1]
        await reset_job_for_retry(version_id)
        raise Retry(defer=delay) from exc

    await persist_failure(version_id, document_id, error_msg)
    raise exc
