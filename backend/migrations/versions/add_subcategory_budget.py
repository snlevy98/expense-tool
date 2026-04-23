"""add subcategory budget support

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add subcategory_id column to budgets (nullable)
    op.add_column(
        "budgets",
        sa.Column("subcategory_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_budgets_subcategory_id",
        "budgets",
        "subcategories",
        ["subcategory_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 2. Replace the old blanket unique constraint with two partial unique indexes.
    #    PostgreSQL treats NULLs as distinct in unique indexes, so we need
    #    separate partial indexes to get the right semantics.
    op.drop_constraint("uq_budget_category_month_year", "budgets", type_="unique")

    # Unique category budget when no subcategory is involved
    op.execute(
        "CREATE UNIQUE INDEX uq_budget_cat_month_year_no_sub "
        "ON budgets (category_id, month, year) "
        "WHERE subcategory_id IS NULL"
    )
    # Unique subcategory budget per month/year
    op.execute(
        "CREATE UNIQUE INDEX uq_budget_sub_month_year "
        "ON budgets (subcategory_id, month, year) "
        "WHERE subcategory_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_budget_sub_month_year")
    op.execute("DROP INDEX IF EXISTS uq_budget_cat_month_year_no_sub")
    op.create_unique_constraint(
        "uq_budget_category_month_year", "budgets", ["category_id", "month", "year"]
    )
    op.drop_constraint("fk_budgets_subcategory_id", "budgets", type_="foreignkey")
    op.drop_column("budgets", "subcategory_id")
