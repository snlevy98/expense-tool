"""envelope budgeting: locks, budget months, saved balances, exclusions

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-06-12 00:00:00.000000

Implements the v1.3 budgeting requirements schema (doc §4):
- budgets.locked + $0-row cleanup + CHECK (amount > 0)
- budget_months lifecycle/settlement registry
- saved_balances + saved_balance_events (with settle-once partial unique index)
- budget_exclusion_rules
- transactions.budget_excluded(+source) + aggregation index
- retires the pool model (drops budget_settings, budget_defaults)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── transactions: budget exclusion flag (FR-4.2) ────────────────────────
    op.add_column(
        "transactions",
        sa.Column("budget_excluded", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "transactions",
        sa.Column("budget_excluded_source", sa.String(length=10), nullable=True),
    )
    op.create_index(
        "ix_transactions_subcat_date",
        "transactions",
        ["subcategory_id", "transaction_date", "budget_excluded"],
    )

    # ── budgets: lock flag + opt-in cleanup (FR-1.1, FR-1.7) ────────────────
    op.add_column(
        "budgets",
        sa.Column("locked", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Legacy auto-seeded $0 rows meant "shown but unbudgeted"; under opt-in
    # semantics row presence = budgeted, so they must go before the CHECK.
    op.execute("DELETE FROM budgets WHERE amount = 0")
    op.create_check_constraint("ck_budgets_amount_positive", "budgets", "amount > 0")

    # ── budget_months: lifecycle/settlement registry (FR-2.1–2.3) ───────────
    op.create_table(
        "budget_months",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("month", "year", name="uq_budget_months_month_year"),
    )

    # ── saved_balances (FR-3.1) ──────────────────────────────────────────────
    op.create_table(
        "saved_balances",
        sa.Column("subcategory_id", UUID(as_uuid=True), nullable=False),
        sa.Column("balance", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["subcategory_id"], ["subcategories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("subcategory_id"),
        sa.CheckConstraint("balance >= 0", name="ck_saved_balances_non_negative"),
    )

    # ── saved_balance_events: audit trail (NFR-5) ────────────────────────────
    op.create_table(
        "saved_balance_events",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("subcategory_id", UUID(as_uuid=True), nullable=False),
        sa.Column("delta", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("balance_after", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["subcategory_id"], ["subcategories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_saved_balance_events_subcategory_id",
        "saved_balance_events",
        ["subcategory_id"],
    )
    # Settle-once idempotency backstop (NFR-2): at most one settlement event
    # per (subcategory, month). Recompute events are exempt (FR-4.4 allows many).
    op.execute(
        "CREATE UNIQUE INDEX uq_sbe_settlement "
        "ON saved_balance_events (subcategory_id, year, month) "
        "WHERE reason IN ('month_close_surplus', 'month_close_coverage')"
    )

    # ── budget_exclusion_rules (FR-4.3) ──────────────────────────────────────
    op.create_table(
        "budget_exclusion_rules",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("rule_type", sa.String(length=20), nullable=False),
        sa.Column("match_value", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── pool model retirement (doc §10) ──────────────────────────────────────
    op.drop_table("budget_settings")
    op.drop_table("budget_defaults")


def downgrade() -> None:
    op.create_table(
        "budget_defaults",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", UUID(as_uuid=True), nullable=False),
        sa.Column("default_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", name="uq_budget_default_category"),
    )
    op.create_table(
        "budget_settings",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("pool_pct", sa.Numeric(precision=5, scale=4), nullable=False, server_default="0.8"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.drop_table("budget_exclusion_rules")
    op.execute("DROP INDEX IF EXISTS uq_sbe_settlement")
    op.drop_index("ix_saved_balance_events_subcategory_id", table_name="saved_balance_events")
    op.drop_table("saved_balance_events")
    op.drop_table("saved_balances")
    op.drop_table("budget_months")
    op.drop_constraint("ck_budgets_amount_positive", "budgets", type_="check")
    op.drop_column("budgets", "locked")
    op.drop_index("ix_transactions_subcat_date", table_name="transactions")
    op.drop_column("transactions", "budget_excluded_source")
    op.drop_column("transactions", "budget_excluded")
