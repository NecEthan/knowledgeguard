"""Add search_vector to document_versions

Revision ID: d2e8f3a1b9c7
Revises: c067b287a0e3
Create Date: 2026-09-22 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d2e8f3a1b9c7"
down_revision: str | None = "c067b287a0e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
    )
    op.create_index(
        "ix_document_versions_search_vector",
        "document_versions",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_versions_search_vector",
        table_name="document_versions",
    )
    op.drop_column("document_versions", "search_vector")
