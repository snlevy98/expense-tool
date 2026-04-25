"""add ai_enriched to transactions

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-25 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'transactions',
        sa.Column('ai_enriched', sa.Boolean(), nullable=False, server_default='false'),
    )
    # Partial index — only covers unenriched rows so it stays small as rows get processed
    op.create_index(
        'ix_transactions_ai_enriched_false',
        'transactions',
        ['ai_enriched'],
        postgresql_where=sa.text('ai_enriched = false'),
    )


def downgrade() -> None:
    op.drop_index('ix_transactions_ai_enriched_false', table_name='transactions')
    op.drop_column('transactions', 'ai_enriched')
