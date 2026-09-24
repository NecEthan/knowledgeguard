"""Integration tests for POST /query.

Postgres is real; OpenAI (embeddings + chat) is mocked.
"""

import json
import secrets
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import delete, func, select, update

from app.models.base import (
    AuditEvent,
    Document,
    DocumentChunk,
    DocumentPermission,
    DocumentVersion,
    User,
)
from app.services.auth import hash_password


# ── Helpers ──────────────────────────────────────────────────────────────────


def _fake_embedding() -> list[float]:
    return [0.1] * 1536


def _mock_embedding_call(embedding: list[float] | None = None):
    return AsyncMock(return_value=[embedding or _fake_embedding()])


def _mock_chat_call(answer: str, citations: list[dict] | None = None):
    """Return a mock AsyncOpenAI instance whose chat.completions.create is mocked."""
    content = json.dumps({"answer": answer, "citations": citations or []})
    choice = MagicMock()
    choice.message.content = content
    completion = MagicMock()
    completion.choices = [choice]
    return AsyncMock(return_value=completion)


def _openai_ctx(mock_emb, mock_chat):
    """Context managers for patching generate_embeddings and AsyncOpenAI."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        with (
            patch("app.routers.query.generate_embeddings", new=mock_emb),
            patch("app.routers.query.AsyncOpenAI") as mock_cls,
        ):
            instance = MagicMock()
            mock_cls.return_value = instance
            instance.chat.completions.create = mock_chat
            yield

    return _ctx()


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def indexed_document(db, test_user):
    """Create Document + ACTIVE version with chunk and fake embedding."""
    doc = Document(
        title="Annual Leave Policy",
        owner_id=test_user.id,
        source_type="upload",
    )
    db.add(doc)
    await db.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        status="ACTIVE",
        content_hash=secrets.token_hex(16),
        storage_key=f"uploads/{doc.id}/v1.txt",
    )
    db.add(version)
    await db.flush()

    content = "Employees receive 25 days of annual leave per year."
    await db.execute(
        update(DocumentVersion)
        .where(DocumentVersion.id == version.id)
        .values(search_vector=func.to_tsvector("english", content))
    )

    chunk = DocumentChunk(
        document_version_id=version.id,
        chunk_index=0,
        content=content,
        embedding=_fake_embedding(),
        token_count=10,
    )
    db.add(chunk)
    await db.commit()
    await db.refresh(doc)
    await db.refresh(version)
    await db.refresh(chunk)

    yield doc, version, chunk
    # test_user teardown handles doc/version/chunk/audit cleanup.


# ── Auth tests ────────────────────────────────────────────────────────────────


async def test_query_requires_auth(client):
    response = await client.post(
        "/query", json={"question": "What is the annual leave policy?"}
    )
    assert response.status_code == 401


async def test_query_whitespace_question_handled(auth_client):
    # Whitespace-only passes Pydantic min_length=1 (length 3).
    # Endpoint strips it and proceeds; empty context → "I don't know" answer.
    mock_emb = _mock_embedding_call()
    mock_chat = _mock_chat_call(
        answer="I don't have enough information to answer that question.",
        citations=[],
    )
    with _openai_ctx(mock_emb, mock_chat):
        response = await auth_client.post("/query", json={"question": "   "})
    assert response.status_code == 200


# ── Successful query ──────────────────────────────────────────────────────────


async def test_query_returns_answer_and_citation(auth_client, db, indexed_document):
    doc, version, chunk = indexed_document

    mock_emb = _mock_embedding_call()
    mock_chat = _mock_chat_call(
        answer="Employees receive 25 days per year.",
        citations=[{"document_title": "Annual Leave Policy", "version_number": 1}],
    )

    with _openai_ctx(mock_emb, mock_chat):
        response = await auth_client.post(
            "/query",
            json={"question": "How many days of annual leave do employees get?"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Employees receive 25 days per year."
    assert len(data["citations"]) == 1
    citation = data["citations"][0]
    assert citation["document_title"] == "Annual Leave Policy"
    assert citation["version_number"] == 1
    assert citation["status"] == "ACTIVE"
    assert "updated_at" in citation


async def test_query_citation_includes_all_required_fields(auth_client, indexed_document):
    doc, version, chunk = indexed_document

    mock_emb = _mock_embedding_call()
    mock_chat = _mock_chat_call(
        answer="25 days.",
        citations=[{"document_title": "Annual Leave Policy", "version_number": 1}],
    )

    with _openai_ctx(mock_emb, mock_chat):
        response = await auth_client.post(
            "/query",
            json={"question": "Leave days?"},
        )

    assert response.status_code == 200
    citation = response.json()["citations"][0]
    assert "document_title" in citation
    assert "version_number" in citation
    assert "status" in citation
    assert "updated_at" in citation


async def test_query_audit_event_written(auth_client, db, test_user, indexed_document):
    mock_emb = _mock_embedding_call()
    mock_chat = _mock_chat_call(answer="Some answer.", citations=[])

    with _openai_ctx(mock_emb, mock_chat):
        await auth_client.post("/query", json={"question": "test question"})

    result = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.event_type == "QUERY_EXECUTED")
        .where(AuditEvent.user_id == test_user.id)
    )
    event = result.scalar_one_or_none()
    assert event is not None
    assert event.metadata_["mode"] == "current"


# ── LLM unavailable → 503 ─────────────────────────────────────────────────────


async def test_llm_unavailable_returns_503(auth_client, indexed_document):
    import openai as oai

    mock_emb = _mock_embedding_call()
    mock_chat = AsyncMock(side_effect=oai.OpenAIError("mocked outage"))

    with _openai_ctx(mock_emb, mock_chat):
        response = await auth_client.post(
            "/query", json={"question": "What is the policy?"}
        )

    assert response.status_code == 503
    body = response.json()
    assert "detail" in body
    # Must not expose provider internals.
    assert "openai" not in body["detail"].lower()
    assert "api_key" not in body["detail"].lower()


async def test_embedding_unavailable_returns_503(auth_client, indexed_document):
    import openai as oai

    mock_emb = AsyncMock(side_effect=oai.OpenAIError("embedding outage"))

    with patch("app.routers.query.generate_embeddings", new=mock_emb):
        response = await auth_client.post(
            "/query", json={"question": "leave days?"}
        )

    assert response.status_code == 503
    assert "openai" not in response.json()["detail"].lower()


# ── Deleted document excluded ─────────────────────────────────────────────────


async def test_deleted_document_excluded(auth_client, db, test_user):
    from datetime import UTC, datetime

    doc = Document(
        title="Deleted Doc",
        owner_id=test_user.id,
        source_type="upload",
        deleted_at=datetime.now(UTC),
    )
    db.add(doc)
    await db.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        status="ACTIVE",
        content_hash=secrets.token_hex(16),
        storage_key=f"uploads/{doc.id}/v1.txt",
    )
    db.add(version)
    await db.flush()

    content = "This document was deleted and should not appear."
    await db.execute(
        update(DocumentVersion)
        .where(DocumentVersion.id == version.id)
        .values(search_vector=func.to_tsvector("english", content))
    )
    chunk = DocumentChunk(
        document_version_id=version.id,
        chunk_index=0,
        content=content,
        embedding=_fake_embedding(),
        token_count=10,
    )
    db.add(chunk)
    await db.commit()

    mock_emb = _mock_embedding_call()
    mock_chat = _mock_chat_call(
        answer="I don't have enough information to answer that question.",
        citations=[],
    )

    with _openai_ctx(mock_emb, mock_chat):
        response = await auth_client.post(
            "/query",
            json={"question": "deleted document content"},
        )

    assert response.status_code == 200
    data = response.json()
    for citation in data["citations"]:
        assert citation["document_title"] != "Deleted Doc"


# ── Version filtering ─────────────────────────────────────────────────────────


async def test_current_mode_excludes_superseded(auth_client, db, test_user):
    doc = Document(
        title="Policy v1",
        owner_id=test_user.id,
        source_type="upload",
    )
    db.add(doc)
    await db.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        status="SUPERSEDED",
        content_hash=secrets.token_hex(16),
        storage_key=f"uploads/{doc.id}/v1.txt",
    )
    db.add(version)
    await db.flush()

    content = "Old superseded policy content unique_superseded_text_xyz."
    await db.execute(
        update(DocumentVersion)
        .where(DocumentVersion.id == version.id)
        .values(search_vector=func.to_tsvector("english", content))
    )
    chunk = DocumentChunk(
        document_version_id=version.id,
        chunk_index=0,
        content=content,
        embedding=_fake_embedding(),
        token_count=10,
    )
    db.add(chunk)
    await db.commit()

    mock_emb = _mock_embedding_call()
    mock_chat = _mock_chat_call(
        answer="I don't have enough information to answer that question.",
        citations=[],
    )

    with _openai_ctx(mock_emb, mock_chat):
        response = await auth_client.post(
            "/query",
            json={"question": "unique_superseded_text_xyz", "mode": "current"},
        )

    assert response.status_code == 200
    for citation in response.json()["citations"]:
        assert citation["document_title"] != "Policy v1"


async def test_historical_mode_includes_superseded(auth_client, db, test_user):
    doc = Document(
        title="Historical Policy",
        owner_id=test_user.id,
        source_type="upload",
    )
    db.add(doc)
    await db.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        status="SUPERSEDED",
        content_hash=secrets.token_hex(16),
        storage_key=f"uploads/{doc.id}/v1.txt",
    )
    db.add(version)
    await db.flush()

    content = "Historical leave entitlement was 20 days per year."
    await db.execute(
        update(DocumentVersion)
        .where(DocumentVersion.id == version.id)
        .values(search_vector=func.to_tsvector("english", content))
    )
    chunk = DocumentChunk(
        document_version_id=version.id,
        chunk_index=0,
        content=content,
        embedding=_fake_embedding(),
        token_count=10,
    )
    db.add(chunk)
    await db.commit()

    mock_emb = _mock_embedding_call()
    mock_chat = _mock_chat_call(
        answer="Historical: 20 days.",
        citations=[{"document_title": "Historical Policy", "version_number": 1}],
    )

    with _openai_ctx(mock_emb, mock_chat):
        response = await auth_client.post(
            "/query",
            json={"question": "historical leave entitlement", "mode": "historical"},
        )

    assert response.status_code == 200
    titles = [c["document_title"] for c in response.json()["citations"]]
    assert "Historical Policy" in titles


# ── Permission isolation ──────────────────────────────────────────────────────


async def test_restricted_document_not_visible_to_other_user(auth_client, db, test_user):
    """User A must never see User B's document in query results."""
    # Create User B and their document.
    user_b = User(
        email=f"userb+{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password"),
        role="user",
    )
    db.add(user_b)
    await db.flush()

    doc_b = Document(
        title="User B Confidential",
        owner_id=user_b.id,
        source_type="upload",
    )
    db.add(doc_b)
    await db.flush()

    version_b = DocumentVersion(
        document_id=doc_b.id,
        version_number=1,
        status="ACTIVE",
        content_hash=secrets.token_hex(16),
        storage_key=f"uploads/{doc_b.id}/v1.txt",
    )
    db.add(version_b)
    await db.flush()

    content_b = "User B secret: the code is hunter2."
    await db.execute(
        update(DocumentVersion)
        .where(DocumentVersion.id == version_b.id)
        .values(search_vector=func.to_tsvector("english", content_b))
    )
    chunk_b = DocumentChunk(
        document_version_id=version_b.id,
        chunk_index=0,
        content=content_b,
        embedding=_fake_embedding(),
        token_count=10,
    )
    db.add(chunk_b)
    await db.commit()

    # Query as test_user (User A) — must not see User B's content.
    mock_emb = _mock_embedding_call()
    mock_chat = _mock_chat_call(
        answer="I don't have enough information to answer that question.",
        citations=[],
    )

    with _openai_ctx(mock_emb, mock_chat):
        response = await auth_client.post(
            "/query",
            json={"question": "User B secret code"},
        )

    assert response.status_code == 200
    for citation in response.json()["citations"]:
        assert citation["document_title"] != "User B Confidential"

    # Cleanup User B's data.
    await db.execute(
        delete(DocumentChunk).where(DocumentChunk.document_version_id == version_b.id)
    )
    await db.execute(delete(DocumentVersion).where(DocumentVersion.id == version_b.id))
    await db.execute(delete(Document).where(Document.id == doc_b.id))
    await db.execute(delete(User).where(User.id == user_b.id))
    await db.commit()


