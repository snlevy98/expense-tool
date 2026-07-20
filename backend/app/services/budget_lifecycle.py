"""
Budget month lifecycle: lazy creation with copy-forward (FR-2.1/2.2),
idempotent month-close settlement (FR-2.3, NFR-2), and late-edit
reconciliation against settled months (FR-4.4).

Concurrency model (NFR-2): all materialization and settlement runs under a
single Postgres advisory transaction lock, with two DB-level backstops —
budget_months.settled_at is claimed via UPDATE ... WHERE settled_at IS NULL
RETURNING, and the partial unique index uq_sbe_settlement rejects a second
settlement event per (subcategory, month).
"""

import logging
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import Budget
from app.models.budget_month import BudgetMonth
from app.models.saved_balance import SavedBalance, SavedBalanceEvent
from app.services import budget_math
from app.services.budget_math import ZERO

logger = logging.getLogger(__name__)

# Single global lock key for all budget lifecycle work ("BUDG"). This is a
# single-user app; serializing materialization/settlement entirely is the
# simplest correct option.
_ADVISORY_LOCK_KEY = 0x42554447


def current_month_tuple() -> tuple[int, int]:
    today = date.today()
    return today.month, today.year


def is_closed_month(month: int, year: int) -> bool:
    """Closed months are read-only for caps and locks (FR-2.4)."""
    cur_m, cur_y = current_month_tuple()
    return (year, month) < (cur_y, cur_m)


async def _acquire_lock(db: AsyncSession) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADVISORY_LOCK_KEY}
    )


# ---------------------------------------------------------------------------
# Lazy month creation (FR-2.1, FR-2.2)
# ---------------------------------------------------------------------------

