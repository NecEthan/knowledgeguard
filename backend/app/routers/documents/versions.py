import asyncio
import uuid

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_arq_pool, get_current_user, get_db, sensitivity_filters
from app.models.base import AuditEvent, Document, DocumentVersion, ProcessingJob, User
from app.schemas.documents import DocumentVersionResponse, VersionUploadedResponse
from app.services import storage
from app.services.documents import compute_hash, generate_storage_key, read_and_validate
from app.utils.enqueue import enqueue_processing_job

router = APIRouter(tags=["documents"])


@router.post(
    "/{document_id}/versions",
    status_code=202,
    response_model=VersionUploadedResponse,
)
async def upload_document_version(
    document_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    arq_pool: ArqRedis = Depends(get_arq_pool),
) -> VersionUploadedResponse:
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(*sensitivity_filters(current_user))
        .where(Document.deleted_at.is_(None))
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Document not found")

    content, content_type = await read_and_validate(file)
    content_hash = compute_hash(content)
    storage_key = generate_storage_key()

    # upload file in separate thread to avoid blocking the asynchronous event loop
    # because it calls api to upload the file to miniO server
    # we allow other requests to be made while this uploads completes
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, storage.upload_bytes, storage_key, content, content_type
    )

    try:
        # get max number of existing versions for this document to determine the next version number
        ver_result = await db.execute(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == document_id
            )
        )
        max_ver = ver_result.scalar_one_or_none() or 0

        version = DocumentVersion(
            document_id=document_id,
            version_number=max_ver + 1,
            status="PROCESSING",
            content_hash=content_hash,
            storage_key=storage_key,
            created_by=current_user.id,
        )
        db.add(version)
        await db.flush()

        job = ProcessingJob(document_version_id=version.id, status="QUEUED")
        db.add(job)

        db.add(
            AuditEvent(
                event_type="VERSION_CREATED",
                user_id=current_user.id,
                document_id=document_id,
                version_id=version.id,
            )
        )

        await db.commit()
    except Exception:
        await db.rollback()
        await loop.run_in_executor(None, storage.delete_object, storage_key)
        raise

    await enqueue_processing_job(arq_pool, db, job, version.id)

    return VersionUploadedResponse(
        id=version.id,
        document_id=document_id,
        version_number=version.version_number,
        status="accepted",
    )


@router.get(
    "/{document_id}/versions",
    response_model=list[DocumentVersionResponse],
)
async def list_document_versions(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DocumentVersionResponse]:
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(*sensitivity_filters(current_user))
        .where(Document.deleted_at.is_(None))
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
    )
    return [DocumentVersionResponse.model_validate(v) for v in result.scalars().all()]


@router.get(
    "/{document_id}/versions/{version_id}",
    response_model=DocumentVersionResponse,
)
async def get_document_version(
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentVersionResponse:
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(*sensitivity_filters(current_user))
        .where(Document.deleted_at.is_(None))
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.id == version_id)
        .where(DocumentVersion.document_id == document_id)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")

    return DocumentVersionResponse.model_validate(version)
