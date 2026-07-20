"""expression index for effective-subcategory Spent aggregation

Unreviewed transactions now count under their AI-suggested subcategory
(effective categorization). The Spent queries group/filter on
CASE WHEN category_id IS NULL THEN ai_suggested_subcategory_id
     ELSE subcategory_id END,
so the covering index must match that expression.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX ix_transactions_effective_subcat_date ON transactions (
            (CASE WHEN category_id IS NULL
                  THEN ai_suggested_subcategory_id
                  ELSE subcategory_id END),
            transaction_date,
            budget_excluded
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_transactions_effective_subcat_date")
