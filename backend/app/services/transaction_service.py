"""
Business logic for transactions: list with filters, update, delete, CSV export.
"""

import csv
import io
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.subcategory import Subcategory
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionOut, TransactionUpdate


def _build_filters(
    query,
    account_id: uuid.UUID | None,
    category_id: uuid.UUID | None,
    subcategory_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
    amount_min: Decimal | None,
    amount_max: Decimal | None,
    is_recurring: bool | None,
    uncategorized: bool | None = None,
):
    conditions = []
    if account_id:
        conditions.append(Transaction.account_id == account_id)
    if uncategorized:
        conditions.append(Transaction.category_id.is_(None))
    elif category_id:
        conditions.append(Transaction.category_id == category_id)
    if subcategory_id:
        conditions.append(Transaction.subcategory_id == subcategory_id)
    if date_from:
        conditions.append(Transaction.transaction_date >= date_from)
    if date_to:
        conditions.append(Transaction.transaction_date <= date_to)
    if amount_min is not None:
        conditions.append(Transaction.amount >= amount_min)
    if amount_max is not None:
        conditions.append(Transaction.amount <= amount_max)
    if is_recurring is not None:
        conditions.append(Transaction.is_recurring == is_recurring)
    if conditions:
        query = query.where(and_(*conditions))
    return query


def _apply_sort(query, sort_by: str, sort_dir: str):
    column_map = {
        "date": Transaction.transaction_date,
        "amount": Transaction.amount,
        "merchant_name": Transaction.merchant_name,
    }
    col = column_map.get(sort_by, Transaction.transaction_date)
    if sort_dir == "asc":
        return query.order_by(col.asc())
    return query.order_by(col.desc())


def _to_transaction_out(txn: Transaction) -> TransactionOut:
    return TransactionOut(
        id=txn.id,
        account_id=txn.account_id,
        category_id=txn.category_id,
        subcategory_id=txn.subcategory_id,
        transaction_date=txn.transaction_date,
        raw_description=txn.raw_description,
        merchant_name=txn.merchant_name,
        amount=Decimal(str(txn.amount)),
        ai_suggested_category_id=txn.ai_suggested_category_id,
        ai_suggested_subcategory_id=txn.ai_suggested_subcategory_id,
        is_recurring=txn.is_recurring,
        import_source=txn.import_source,
        import_batch_id=txn.import_batch_id,
        created_at=txn.created_at,
        updated_at=txn.updated_at,
        category_name=txn.category.name if txn.category else None,
        subcategory_name=txn.subcategory.name if txn.subcategory else None,
        account_name=txn.account.name if txn.account else None,
    )


async def get_transactions(
    db: AsyncSession,
    account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    subcategory_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    is_recurring: bool | None = None,
    uncategorized: bool | None = None,
    sort_by: str = "date",
    sort_dir: str = "desc",
    skip: int = 0,
    limit: int = 100,
) -> dict:
    # Count query (same filters, no sort/pagination)
    count_query = select(func.count()).select_from(Transaction)
    count_query = _build_filters(
        count_query, account_id, category_id, subcategory_id,
        date_from, date_to, amount_min, amount_max, is_recurring, uncategorized
    )
    total: int = (await db.execute(count_query)).scalar_one()

    # Data query
    query = select(Transaction).options(
        selectinload(Transaction.category),
        selectinload(Transaction.subcategory),
        selectinload(Transaction.account),
    )
    query = _build_filters(
        query, account_id, category_id, subcategory_id,
        date_from, date_to, amount_min, amount_max, is_recurring, uncategorized
    )
    query = _apply_sort(query, sort_by, sort_dir)
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    transactions = result.scalars().all()
    return {"items": [_to_transaction_out(t) for t in transactions], "total": total}


async def update_transaction(
    db: AsyncSession,
    transaction_id: uuid.UUID,
    body: TransactionUpdate,
) -> TransactionOut | None:
    result = await db.execute(
        select(Transaction)
        .where(Transaction.id == transaction_id)
        .options(
            selectinload(Transaction.category),
            selectinload(Transaction.subcategory),
            selectinload(Transaction.account),
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        return None

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(txn, field, value)

    await db.flush()
    await db.refresh(txn)
    return _to_transaction_out(txn)


async def delete_transaction(
    db: AsyncSession, transaction_id: uuid.UUID
) -> bool:
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        return False
    await db.delete(txn)
    await db.flush()
    return True


async def export_transactions_csv(
    db: AsyncSession,
    account_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    subcategory_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    is_recurring: bool | None = None,
    sort_by: str = "date",
    sort_dir: str = "desc",
) -> str:
    """Return all matching transactions as a CSV string."""
    query = select(Transaction).options(
        selectinload(Transaction.category),
        selectinload(Transaction.subcategory),
        selectinload(Transaction.account),
    )
    query = _build_filters(
        query, account_id, category_id, subcategory_id,
        date_from, date_to, amount_min, amount_max, is_recurring
    )
    query = _apply_sort(query, sort_by, sort_dir)

    result = await db.execute(query)
    transactions = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "date", "merchant_name", "raw_description",
        "amount", "category", "subcategory", "account",
        "is_recurring", "import_source", "import_batch_id",
    ])
    for t in transactions:
        writer.writerow([
            str(t.id),
            t.transaction_date.isoformat(),
            t.merchant_name,
            t.raw_description,
            t.amount,
            t.category.name if t.category else "",
            t.subcategory.name if t.subcategory else "",
            t.account.name if t.account else "",
            t.is_recurring,
            t.import_source,
            str(t.import_batch_id) if t.import_batch_id else "",
        ])
    return output.getvalue()
