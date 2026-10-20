import asyncio
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.base import Session

_bcrypt_executor = ThreadPoolExecutor(max_workers=settings.bcrypt_executor_workers)


async def hash_password(password: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _bcrypt_executor,
        lambda: bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    )


async def verify_password(plain: str, hashed: str) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _bcrypt_executor, lambda: bcrypt.checkpw(plain.encode(), hashed.encode())
    )


async def create_session(db: AsyncSession, user_id: uuid.UUID) -> Session:
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    session = Session(
        session_token=token,
        user_id=user_id,
        expires_at=now + timedelta(hours=settings.session_max_age_hours),
    )
    db.add(session)
    return session


async def get_valid_session(db: AsyncSession, token: str) -> Session | None:
    result = await db.execute(
        select(Session)
        .where(Session.session_token == token)
        .where(Session.expires_at > func.now())
        .options(selectinload(Session.user))
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None
    await db.commit()
    return session


async def invalidate_session(db: AsyncSession, token: str) -> None:
    result = await db.execute(select(Session).where(Session.session_token == token))
    session = result.scalar_one_or_none()
    if session is not None:
        await db.delete(session)
        await db.commit()
