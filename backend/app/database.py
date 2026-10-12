from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

_db_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
    "postgres://", "postgresql+asyncpg://", 1
)

engine = create_async_engine(
    _db_url,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass
