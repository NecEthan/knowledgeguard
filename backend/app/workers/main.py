from arq.connections import RedisSettings

from app.config import settings


async def noop(ctx: dict) -> None:
    """Placeholder — replace with real job functions as they are implemented."""


class WorkerSettings:
    """arq worker configuration."""

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [noop]
