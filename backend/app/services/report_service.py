"""
Report query logic: dashboard, trends, top_merchants, ytd, recurring.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import Transaction
from app.schemas.report import (
    DashboardCategoryRow,
    DashboardResponse,
    TopMerchantRow,
    TrendPoint,
    TrendResponse,
    YTDCategoryRow,
    YTDMonthEntry,
    YTDResponse,
)
from app.schemas.transaction import TransactionOut


def _dashboard_status(spent: Decimal, budget: Decimal) -> str:
    if budget == 0:
        return "green" if spent == 0 else "red"
    ratio = spent / budget
    if ratio < Decimal("0.5"):
        return "green"
    if ratio <= Decimal("1.0"):
        return "yellow"
    return "red"


async def get_dashboard(
    db: AsyncSession, month: int, year: int
) -> DashboardResponse:
    # Load all active categories
    cat_result = await db.execute(
        select(Category).where(Category.is_active == True)
    )
    categories = cat_result.scalars().all()
    category_map = {c.id: c for c in categories}

    # Load budgets for the month
    budget_result = await db.execute(
        select(Budget).where(Budget.month == month, Budget.year == year)
    )
    budget_map: dict[uuid.UUID, Decimal] = {
        b.category_id: Decimal(str(b.amount)) for b in budget_result.scalars().all()
    }

    # Aggregate spending per category (amount > 0 only = expenses)
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)

    spend_result = await db.execute(
        select(Transaction.category_id, func.sum(Transaction.amount).label("total"))
        .where(
            and_(
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
                Transaction.amount > 0,
            )
        )
        .group_by(Transaction.category_id)
    )
    spend_map: dict[uuid.UUID | None, Decimal] = {
        row.category_id: Decimal(str(row.total)) for row in spend_result.all()
    }

    rows: list[DashboardCategoryRow] = []
    total_budget = Decimal("0")
    total_spent = Decimal("0")

    for cat in categories:
        budget = budget_map.get(cat.id, Decimal("0"))
        spent = spend_map.get(cat.id, Decimal("0"))
        remaining = budget - spent
        status = _dashboard_status(spent, budget)

        total_budget += budget
        total_spent += spent

        rows.append(
            DashboardCategoryRow(
                category_id=str(cat.id),
                category_name=cat.name,
                category_color=cat.color,
                budget=budget,
                spent=spent,
                remaining=remaining,
                status=status,
            )
        )

    return DashboardResponse(
        month=month,
        year=year,
        rows=rows,
        total_budget=total_budget,
        total_spent=total_spent,
    )


async def get_trends(
    db: AsyncSession,
    months: int = 12,
    category_id: uuid.UUID | None = None,
) -> TrendResponse:
    """Monthly total spending for the last N months."""
    today = date.today()
    # Start from the first day of N months ago
    start_month = today.month - months + 1
    start_year = today.year
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    start_date = date(start_year, start_month, 1)

    conditions = [
        Transaction.transaction_date >= start_date,
        Transaction.amount > 0,
    ]
    if category_id:
        conditions.append(Transaction.category_id == category_id)

    result = await db.execute(
        select(
            func.extract("year", Transaction.transaction_date).label("year"),
            func.extract("month", Transaction.transaction_date).label("month"),
            func.sum(Transaction.amount).label("total_spent"),
        )
        .where(and_(*conditions))
        .group_by(
            func.extract("year", Transaction.transaction_date),
            func.extract("month", Transaction.transaction_date),
        )
        .order_by(
            func.extract("year", Transaction.transaction_date).asc(),
            func.extract("month", Transaction.transaction_date).asc(),
        )
    )

    points = [
        TrendPoint(
            month=int(row.month),
            year=int(row.year),
            total_spent=Decimal(str(row.total_spent)),
        )
        for row in result.all()
    ]
    return TrendResponse(points=points)


async def get_top_merchants(
    db: AsyncSession, month: int, year: int, limit: int = 10
) -> list[TopMerchantRow]:
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)

    result = await db.execute(
        select(
            Transaction.merchant_name,
            func.sum(Transaction.amount).label("total_spent"),
            func.count(Transaction.id).label("transaction_count"),
        )
        .where(
            and_(
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
                Transaction.amount > 0,
            )
        )
        .group_by(Transaction.merchant_name)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(limit)
    )

    return [
        TopMerchantRow(
            merchant_name=row.merchant_name,
            total_spent=Decimal(str(row.total_spent)),
            transaction_count=row.transaction_count,
        )
        for row in result.all()
    ]


async def get_ytd(db: AsyncSession, year: int) -> YTDResponse:
    """Year-to-date: for each category, month-by-month spending vs budget."""
    cat_result = await db.execute(
        select(Category).where(Category.is_active == True)
    )
    categories = cat_result.scalars().all()

    # Load all budgets for the year
    budget_result = await db.execute(
        select(Budget).where(Budget.year == year)
    )
    # budget_map[category_id][month] = amount
    budget_map: dict[uuid.UUID, dict[int, Decimal]] = {}
    for b in budget_result.scalars().all():
        budget_map.setdefault(b.category_id, {})[b.month] = Decimal(str(b.amount))

    # Aggregate spending per category per month
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)

    spend_result = await db.execute(
        select(
            Transaction.category_id,
            func.extract("month", Transaction.transaction_date).label("month"),
            func.sum(Transaction.amount).label("total"),
        )
        .where(
            and_(
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
                Transaction.amount > 0,
            )
        )
        .group_by(
            Transaction.category_id,
            func.extract("month", Transaction.transaction_date),
        )
    )
    # spend_by[category_id][month] = total
    spend_by: dict[uuid.UUID | None, dict[int, Decimal]] = {}
    for row in spend_result.all():
        spend_by.setdefault(row.category_id, {})[int(row.month)] = Decimal(
            str(row.total)
        )

    category_rows: list[YTDCategoryRow] = []
    for cat in categories:
        month_entries: list[YTDMonthEntry] = []
        for m in range(1, 13):
            budget_amt = budget_map.get(cat.id, {}).get(m, Decimal("0"))
            spent_amt = spend_by.get(cat.id, {}).get(m, Decimal("0"))
            month_entries.append(
                YTDMonthEntry(month=m, budget=budget_amt, spent=spent_amt)
            )
        category_rows.append(
            YTDCategoryRow(
                category_id=str(cat.id),
                category_name=cat.name,
                months=month_entries,
            )
        )

    return YTDResponse(year=year, categories=category_rows)


async def get_recurring(db: AsyncSession) -> list[TransactionOut]:
    """List all transactions marked as recurring."""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.is_recurring == True)
        .options(
            selectinload(Transaction.category),
            selectinload(Transaction.subcategory),
            selectinload(Transaction.account),
        )
        .order_by(Transaction.transaction_date.desc())
    )
    transactions = result.scalars().all()

    return [
        TransactionOut(
            id=t.id,
            account_id=t.account_id,
            category_id=t.category_id,
            subcategory_id=t.subcategory_id,
            transaction_date=t.transaction_date,
            raw_description=t.raw_description,
            merchant_name=t.merchant_name,
            amount=Decimal(str(t.amount)),
            ai_suggested_category_id=t.ai_suggested_category_id,
            ai_suggested_subcategory_id=t.ai_suggested_subcategory_id,
            is_recurring=t.is_recurring,
            import_source=t.import_source,
            import_batch_id=t.import_batch_id,
            created_at=t.created_at,
            updated_at=t.updated_at,
            category_name=t.category.name if t.category else None,
            subcategory_name=t.subcategory.name if t.subcategory else None,
            account_name=t.account.name if t.account else None,
        )
        for t in transactions
    ]
