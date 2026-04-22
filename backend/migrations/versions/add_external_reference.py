"""add external_reference to transactions

Revision ID: a1b2c3d4e5f6
Revises: 9cfc39e4dbfa
Create Date: 2026-04-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9cfc39e4dbfa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'transactions',
        sa.Column('external_reference', sa.String(length=200), nullable=True),
    )
    op.create_index(
        'ix_transactions_external_reference',
        'transactions',
        ['external_reference'],
    )


def downgrade() -> None:
    op.drop_index('ix_transactions_external_reference', table_name='transactions')
    op.drop_column('transactions', 'external_reference')
