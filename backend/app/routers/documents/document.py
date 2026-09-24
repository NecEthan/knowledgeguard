import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_current_user, get_db, sensitivity_filters
from app.models.base import (
    AuditEvent,
    Document,
    DocumentChunk,
    DocumentVersion,
    ProcessingJob,
    User,
)
from app.schemas.documents import (
    DocumentDetailResponse,
    DocumentResponse,
    DocumentUpdateRequest,
)

router = APIRouter(tags=["documents"])


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentDetailResponse:
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(*sensitivity_filters(current_user))
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
        .where(*sensitivity_filters(current_user))
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.title = body.title
    await db.commit()
    return DocumentResponse.model_validate(doc)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .where(*sensitivity_filters(current_user))
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Subquery: all version IDs for this document.
    version_ids_stmt = select(DocumentVersion.id).where(
        DocumentVersion.document_id == document_id
    )

    # Emit audit event before deletion (document_id stored as plain UUID, no FK).
    db.add(
        AuditEvent(
            event_type="DOCUMENT_DELETED",
            user_id=current_user.id,
            document_id=document_id,
        )
    )

    # Delete children in FK-dependency order before deleting parent rows.

    # 1. Chunks (FK → versions)
    await db.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_version_id.in_(version_ids_stmt)
        )
    )

    # 2. Processing jobs (FK → versions)
    await db.execute(
        delete(ProcessingJob).where(
            ProcessingJob.document_version_id.in_(version_ids_stmt)
        )
    )

    # 3. Versions (FK → document)
    await db.execute(
        delete(DocumentVersion).where(
            DocumentVersion.document_id == document_id
        )
    )

    # 4. Document.
    await db.execute(delete(Document).where(Document.id == document_id))

    await db.commit()
    return Response(status_code=204)
