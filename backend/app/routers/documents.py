import asyncio
import logging
import uuid
from datetime import UTC, datetime

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.dependencies import get_current_user, get_db
from app.models.base import Document, DocumentVersion, ProcessingJob, User
from app.schemas.documents import (
    DocumentDetailResponse,
    DocumentResponse,
    DocumentUpdateRequest,
    DocumentUploadedResponse,
)
from app.services import storage
from app.services.documents import compute_hash, generate_storage_key, read_and_validate

router = APIRouter(tags=["documents"])
logger = logging.getLogger(__name__)


async def _enqueue_processing(document_version_id: str) -> None:
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    await pool.enqueue_job("process_document", document_version_id)
    await pool.aclose()


@router.post("", status_code=202, response_model=DocumentUploadedResponse)
async def upload_document(
    file: UploadFile,
    title: str = Form(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentUploadedResponse:
    content, content_type = await read_and_validate(file)
    content_hash = compute_hash(content)
    storage_key = generate_storage_key()

    # upload file in separate thread to avoid blocking the asynchronous event loop
    # because it calls api to upload the file to miniO server
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, storage.upload_bytes, storage_key, content, content_type
    )

    try:
        doc = Document(
            title=title,
            owner_id=current_user.id,
            source_type="upload",
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

        job = ProcessingJob(
            document_version_id=version.id,
            status="QUEUED",
        )
        db.add(job)
        await db.commit()
        await db.refresh(doc)
    except Exception:
        await db.rollback()
        await loop.run_in_executor(None, storage.delete_object, storage_key)
        raise

    # Best-effort enqueue: if Redis is down the job stays QUEUED and the
    # background poller in main.py will re-enqueue it once Redis recovers.
    try:
        await _enqueue_processing(str(version.id))
        job.status = "DISPATCHED"
        await db.commit()
    except Exception:
        logger.exception("failed to enqueue job %s — poller will retry", job.id)

    return DocumentUploadedResponse(id=doc.id, status="accepted")


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DocumentResponse]:
    result = await db.execute(
        select(Document)
        .where(Document.owner_id == current_user.id)
        .where(Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc())
    )
    return [DocumentResponse.model_validate(d) for d in result.scalars().all()]


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentDetailResponse:
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.owner_id == current_user.id)
        .where(Document.deleted_at.is_(None))
        .options(selectinload(Document.versions))
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentDetailResponse.model_validate(doc)


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: uuid.UUID,
    body: DocumentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.owner_id == current_user.id)
        .where(Document.deleted_at.is_(None))
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.title = body.title
    await db.commit()
    await db.refresh(doc)
    return DocumentResponse.model_validate(doc)

# soft delete
@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(Document.owner_id == current_user.id)
        .where(Document.deleted_at.is_(None))
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.deleted_at = datetime.now(UTC)
    await db.commit()
    return Response(status_code=204)
