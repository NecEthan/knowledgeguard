import hashlib
import uuid

from fastapi import HTTPException, UploadFile

from app.config import settings

# Magic-byte signatures for supported types
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_MAGIC: dict[bytes, str] = {
    b"\x25\x50\x44\x46": "application/pdf",
    b"\x50\x4b\x03\x04": _DOCX,
}

ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    ]
)


async def read_and_validate(file: UploadFile) -> tuple[bytes, str]:
    """Read the upload, enforce size limit, detect real content type.

    Returns (content_bytes, detected_content_type).
    Raises HTTPException on violations.
    """
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    content: bytes = await file.read(max_bytes + 1)

    if len(content) == 0:
        raise HTTPException(status_code=422, detail="File is empty")

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.max_upload_size_mb} MB limit",
        )

    # Check magic bytes
    header = content[:4]
    detected = _MAGIC.get(header)

    if detected is None:
        # Try to classify as plain text (valid UTF-8, no null bytes)
        try:
            content.decode("utf-8")
            if b"\x00" not in content:
                detected = "text/plain"
        except UnicodeDecodeError:
            pass

    if detected is None or detected not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported file type")

    return content, detected


def detect_content_type(content: bytes) -> str:
    """Detect content type from magic bytes. Returns 'text/plain' for valid UTF-8 text."""
    header = content[:4]
    detected = _MAGIC.get(header)
    if detected is not None:
        return detected
    try:
        content.decode("utf-8")
        if b"\x00" not in content:
            return "text/plain"
    except UnicodeDecodeError:
        pass
    return "application/octet-stream"


def compute_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def generate_storage_key() -> str:
    return f"documents/{uuid.uuid4()}"
