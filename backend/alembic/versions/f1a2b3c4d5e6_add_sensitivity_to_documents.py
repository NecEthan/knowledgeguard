"""add sensitivity to documents

Revision ID: f1a2b3c4d5e6
Revises: e5c1d7b2a0f4
Create Date: 2026-09-24

"""

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e5c1d7b2a0f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("sensitivity", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("documents", "sensitivity")