async def ensure_month(db: AsyncSession, month: int, year: int) -> None:
    """Materialize (month, year) if absent, walking forward from the latest
    materialized month: copy caps + lock states month by month, settling each
    month being left behind exactly once.

    - Future months are never materialized.
    - Months before the first-ever materialized month are pre-adoption and are
      never created or settled retroactively (doc §10 — fresh start).
    - The first-ever month is created empty; caps are added manually.
    """
    cur_m, cur_y = current_month_tuple()
    if (year, month) > (cur_y, cur_m):
        return

    # Cheap existence check before taking the lock (the common case).
    existing = await db.execute(
        select(BudgetMonth.id).where(
            BudgetMonth.month == month, BudgetMonth.year == year
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    await _acquire_lock(db)

    # Re-check under the lock — another request may have materialized it.
    rows = await db.execute(select(BudgetMonth))
    months = {(m.year, m.month) for m in rows.scalars().all()}
    if (year, month) in months:
        return

    if not months:
        # Adoption: first-ever budget month, created empty (fresh start).
        db.add(BudgetMonth(id=uuid.uuid4(), month=month, year=year))
        await db.flush()
        return

    latest_y, latest_m = max(months)
    if (year, month) < (latest_y, latest_m):
        # Absent but older than the latest month ⇒ pre-adoption (months are
        # always created consecutively). Never created retroactively.
        return

    walk_m, walk_y = latest_m, latest_y
    while (walk_y, walk_m) < (year, month):
        nxt_m, nxt_y = budget_math.next_month(walk_m, walk_y)
        await _copy_budgets_forward(db, walk_m, walk_y, nxt_m, nxt_y)
        db.add(BudgetMonth(id=uuid.uuid4(), month=nxt_m, year=nxt_y))
        await db.flush()
        await settle_month(db, walk_m, walk_y)
        walk_m, walk_y = nxt_m, nxt_y


async def _copy_budgets_forward(
    db: AsyncSession, from_m: int, from_y: int, to_m: int, to_y: int
) -> None:
    """Copy subcategory caps + lock states into the next month (FR-2.1, FR-1.7).

    Skips subcategories that already have a cap in the target month (a cap
    set ahead of time via PUT wins over the copy).
    """
    src_result = await db.execute(
        select(Budget).where(
            and_(
                Budget.month == from_m,
                Budget.year == from_y,
                Budget.subcategory_id.isnot(None),
            )
        )
    )
    src_budgets = src_result.scalars().all()
    if not src_budgets:
        return

    dst_result = await db.execute(
        select(Budget.subcategory_id).where(
            and_(
                Budget.month == to_m,
                Budget.year == to_y,
                Budget.subcategory_id.isnot(None),
            )
        )
    )
    already = {row[0] for row in dst_result.all()}

    for src in src_budgets:
        if src.subcategory_id in already:
            continue
        db.add(
            Budget(
                id=uuid.uuid4(),
                category_id=src.category_id,
                subcategory_id=src.subcategory_id,
                month=to_m,
                year=to_y,
                amount=src.amount,
                locked=src.locked,
            )
        )
    await db.flush()


# ---------------------------------------------------------------------------
# Month-close settlement (FR-2.3)
# ---------------------------------------------------------------------------

async def settle_month(db: AsyncSession, month: int, year: int) -> None:
    """Settle a closed month exactly once: surplus → saved balance, covered
    overage → deduction (floor 0). Idempotent via the settled_at claim."""
    claim = await db.execute(
        update(BudgetMonth)
        .where(
            and_(
                BudgetMonth.month == month,
                BudgetMonth.year == year,
                BudgetMonth.settled_at.is_(None),
            )
        )
        .values(settled_at=func.now())
        .returning(BudgetMonth.id)
    )
    if claim.scalar_one_or_none() is None:
        return  # already settled, or month never materialized

    budgets_result = await db.execute(
        select(Budget).where(
            and_(
                Budget.month == month,
                Budget.year == year,
                Budget.subcategory_id.isnot(None),
            )
        )
    )
    budgets = budgets_result.scalars().all()
    if not budgets:
        return

    spent_map = await budget_math.get_spent_by_subcategory(db, month, year)

    for b in budgets:
        balance_row = await _get_or_create_balance(db, b.subcategory_id)
        balance = Decimal(str(balance_row.balance))
        delta, reason = budget_math.settlement_outcome(
            Decimal(str(b.amount)), spent_map.get(b.subcategory_id, ZERO), balance
        )
        if reason is None:
            continue
        balance_row.balance = balance + delta
        db.add(
            SavedBalanceEvent(
                id=uuid.uuid4(),
                subcategory_id=b.subcategory_id,
                delta=delta,
                balance_after=balance_row.balance,
                reason=reason,
                month=month,
                year=year,
            )
        )
    await db.flush()


async def _get_or_create_balance(
    db: AsyncSession, subcategory_id: uuid.UUID
) -> SavedBalance:
    result = await db.execute(
        select(SavedBalance).where(SavedBalance.subcategory_id == subcategory_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = SavedBalance(subcategory_id=subcategory_id, balance=ZERO)
        db.add(row)
        await db.flush()
    return row


# ---------------------------------------------------------------------------
# Late-edit reconciliation (FR-4.4)
# ---------------------------------------------------------------------------

def budget_snapshot(txn) -> dict:
    """Capture the budget-relevant fields of a transaction. Take one before
    and one after any mutation and pass both to reconcile_transaction_change.

    subcategory_id holds the *effective* subcategory (confirmed, or the AI
    suggestion while unreviewed) so reconciliation tracks the same attribution
    the Spent aggregation uses — including the move that happens when a review
    confirms or corrects an AI suggestion."""
    return {
        "transaction_date": txn.transaction_date,
        "subcategory_id": budget_math.effective_subcategory_of(txn),
        "amount": txn.amount,
        "budget_excluded": txn.budget_excluded,
    }


async def reconcile_transaction_change(
    db: AsyncSession, snapshots: list[dict | None]
) -> None:
    """Re-settle any settled months affected by a transaction mutation.

    `snapshots` holds before/after states (either may be None for
    inserts/deletes). Every (month, subcategory) pair touched by either state
    is recomputed if that month has been settled; open and pre-adoption
    months need nothing (their figures are query-time).
    """
    pairs: set[tuple[int, int, uuid.UUID]] = set()
    for s in snapshots:
        if s and s.get("subcategory_id") and s.get("transaction_date"):
            d = s["transaction_date"]
            pairs.add((d.month, d.year, s["subcategory_id"]))
    if not pairs:
        return

    month_keys = {(m, y) for (m, y, _) in pairs}
    settled_result = await db.execute(
        select(BudgetMonth.month, BudgetMonth.year).where(
            BudgetMonth.settled_at.isnot(None)
        )
    )
    settled = {(row.month, row.year) for row in settled_result.all()}
    affected = [(m, y, sub) for (m, y, sub) in pairs if (m, y) in settled]
    if not affected:
        return

    await _acquire_lock(db)
    for m, y, sub in affected:
        await _resettle_subcategory_month(db, sub, m, y)


async def _resettle_subcategory_month(
    db: AsyncSession, subcategory_id: uuid.UUID, month: int, year: int
) -> None:
    cap_result = await db.execute(
        select(Budget).where(
            and_(
                Budget.month == month,
                Budget.year == year,
                Budget.subcategory_id == subcategory_id,
            )
        )
    )
    budget = cap_result.scalar_one_or_none()
    if budget is None:
        return  # subcategory was not budgeted in that month — no budget effect

    balance_result = await db.execute(
        select(SavedBalance).where(SavedBalance.subcategory_id == subcategory_id)
    )
    balance_row = balance_result.scalar_one_or_none()
    if balance_row is None:
        # Unbudgeted since (FR-1.5): the balance was deleted and is never
        # restored; the late edit is recorded in history only.
        logger.warning(
            "Recompute skipped for subcategory %s %04d-%02d: saved balance "
            "was deleted (unbudgeted)",
            subcategory_id, year, month,
        )
        return

    applied_result = await db.execute(
        select(func.coalesce(func.sum(SavedBalanceEvent.delta), 0)).where(
            and_(
                SavedBalanceEvent.subcategory_id == subcategory_id,
                SavedBalanceEvent.month == month,
                SavedBalanceEvent.year == year,
                SavedBalanceEvent.reason.in_(
                    SavedBalanceEvent.BALANCE_AFFECTING_REASONS
                ),
            )
        )
    )
    applied = Decimal(str(applied_result.scalar_one()))

    spent = await budget_math.get_spent_for_subcategory_month(
        db, subcategory_id, month, year
    )
    balance = Decimal(str(balance_row.balance))
    actual, discrepancy = budget_math.recompute_delta(
        Decimal(str(budget.amount)), spent, applied, balance
    )

    if discrepancy != 0:
        logger.warning(
            "Recompute discrepancy for subcategory %s %04d-%02d: %s could not "
            "be drawn (balance floored at 0)",
            subcategory_id, year, month, discrepancy,
        )
    if actual == 0:
        return

    balance_row.balance = balance + actual
    db.add(
        SavedBalanceEvent(
            id=uuid.uuid4(),
            subcategory_id=subcategory_id,
            delta=actual,
            balance_after=balance_row.balance,
            reason=SavedBalanceEvent.REASON_RECOMPUTE,
            month=month,
            year=year,
        )
    )
    await db.flush()
