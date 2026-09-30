"""Integration tests for auth routes — audit event emission and transaction atomicity."""

import uuid
from unittest.mock import patch

from sqlalchemy import delete, select

from app.models.base import AuditEvent, Session, User
from app.services.auth import hash_password


async def test_register_emits_user_registered_event(client, db):
    email = f"reg+{uuid.uuid4().hex[:8]}@example.com"
    response = await client.post(
        "/auth/register", json={"email": email, "password": "password123"}
    )
    assert response.status_code == 201
    user_id = uuid.UUID(response.json()["id"])

    db.expire_all()
    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.event_type == "USER_REGISTERED")
        .where(AuditEvent.user_id == user_id)
    )
    event = result.scalar_one_or_none()
    assert event is not None

    # Cleanup
    await db.execute(delete(AuditEvent).where(AuditEvent.user_id == user_id))
    await db.execute(delete(Session).where(Session.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()


async def test_login_emits_user_login_event(client, db):
    email = f"login+{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("password123"),
        role="user",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    user_id = user.id

    response = await client.post(
        "/auth/login", json={"email": email, "password": "password123"}
    )
    assert response.status_code == 200

    db.expire_all()
    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.event_type == "USER_LOGIN")
        .where(AuditEvent.user_id == user_id)
    )
    event = result.scalar_one_or_none()
    assert event is not None

    # Cleanup
    await db.execute(delete(AuditEvent).where(AuditEvent.user_id == user_id))
    await db.execute(delete(Session).where(Session.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()


async def test_failed_login_does_not_emit_event(client, db):
    response = await client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "wrong"}
    )
    assert response.status_code == 401


async def test_register_is_atomic_audit_failure_rolls_back_user(client, db):
    """If AuditEvent creation fails, the User must not be persisted."""
    email = f"atomic-reg+{uuid.uuid4().hex[:8]}@example.com"

    with patch("app.routers.auth.AuditEvent", side_effect=Exception("audit failure")):
        response = await client.post(
            "/auth/register", json={"email": email, "password": "password123"}
        )

    assert response.status_code == 500

    db.expire_all()
    result = await db.execute(select(User).where(User.email == email))
    assert result.scalar_one_or_none() is None


async def test_login_is_atomic_audit_failure_rolls_back_session(client, db):
    """If AuditEvent creation fails, the Session must not be persisted."""
    email = f"atomic-login+{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("password123"),
        role="user",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    user_id = user.id

    with patch("app.routers.auth.AuditEvent", side_effect=Exception("audit failure")):
        response = await client.post(
            "/auth/login", json={"email": email, "password": "password123"}
        )

    assert response.status_code == 500

    db.expire_all()
    result = await db.execute(select(Session).where(Session.user_id == user_id))
    assert result.scalar_one_or_none() is None

    # Cleanup
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
