import pytest

from app.services.documents import (
    ALLOWED_CONTENT_TYPES,
    compute_hash,
    generate_storage_key,
    read_and_validate,
)

_DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class MockUploadFile:
    def __init__(self, content: bytes) -> None:
        self._content = content

    async def read(self, size: int = -1) -> bytes:
        if size == -1:
            return self._content
        return self._content[:size]


# compute_hash


def test_compute_hash_is_sha256_hex():
    h = compute_hash(b"hello")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_compute_hash_deterministic():
    assert compute_hash(b"same") == compute_hash(b"same")


def test_compute_hash_differs_for_different_content():
    assert compute_hash(b"a") != compute_hash(b"b")


# generate_storage_key


def test_generate_storage_key_prefix():
    assert generate_storage_key().startswith("documents/")


def test_generate_storage_key_unique():
    assert generate_storage_key() != generate_storage_key()


# read_and_validate


@pytest.mark.asyncio
async def test_validates_pdf():
    content = b"\x25\x50\x44\x46" + b" rest of pdf"
    _, ct = await read_and_validate(MockUploadFile(content))
    assert ct == "application/pdf"


@pytest.mark.asyncio
async def test_validates_docx():
    content = b"\x50\x4b\x03\x04" + b" rest of docx"
    _, ct = await read_and_validate(MockUploadFile(content))
    assert ct == _DOCX_CT


@pytest.mark.asyncio
async def test_validates_plain_text():
    content = b"Hello, this is plain text."
    _, ct = await read_and_validate(MockUploadFile(content))
    assert ct == "text/plain"


@pytest.mark.asyncio
async def test_rejects_empty_file():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await read_and_validate(MockUploadFile(b""))
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_rejects_unsupported_binary():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await read_and_validate(MockUploadFile(bytes(range(256)) * 10))
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_rejects_oversized_file(monkeypatch):
    from fastapi import HTTPException

    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_size_mb", 0)
    with pytest.raises(HTTPException) as exc:
        await read_and_validate(MockUploadFile(b"x" * 2))
    assert exc.value.status_code == 413


# ALLOWED_CONTENT_TYPES
def test_allowed_content_types_contains_expected():
    assert "application/pdf" in ALLOWED_CONTENT_TYPES
    assert "text/plain" in ALLOWED_CONTENT_TYPES
    assert "new/type" not in ALLOWED_CONTENT_TYPES
