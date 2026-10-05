import asyncio

import structlog
from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_arq_pool, get_current_user, get_db, sensitivity_filters
from app.models.base import AuditEvent, Document, User
from app.schemas.documents import DocumentResponse, DocumentUploadedResponse
from app.services import storage
from app.services.documents import (
    assert_no_duplicate,
    compute_hash,
    create_document_records,
    generate_storage_key,
    read_and_validate,
)
from app.utils.enqueue import enqueue_processing_job

router = APIRouter(tags=["documents"])
logger = structlog.get_logger(__name__)

_VALID_SENSITIVITIES = {"STANDARD", "SENSITIVE"}


async def _check_sensitivity_permission(
    sensitivity: str, current_user: User, db: AsyncSession
) -> None:
    if sensitivity not in _VALID_SENSITIVITIES:
        raise HTTPException(
            status_code=422,
            detail=f"sensitivity must be one of {sorted(_VALID_SENSITIVITIES)}",
        )
    if sensitivity == "SENSITIVE" and current_user.role != "admin":
        db.add(
            AuditEvent(
                event_type="PERMISSION_DENIED",
                user_id=current_user.id,
                metadata_={"action": "upload_sensitive_document"},
            )
        )
        await db.commit()
        raise HTTPException(status_code=403, detail="Only admins can upload sensitive documents")


@router.post("", status_code=202, response_model=DocumentUploadedResponse)
async def upload_document(
    file: UploadFile,
    title: str = Form(),
    sensitivity: str = Form(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    arq_pool: ArqRedis = Depends(get_arq_pool),
) -> DocumentUploadedResponse:
    logger.info("document_upload_start", filename=file.filename, sensitivity=sensitivity)

    await _check_sensitivity_permission(sensitivity, current_user, db)

    content, content_type = await read_and_validate(file)
    content_hash = compute_hash(content)
    await assert_no_duplicate(db, content_hash)

    storage_key = generate_storage_key()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, storage.upload_bytes, storage_key, content, content_type)
    await loop.run_in_executor(None, storage.tag_as_orphan, storage_key)

    try:
        doc, version, job = await create_document_records(
            db, title, sensitivity, content_hash, storage_key, current_user
        )
    except Exception:
        await db.rollback()
        await loop.run_in_executor(None, storage.delete_object, storage_key)
        raise

    await loop.run_in_executor(None, storage.confirm_object, storage_key)
    await enqueue_processing_job(arq_pool, db, job, version.id)

    return DocumentUploadedResponse(id=doc.id, status="accepted")


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DocumentResponse]:
    result = await db.execute(
        select(Document)
        .where(*sensitivity_filters(current_user))
        .order_by(Document.created_at.desc())
    )
    return [DocumentResponse.model_validate(d) for d in result.scalars().all()]
