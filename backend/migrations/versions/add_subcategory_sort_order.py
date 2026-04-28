"""add sort_order to subcategories

Revision ID: a1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Create Date: 2026-04-28 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subcategories",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    # Initialise sort_order for existing rows using row_number within each category,
    # ordered by created_at so the visual order matches insertion order.
    op.execute(
        """
        UPDATE subcategories s
        SET sort_order = ranked.rn
        FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY category_id ORDER BY created_at
                   ) - 1 AS rn
            FROM subcategories
        ) ranked
        WHERE s.id = ranked.id
        """
    )


def downgrade() -> None:
    op.drop_column("subcategories", "sort_order")
