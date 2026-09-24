"""Auth and HTTP client fixtures for router integration tests."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.main import app
from app.models.base import (
    AuditEvent,
    Document,
    DocumentChunk,
    DocumentVersion,
    ProcessingJob,
    Session,
    User,
)
from app.services.auth import hash_password


@pytest.fixture
async def test_user(db):
    user = User(
        email=f"test+{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password"),
        role="user",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    user_id = (
        user.id
    )  # capture before yield — expire_all() in tests makes user.id inaccessible

    yield user

    # Delete in FK order: chunks/jobs → versions → audit events → documents → sessions → user
    doc_ids = select(Document.id).where(Document.owner_id == user_id)
    version_ids = select(DocumentVersion.id).where(
        DocumentVersion.document_id.in_(doc_ids)
    )
    await db.execute(
        delete(DocumentChunk).where(DocumentChunk.document_version_id.in_(version_ids))
    )
    await db.execute(
        delete(ProcessingJob).where(ProcessingJob.document_version_id.in_(version_ids))
    )
    await db.execute(
        delete(DocumentVersion).where(DocumentVersion.document_id.in_(doc_ids))
    )
    await db.execute(delete(AuditEvent).where(AuditEvent.document_id.in_(doc_ids)))
    await db.execute(delete(AuditEvent).where(AuditEvent.user_id == user_id))
    await db.execute(delete(Document).where(Document.owner_id == user_id))
    await db.execute(delete(Session).where(Session.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()


@pytest.fixture
async def auth_cookies(db, test_user):
    token = secrets.token_urlsafe(32)
    session = Session(
        session_token=token,
        user_id=test_user.id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(session)
    await db.commit()
    return {"kg_session": token}


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
async def auth_client(auth_cookies):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies=auth_cookies,
    ) as c:
        yield c
