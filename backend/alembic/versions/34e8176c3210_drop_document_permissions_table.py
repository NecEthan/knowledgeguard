"""drop document_permissions table

Revision ID: 34e8176c3210
Revises: f1a2b3c4d5e6
Create Date: 2026-09-24 20:56:04.257808

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '34e8176c3210'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('document_permissions')


def downgrade() -> None:
    op.create_table(
        'document_permissions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('granted_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.ForeignKeyConstraint(['granted_by'], ['users.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_id', 'user_id', name='uq_document_user_permission'),
    )
