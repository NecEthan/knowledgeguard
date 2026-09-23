"""add unique constraint document_chunks

Revision ID: e5c1d7b2a0f4
Revises: d2e8f3a1b9c7
Create Date: 2026-09-23

"""

from alembic import op

revision = "e5c1d7b2a0f4"
down_revision = "d2e8f3a1b9c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_document_chunk_version_index",
        "document_chunks",
        ["document_version_id", "chunk_index"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_document_chunk_version_index", "document_chunks", type_="unique"
    )
