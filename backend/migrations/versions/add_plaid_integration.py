"""add plaid_items table and plaid columns on accounts

Revision ID: c8d9e0f1a2b3
Revises: b7e8f9a0c1d2
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b7e8f9a0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plaid_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", sa.String(length=100), nullable=False, unique=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("institution_id", sa.String(length=50), nullable=True),
        sa.Column(
            "institution_name", sa.String(length=200), nullable=False,
            server_default="",
        ),
        sa.Column("sync_cursor", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "plaid_item_id", UUID(as_uuid=True),
            sa.ForeignKey("plaid_items.id"), nullable=True,
        ),
    )
    op.add_column(
        "accounts",
        sa.Column("plaid_account_id", sa.String(length=100), nullable=True),
    )
    op.create_unique_constraint(
        "uq_accounts_plaid_account_id", "accounts", ["plaid_account_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_accounts_plaid_account_id", "accounts", type_="unique")
    op.drop_column("accounts", "plaid_account_id")
    op.drop_column("accounts", "plaid_item_id")
    op.drop_table("plaid_items")
