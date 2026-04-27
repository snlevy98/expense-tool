"""add budget_settings table

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-04-27 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "budget_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "pool_pct",
            sa.Numeric(precision=5, scale=4),
            nullable=False,
            server_default="0.8000",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Insert the single default settings row
    op.execute(
        "INSERT INTO budget_settings (id, pool_pct) VALUES (gen_random_uuid(), 0.8000)"
    )


def downgrade() -> None:
    op.drop_table("budget_settings")
