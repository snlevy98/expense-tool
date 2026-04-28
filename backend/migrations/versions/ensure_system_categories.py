"""ensure Income and Investments are marked budget_excluded=True

Revision ID: e9f0a1b2c3d4
Revises: d7e8f9a0b1c2
Create Date: 2026-04-28 00:00:00.000000

Marks existing Income / Investments categories as budget_excluded=True.
Creates them if they are missing entirely.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SYSTEM = [
    ("Income",      "#A8E8B0"),
    ("Investments", "#D4B8D8"),
]


def upgrade() -> None:
    conn = op.get_bind()

    for name, color in _SYSTEM:
        row = conn.execute(
            sa.text("SELECT id FROM categories WHERE LOWER(name) = LOWER(:name) LIMIT 1"),
            {"name": name},
        ).fetchone()

        if row:
            # Update existing category to mark it as budget_excluded
            conn.execute(
                sa.text(
                    "UPDATE categories SET budget_excluded = TRUE WHERE id = :id"
                ),
                {"id": row[0]},
            )
        else:
            # Create the missing system category
            conn.execute(
                sa.text(
                    """
                    INSERT INTO categories (id, name, color, is_active, budget_excluded, created_at, updated_at)
                    VALUES (gen_random_uuid(), :name, :color, TRUE, TRUE, NOW(), NOW())
                    """
                ),
                {"name": name, "color": color},
            )


def downgrade() -> None:
    # Revert: unmark both categories (does NOT delete them if they were created)
    conn = op.get_bind()
    for name, _ in _SYSTEM:
        conn.execute(
            sa.text(
                "UPDATE categories SET budget_excluded = FALSE WHERE LOWER(name) = LOWER(:name)"
            ),
            {"name": name},
        )
