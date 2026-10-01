from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.document_chunk import DocumentChunk
    from app.models.processing_job import ProcessingJob

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # PROCESSING | ACTIVE | SUPERSEDED | DELETED | REVIEW_REQUIRED | FAILED
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    search_vector: Mapped[Any | None] = mapped_column(TSVECTOR, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="versions")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="version")
    processing_jobs: Mapped[list["ProcessingJob"]] = relationship(
        back_populates="document_version"
    )

    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version"),
        Index("ix_document_versions_document_id", "document_id"),
        Index(
            "one_active_version_per_document",
            "document_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )
