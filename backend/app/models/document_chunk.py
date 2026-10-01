import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list | None] = mapped_column(Vector(1536), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    version: Mapped["DocumentVersion"] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint(
            "document_version_id", "chunk_index", name="uq_document_chunk_version_index"
        ),
    )
