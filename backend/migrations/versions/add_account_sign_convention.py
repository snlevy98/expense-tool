"""add accounts.sign_convention

Revision ID: b7e8f9a0c1d2
Revises: f0a1b2c3d4e5
Create Date: 2026-06-13 00:00:00.000000

Backfills a migration for accounts.sign_convention, which was added to the
model (and applied directly to the hosted DB) without one — so a database
built from scratch via `alembic upgrade head` was missing the column. Written
idempotently (ADD COLUMN IF NOT EXISTS) so it is a safe no-op on any DB where
the column already exists.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b7e8f9a0c1d2"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS sign_convention "
        "VARCHAR(20) NOT NULL DEFAULT 'positive_expense'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE accounts DROP COLUMN IF EXISTS sign_convention")
