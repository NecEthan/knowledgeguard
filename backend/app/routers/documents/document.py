import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_current_user, get_db, sensitivity_filters
from app.models.base import Document, User
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
        .where(Document.deleted_at.is_(None))
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
        .where(Document.deleted_at.is_(None))
        .where(*sensitivity_filters(current_user))
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.title = body.title
    await db.commit()
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
        .where(Document.deleted_at.is_(None))
        .where(*sensitivity_filters(current_user))
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.deleted_at = datetime.now(UTC)
    await db.commit()
    return Response(status_code=204)
