import asyncio
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import require_auth
from app.models.transaction import Transaction
from app.schemas.transaction import EnrichPendingResponse, PaginatedTransactions, TransactionOut, TransactionUpdate
from app.services.enrichment_service import run_background_enrichment
from app.services.transaction_service import (
    delete_transaction,
    export_transactions_csv,
    get_transactions,
    update_transaction,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("/uncategorized-count")
async def uncategorized_count(
    exclude_amazon: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    conditions = [Transaction.category_id.is_(None)]
    if exclude_amazon:
        conditions.append(Transaction.merchant_name != "Amazon")
    result = await db.execute(
        select(func.count()).select_from(Transaction).where(and_(*conditions))
    )
    return {"count": result.scalar_one()}


@router.get("/export")
async def export_transactions(
    account_id: uuid.UUID | None = Query(None),
    category_id: uuid.UUID | None = Query(None),
    subcategory_id: uuid.UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    amount_min: Decimal | None = Query(None),
    amount_max: Decimal | None = Query(None),
    is_recurring: bool | None = Query(None),
    sort_by: str = Query("date", pattern="^(date|amount|merchant_name)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
):
    csv_content = await export_transactions_csv(
        db,
        account_id=account_id,
        category_id=category_id,
        subcategory_id=subcategory_id,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        is_recurring=is_recurring,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"},
    )


@router.get("/", response_model=PaginatedTransactions)
async def list_transactions(
    account_id: uuid.UUID | None = Query(None),
    category_id: uuid.UUID | None = Query(None),
    subcategory_id: uuid.UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    amount_min: Decimal | None = Query(None),
    amount_max: Decimal | None = Query(None),
    is_recurring: bool | None = Query(None),
    sort_by: str = Query("date", pattern="^(date|amount|merchant_name)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    uncategorized: bool | None = Query(None),
    exclude_amazon: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> PaginatedTransactions:
    return await get_transactions(
        db,
        account_id=account_id,
        category_id=category_id,
        subcategory_id=subcategory_id,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        is_recurring=is_recurring,
        uncategorized=uncategorized,
        exclude_amazon=exclude_amazon,
        sort_by=sort_by,
        sort_dir=sort_dir,
        skip=skip,
        limit=limit,
    )


@router.put("/{transaction_id}", response_model=TransactionOut)
async def update_transaction_endpoint(
    transaction_id: uuid.UUID,
    body: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> TransactionOut:
    result = await update_transaction(db, transaction_id, body)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found"
        )
    return result


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction_endpoint(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> None:
    deleted = await delete_transaction(db, transaction_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found"
        )


@router.post("/enrich-pending", response_model=EnrichPendingResponse)
async def enrich_pending(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> EnrichPendingResponse:
    """
    Find all unenriched non-Amazon transactions and kick off background enrichment.
    Returns immediately — enrichment runs as a background task.
    Capped at 500 rows per call; click again to process more after rate limits reset.
    """
    result = await db.execute(
        select(Transaction)
        .where(
            and_(
                Transaction.ai_enriched == False,   # noqa: E712
                Transaction.merchant_name != "Amazon",
            )
        )
        .limit(500)
    )
    pending = result.scalars().all()

    if not pending:
        return EnrichPendingResponse(queued=0, message="No transactions need enrichment.")

    asyncio.create_task(run_background_enrichment(list(pending)))
    count = len(pending)
    return EnrichPendingResponse(
        queued=count,
        message=f"Enrichment started for {count} transaction{'s' if count != 1 else ''}.",
    )
