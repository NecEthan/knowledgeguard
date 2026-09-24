from collections.abc import AsyncGenerator

from arq.connections import ArqRedis
from fastapi import Depends, HTTPException, Request
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.base import Document, User
from app.services.auth import get_valid_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_arq_pool(request: Request) -> ArqRedis:
    return request.app.state.arq_pool


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = await get_valid_session(db, token)
    if session is None:
        raise HTTPException(status_code=401, detail="Session invalid or expired")
    return session.user


def sensitivity_filters(current_user: User) -> list[ColumnElement[bool]]:
    """For non-admin users, restrict access to STANDARD documents only."""
    if current_user.role == "admin":
        return []
    return [Document.sensitivity == "STANDARD"]