async def test_restricted_document_not_visible_historical_mode(auth_client, db, test_user):
    """Permission isolation must hold for mode=historical too."""
    user_c = User(
        email=f"userc+{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password"),
        role="user",
    )
    db.add(user_c)
    await db.flush()

    doc_c = Document(
        title="User C Old Document",
        owner_id=user_c.id,
        source_type="upload",
    )
    db.add(doc_c)
    await db.flush()

    version_c = DocumentVersion(
        document_id=doc_c.id,
        version_number=1,
        status="SUPERSEDED",
        content_hash=secrets.token_hex(16),
        storage_key=f"uploads/{doc_c.id}/v1.txt",
    )
    db.add(version_c)
    await db.flush()

    content_c = "User C private superseded content."
    await db.execute(
        update(DocumentVersion)
        .where(DocumentVersion.id == version_c.id)
        .values(search_vector=func.to_tsvector("english", content_c))
    )
    chunk_c = DocumentChunk(
        document_version_id=version_c.id,
        chunk_index=0,
        content=content_c,
        embedding=_fake_embedding(),
        token_count=10,
    )
    db.add(chunk_c)
    await db.commit()

    mock_emb = _mock_embedding_call()
    mock_chat = _mock_chat_call(
        answer="I don't have enough information to answer that question.",
        citations=[],
    )

    with _openai_ctx(mock_emb, mock_chat):
        response = await auth_client.post(
            "/query",
            json={"question": "User C private content", "mode": "historical"},
        )

    assert response.status_code == 200
    for citation in response.json()["citations"]:
        assert citation["document_title"] != "User C Old Document"

    # Cleanup.
    await db.execute(
        delete(DocumentChunk).where(DocumentChunk.document_version_id == version_c.id)
    )
    await db.execute(delete(DocumentVersion).where(DocumentVersion.id == version_c.id))
    await db.execute(delete(Document).where(Document.id == doc_c.id))
    await db.execute(delete(User).where(User.id == user_c.id))
    await db.commit()
