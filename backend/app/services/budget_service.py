"""
Business logic for budgets: auto-seed, upsert, and default management.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.budget import Budget
from app.models.budget_default import BudgetDefault
from app.models.category import Category
from app.schemas.budget import (
    BudgetDefaultUpdate,
    BudgetUpsert,
    CategoryBudgetOut,
    SubcategoryBudgetOut,
)


async def get_budgets_for_month(
    db: AsyncSession, month: int, year: int
) -> list[CategoryBudgetOut]:
    """
    Return budgets for all active categories for the given month/year.

    - Categories with active subcategories: one Budget row per subcategory is
      auto-seeded at $0.  The category total is the sum.
    - Categories without subcategories: one Budget row per category, seeded
      from budget_defaults (or $0).  The amount is directly editable.
    """
    # Load active categories with their active subcategories
    cat_result = await db.execute(
        select(Category)
        .where(Category.is_active == True)  # noqa: E712
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

    return result_out


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
