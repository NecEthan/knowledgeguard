from arq.connections import RedisSettings

from app.config import settings


async def noop(ctx: dict) -> None:
    """Placeholder — replace with real job functions as they are implemented."""


async def process_document(ctx: dict, document_version_id: str) -> None:
    """Process a document version: extract text, chunk, embed, update status.

    TODO: implement text extraction, chunking, and embedding.
    """


class WorkerSettings:
    """arq worker configuration."""

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [noop, process_document]
