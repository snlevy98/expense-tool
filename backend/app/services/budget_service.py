"""
Business logic for budgets: auto-seed, upsert, pool settings, and fill-from-last-month.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.budget import Budget
from app.models.budget_default import BudgetDefault
from app.models.budget_settings import BudgetSettings
from app.models.category import Category
from app.models.transaction import Transaction
from app.schemas.budget import (
    BudgetDefaultUpdate,
    BudgetListResponse,
    BudgetSettingsUpdate,
    BudgetUpsert,
    CategoryBudgetOut,
    SubcategoryBudgetOut,
)


# ---------------------------------------------------------------------------
# Budget Settings helpers
# ---------------------------------------------------------------------------

async def get_budget_settings(db: AsyncSession) -> BudgetSettings:
    """Return the single BudgetSettings row, creating it if absent."""
    result = await db.execute(select(BudgetSettings).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = BudgetSettings(id=uuid.uuid4(), pool_pct=Decimal("0.8000"))
        db.add(settings)
        await db.flush()
        await db.refresh(settings)
    return settings


async def update_pool_pct(db: AsyncSession, body: BudgetSettingsUpdate) -> BudgetSettings:
    """Update the pool_pct on the single BudgetSettings row."""
    settings = await get_budget_settings(db)
    settings.pool_pct = body.pool_pct
    await db.flush()
    await db.refresh(settings)
    return settings


# ---------------------------------------------------------------------------
# Income helpers
# ---------------------------------------------------------------------------

async def get_last_month_income(db: AsyncSession, month: int, year: int) -> Decimal:
    """
    Return total income for the month BEFORE (month, year).
    Income = abs(sum of negative-amount transactions in the Income-category).
    """
    # Compute previous month/year
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year

    start_date = date(prev_year, prev_month, 1)
    if prev_month == 12:
        end_date = date(prev_year + 1, 1, 1)
    else:
        end_date = date(prev_year, prev_month + 1, 1)

    # Find the Income category (budget_excluded=True, name matching "Income")
    cat_result = await db.execute(
        select(Category).where(
            Category.budget_excluded == True,  # noqa: E712
            func.lower(Category.name) == "income",
        )
    )
    income_cat = cat_result.scalar_one_or_none()
    if income_cat is None:
        return Decimal("0")

    # Income transactions are typically credits (negative amounts in our schema)
    result = await db.execute(
        select(func.sum(Transaction.amount)).where(
            and_(
                Transaction.category_id == income_cat.id,
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date < end_date,
            )
        )
    )
    total = result.scalar_one_or_none()
    if total is None:
        return Decimal("0")
    # Negate because income credits are stored as negative amounts
    return abs(Decimal(str(total)))


# ---------------------------------------------------------------------------
# Fill from last month
# ---------------------------------------------------------------------------

async def fill_from_last_month(db: AsyncSession, month: int, year: int) -> int:
    """
    Copy Budget rows from the previous month into (month, year).
    Existing rows for (month, year) are overwritten.
    Returns the count of rows copied.
    """
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year

    # Load previous month's budgets
    prev_result = await db.execute(
        select(Budget).where(Budget.month == prev_month, Budget.year == prev_year)
    )
    prev_budgets = prev_result.scalars().all()

    if not prev_budgets:
        return 0

    # Load current month's existing budgets for upsert
    cur_result = await db.execute(
        select(Budget).where(Budget.month == month, Budget.year == year)
    )
    # Index by (category_id, subcategory_id)
    cur_map: dict[tuple, Budget] = {}
    for b in cur_result.scalars().all():
        cur_map[(b.category_id, b.subcategory_id)] = b

    count = 0
    for prev in prev_budgets:
        key = (prev.category_id, prev.subcategory_id)
        if key in cur_map:
            cur_map[key].amount = prev.amount
        else:
            db.add(Budget(
                id=uuid.uuid4(),
                category_id=prev.category_id,
                subcategory_id=prev.subcategory_id,
                month=month,
                year=year,
                amount=prev.amount,
            ))
        count += 1

    await db.flush()
    return count


# ---------------------------------------------------------------------------
# Main budget listing
# ---------------------------------------------------------------------------

async def get_budgets_for_month(
    db: AsyncSession, month: int, year: int
) -> BudgetListResponse:
    """
    Return budgets for all non-excluded active categories for the given month/year,
    plus pool summary fields (pool_pct, pool_amount, allocated, leftover).

    - Categories with budget_excluded=True (Income, Investments) are skipped.
    - Categories with active subcategories: one Budget row per subcategory is
      auto-seeded at $0.  The category total is the sum.
    - Categories without subcategories: one Budget row per category, seeded
      from budget_defaults (or $0).  The amount is directly editable.
    """
    # Load non-excluded active categories with their active subcategories
    cat_result = await db.execute(
        select(Category)
        .where(
            Category.is_active == True,  # noqa: E712
            Category.budget_excluded == False,  # noqa: E712
        )
        .options(selectinload(Category.subcategories))
    )
    categories = cat_result.scalars().all()

    # Load all existing budgets for this month/year
    budget_result = await db.execute(
        select(Budget).where(Budget.month == month, Budget.year == year)
    )
    budgets = budget_result.scalars().all()

    # Index existing budgets
    cat_only_budgets: dict[uuid.UUID, Budget] = {}   # category_id → row where sub IS NULL
    sub_budgets: dict[uuid.UUID, Budget] = {}         # subcategory_id → row

    for b in budgets:
        if b.subcategory_id is None:
            cat_only_budgets[b.category_id] = b
        else:
            sub_budgets[b.subcategory_id] = b

    # Load category-level defaults
    default_result = await db.execute(select(BudgetDefault))
    defaults: dict[uuid.UUID, BudgetDefault] = {
        bd.category_id: bd for bd in default_result.scalars().all()
    }

    result_out: list[CategoryBudgetOut] = []

    for cat in categories:
        active_subs = [s for s in cat.subcategories if s.is_active]

        if active_subs:
            # ── Category with subcategories ─────────────────────────────────
            sub_outs: list[SubcategoryBudgetOut] = []

            for sub in active_subs:
                if sub.id not in sub_budgets:
                    new_b = Budget(
                        id=uuid.uuid4(),
                        category_id=cat.id,
                        subcategory_id=sub.id,
                        month=month,
                        year=year,
                        amount=Decimal("0"),
                    )
                    db.add(new_b)
                    await db.flush()
                    sub_budgets[sub.id] = new_b

                b = sub_budgets[sub.id]
                sub_outs.append(
                    SubcategoryBudgetOut(
                        id=b.id,
                        subcategory_id=sub.id,
                        subcategory_name=sub.name,
                        category_id=cat.id,
                        month=month,
                        year=year,
                        amount=Decimal(str(b.amount)),
                    )
                )

            total = sum(s.amount for s in sub_outs)
            result_out.append(
                CategoryBudgetOut(
                    category_id=cat.id,
                    category_name=cat.name,
                    category_color=cat.color,
                    has_subcategories=True,
                    total_amount=total,
                    budget_id=None,
                    month=month,
                    year=year,
                    subcategory_budgets=sub_outs,
                )
            )

        else:
            # ── Category without subcategories ──────────────────────────────
            if cat.id not in cat_only_budgets:
                default_amount = Decimal("0")
                if cat.id in defaults:
                    default_amount = Decimal(str(defaults[cat.id].default_amount))

                new_b = Budget(
                    id=uuid.uuid4(),
                    category_id=cat.id,
                    subcategory_id=None,
                    month=month,
                    year=year,
                    amount=default_amount,
                )
                db.add(new_b)
                await db.flush()
                cat_only_budgets[cat.id] = new_b

            b = cat_only_budgets[cat.id]
            result_out.append(
                CategoryBudgetOut(
                    category_id=cat.id,
                    category_name=cat.name,
                    category_color=cat.color,
                    has_subcategories=False,
                    total_amount=Decimal(str(b.amount)),
                    budget_id=b.id,
                    month=month,
                    year=year,
                    subcategory_budgets=[],
                )
            )

    # Pool summary
    settings = await get_budget_settings(db)
    pool_pct = Decimal(str(settings.pool_pct))
    last_month_income = await get_last_month_income(db, month, year)
    pool_amount = (last_month_income * pool_pct).quantize(Decimal("0.01"))
    allocated = sum(c.total_amount for c in result_out)
    leftover = pool_amount - allocated

    return BudgetListResponse(
        budgets=result_out,
        pool_pct=pool_pct,
        pool_amount=pool_amount,
        last_month_income=last_month_income,
        allocated=allocated,
        leftover=leftover,
    )


async def upsert_budget(db: AsyncSession, body: BudgetUpsert) -> dict:
    """Create or update a budget row for (category_id [+ subcategory_id], month, year)."""
    if body.subcategory_id is not None:
        result = await db.execute(
            select(Budget).where(
                Budget.subcategory_id == body.subcategory_id,
                Budget.month == body.month,
                Budget.year == body.year,
            )
        )
    else:
        result = await db.execute(
            select(Budget).where(
                Budget.category_id == body.category_id,
                Budget.subcategory_id.is_(None),
                Budget.month == body.month,
                Budget.year == body.year,
            )
        )

    budget = result.scalar_one_or_none()

    if budget:
        budget.amount = body.amount
    else:
        budget = Budget(
            id=uuid.uuid4(),
            category_id=body.category_id,
            subcategory_id=body.subcategory_id,
            month=body.month,
            year=body.year,
            amount=body.amount,
        )
        db.add(budget)

    await db.flush()
    await db.refresh(budget)

    return {
        "id": str(budget.id),
        "category_id": str(budget.category_id),
        "subcategory_id": str(budget.subcategory_id) if budget.subcategory_id else None,
        "month": budget.month,
        "year": budget.year,
        "amount": str(budget.amount),
    }


async def update_budget_default(
    db: AsyncSession, category_id: uuid.UUID, body: BudgetDefaultUpdate
) -> BudgetDefault:
    """Upsert a BudgetDefault for the given category."""
    result = await db.execute(
        select(BudgetDefault).where(BudgetDefault.category_id == category_id)
    )
    bd = result.scalar_one_or_none()

    if bd:
        bd.default_amount = body.default_amount
    else:
        bd = BudgetDefault(
            id=uuid.uuid4(),
            category_id=category_id,
            default_amount=body.default_amount,
        )
        db.add(bd)

    await db.flush()
    await db.refresh(bd)
    return bd
