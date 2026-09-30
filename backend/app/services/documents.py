import hashlib
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def assert_no_duplicate(db: AsyncSession, content_hash: str) -> None:
    from app.models.base import DocumentVersion

    result = await db.execute(
        select(DocumentVersion).where(DocumentVersion.content_hash == content_hash)
    )
    if result.scalars().first() is not None:
        raise HTTPException(status_code=409, detail="Document with identical content already exists")


async def create_document_records(
    db: AsyncSession,
    title: str,
    sensitivity: str,
    content_hash: str,
    storage_key: str,
    current_user,
):
    from app.models.base import AuditEvent, Document, DocumentVersion, ProcessingJob

    doc = Document(
        title=title,
        owner_id=current_user.id,
        source_type="upload",
        sensitivity=sensitivity,
    )
    db.add(doc)
    await db.flush()

    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        status="PROCESSING",
        content_hash=content_hash,
        storage_key=storage_key,
        created_by=current_user.id,
    )
    db.add(version)
    await db.flush()

    job = ProcessingJob(document_version_id=version.id, status="QUEUED")
    db.add(job)
    db.add(AuditEvent(event_type="DOCUMENT_UPLOADED", user_id=current_user.id, document_id=doc.id))
    db.add(AuditEvent(event_type="VERSION_CREATED", user_id=current_user.id, document_id=doc.id, version_id=version.id))
    await db.commit()

    return doc, version, job
