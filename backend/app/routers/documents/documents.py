import asyncio
import uuid

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_arq_pool, get_current_user, get_db
from app.models.base import Document, DocumentVersion, ProcessingJob, User
from app.schemas.documents import DocumentResponse, DocumentUploadedResponse
from app.services import storage
from app.services.documents import compute_hash, generate_storage_key, read_and_validate
from app.utils.enqueue import enqueue_processing_job

router = APIRouter(tags=["documents"])


@router.post("", status_code=202, response_model=DocumentUploadedResponse)
async def upload_document(
    file: UploadFile,
    title: str = Form(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    arq_pool: ArqRedis = Depends(get_arq_pool),
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
    except Exception:
        await db.rollback()
        await loop.run_in_executor(None, storage.delete_object, storage_key)
        raise

    await enqueue_processing_job(arq_pool, db, job, version.id)

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
