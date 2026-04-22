"""
Business logic for budgets: auto-seed, upsert, and default management.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import Budget
from app.models.budget_default import BudgetDefault
from app.models.category import Category
from app.schemas.budget import BudgetDefaultUpdate, BudgetOut, BudgetUpsert


def _to_budget_out(budget: Budget) -> BudgetOut:
    return BudgetOut(
        id=budget.id,
        category_id=budget.category_id,
        month=budget.month,
        year=budget.year,
        amount=Decimal(str(budget.amount)),
        created_at=budget.created_at,
        updated_at=budget.updated_at,
        category_name=budget.category.name if budget.category else None,
        category_color=budget.category.color if budget.category else None,
    )


async def get_budgets_for_month(
    db: AsyncSession, month: int, year: int
) -> list[BudgetOut]:
    """
    Return budgets for all active categories for the given month/year.
    Auto-seeds from budget_defaults (or 0) if a budget row doesn't exist yet.
    """
    # Load active categories with their budget_defaults
    cat_result = await db.execute(
        select(Category).where(Category.is_active == True)
    )
    categories = cat_result.scalars().all()

    # Load existing budgets for the month
    budget_result = await db.execute(
        select(Budget).where(Budget.month == month, Budget.year == year)
    )
    existing_budgets = {b.category_id: b for b in budget_result.scalars().all()}

    # Load all budget defaults
    default_result = await db.execute(select(BudgetDefault))
    defaults = {bd.category_id: bd for bd in default_result.scalars().all()}

    budgets_out: list[BudgetOut] = []
    for cat in categories:
        if cat.id not in existing_budgets:
            default_amount = Decimal("0")
            if cat.id in defaults:
                default_amount = Decimal(str(defaults[cat.id].default_amount))

            new_budget = Budget(
                id=uuid.uuid4(),
                category_id=cat.id,
                month=month,
                year=year,
                amount=default_amount,
            )
            db.add(new_budget)
            await db.flush()
            await db.refresh(new_budget)
            # Attach category for serialization
            new_budget.category = cat
            existing_budgets[cat.id] = new_budget

    for budget in existing_budgets.values():
        if not hasattr(budget, "category") or budget.category is None:
            # Lazy-load category
            for cat in categories:
                if cat.id == budget.category_id:
                    budget.category = cat
                    break
        budgets_out.append(_to_budget_out(budget))

    return budgets_out


async def upsert_budget(db: AsyncSession, body: BudgetUpsert) -> BudgetOut:
    """Create or update a budget row for (category_id, month, year)."""
    result = await db.execute(
        select(Budget).where(
            Budget.category_id == body.category_id,
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
            month=body.month,
            year=body.year,
            amount=body.amount,
        )
        db.add(budget)

    await db.flush()
    await db.refresh(budget)

    # Load category for response
    cat_result = await db.execute(
        select(Category).where(Category.id == budget.category_id)
    )
    budget.category = cat_result.scalar_one_or_none()

    return _to_budget_out(budget)


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
