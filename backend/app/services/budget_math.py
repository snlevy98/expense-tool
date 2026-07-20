"""
Shared budget math — the single definition of "Spent" plus pure settlement
functions (requirements doc §4 Notes).

Spent for a subcategory-month is the SIGNED sum of its non-budget-excluded
transactions (positive = expense, negative = refund/credit), so refunds net
against spending (FR-4.1). Every consumer — budget dashboard, settlement,
recompute, reports, AI-suggestion inputs — must use these helpers rather than
rolling its own aggregation.

Unreviewed transactions count provisionally: a transaction with no confirmed
category (category_id IS NULL) is attributed to its AI-suggested subcategory
until the user reviews it in the Categorize tab. Once reviewed, only the
confirmed fields matter — a confirmed category with no subcategory does NOT
fall back to a stale AI suggestion. Consumers that group or filter by
category/subcategory must use effective_category_expr /
effective_subcategory_expr (or budget_lifecycle.budget_snapshot, which applies
the same rule) so the whole app agrees on where spend lands.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction

ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# Effective categorization (provisional AI attribution until reviewed)
# ---------------------------------------------------------------------------

def effective_category_expr():
    """SQL expression: confirmed category, or the AI suggestion when the
    transaction has not been reviewed yet."""
    return case(
        (Transaction.category_id.is_(None), Transaction.ai_suggested_category_id),
        else_=Transaction.category_id,
    )


def effective_subcategory_expr():
    """SQL expression: confirmed subcategory, or the AI-suggested subcategory
    when the transaction has not been reviewed yet (category_id IS NULL)."""
    return case(
        (Transaction.category_id.is_(None), Transaction.ai_suggested_subcategory_id),
        else_=Transaction.subcategory_id,
    )


def effective_subcategory_of(txn) -> uuid.UUID | None:
    """Python twin of effective_subcategory_expr for in-memory Transaction
    objects (used by budget_lifecycle.budget_snapshot)."""
    if txn.category_id is None:
        return txn.ai_suggested_subcategory_id
    return txn.subcategory_id


# ---------------------------------------------------------------------------
# Month helpers
# ---------------------------------------------------------------------------

def month_range(month: int, year: int) -> tuple[date, date]:
    """Return [start, end) date bounds for a calendar month."""
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def prev_month(month: int, year: int) -> tuple[int, int]:
    return (12, year - 1) if month == 1 else (month - 1, year)


def next_month(month: int, year: int) -> tuple[int, int]:
    return (1, year + 1) if month == 12 else (month + 1, year)


# ---------------------------------------------------------------------------
# Spent aggregation (FR-4.1, FR-4.2)
# ---------------------------------------------------------------------------

async def get_spent_by_subcategory(
    db: AsyncSession, month: int, year: int
) -> dict[uuid.UUID, Decimal]:
    """Netted Spent per effective subcategory for one month, excluding flagged
    transactions. Unreviewed spend counts under its AI-suggested subcategory."""
    start, end = month_range(month, year)
    effective_sub = effective_subcategory_expr()
    result = await db.execute(
        select(
            effective_sub.label("subcategory_id"),
            func.sum(Transaction.amount).label("total"),
        )
        .where(
            and_(
                effective_sub.isnot(None),
                Transaction.budget_excluded == False,  # noqa: E712
                Transaction.transaction_date >= start,
                Transaction.transaction_date < end,
            )
        )
        .group_by(effective_sub)
    )
    return {row.subcategory_id: Decimal(str(row.total)) for row in result.all()}


async def get_spent_for_subcategory_month(
    db: AsyncSession, subcategory_id: uuid.UUID, month: int, year: int
) -> Decimal:
    """Netted Spent for a single effective subcategory-month, excluding
    flagged transactions."""
    start, end = month_range(month, year)
    result = await db.execute(
        select(func.sum(Transaction.amount)).where(
            and_(
                effective_subcategory_expr() == subcategory_id,
                Transaction.budget_excluded == False,  # noqa: E712
                Transaction.transaction_date >= start,
                Transaction.transaction_date < end,
            )
        )
    )
    total = result.scalar_one_or_none()
    return Decimal(str(total)) if total is not None else ZERO


async def get_pending_spent_by_subcategory(
    db: AsyncSession, month: int, year: int
) -> dict[uuid.UUID, Decimal]:
    """The unreviewed slice of Spent per subcategory: transactions counted via
    their AI suggestion only (category_id IS NULL). Always a subset of
    get_spent_by_subcategory — used for the "pending review" indicator."""
    start, end = month_range(month, year)
    result = await db.execute(
        select(
            Transaction.ai_suggested_subcategory_id,
            func.sum(Transaction.amount).label("total"),
        )
        .where(
            and_(
                Transaction.category_id.is_(None),
                Transaction.ai_suggested_subcategory_id.isnot(None),
                Transaction.budget_excluded == False,  # noqa: E712
                Transaction.transaction_date >= start,
                Transaction.transaction_date < end,
            )
        )
        .group_by(Transaction.ai_suggested_subcategory_id)
    )
    return {
        row.ai_suggested_subcategory_id: Decimal(str(row.total))
        for row in result.all()
    }


# ---------------------------------------------------------------------------
# Pure settlement math (FR-2.3, FR-4.4) — unit-testable, no DB
# ---------------------------------------------------------------------------

def settlement_outcome(
    cap: Decimal, spent: Decimal, balance: Decimal
) -> tuple[Decimal, str | None]:
    """Month-close settlement for one subcategory (FR-2.3).

    Returns (delta, reason): surplus adds to the saved balance; covered
    overage (capped at the available balance, floor 0) deducts. Net overage
    beyond the balance carries nothing forward. (ZERO, None) when spent == cap
    or there is an overage but no balance to draw from.
    """
    remaining = cap - spent
    if remaining > 0:
        return remaining, "month_close_surplus"
    coverage = min(-remaining, balance)
    if coverage > 0:
        return -coverage, "month_close_coverage"
    return ZERO, None


def recompute_delta(
    cap: Decimal, spent: Decimal, applied: Decimal, balance: Decimal
) -> tuple[Decimal, Decimal]:
    """Compensating delta after a late edit to a settled month (FR-4.4).

    `applied` is the sum of settlement + recompute event deltas already
    applied for this (subcategory, month). The recomputed expectation is
    cap - spent (positive surplus / negative full coverage); the difference
    is clamped so the *current* balance never goes below zero — by design the
    clamp uses the current balance, which may include later months' surpluses
    (replaying the full event history in order is intentionally out of scope).

    Returns (actual_delta, discrepancy). discrepancy != 0 means part of the
    correction could not be drawn (balance floored at 0) and must be logged.
    """
    delta = (cap - spent) - applied
    actual = max(delta, -balance)
    return actual, delta - actual
