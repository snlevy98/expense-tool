import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.middleware.auth import require_auth
from app.models.category import Category
from app.models.transaction import Transaction
from app.schemas.budget import (
    BudgetDefaultUpdate,
    BudgetListResponse,
    BudgetSettingsOut,
    BudgetSettingsUpdate,
    BudgetSuggestRequest,
    BudgetSuggestResponse,
    BudgetSuggestionItem,
    BudgetUpsert,
    CategoryBudgetOut,
)
from app.services import ai_service
from app.services.budget_service import (
    fill_from_last_month,
    get_budget_settings,
    get_budgets_for_month,
    update_budget_default,
    update_pool_pct,
    upsert_budget,
)

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("/settings", response_model=BudgetSettingsOut)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> BudgetSettingsOut:
    settings = await get_budget_settings(db)
    return BudgetSettingsOut(pool_pct=settings.pool_pct)


@router.put("/settings", response_model=BudgetSettingsOut)
async def update_settings(
    body: BudgetSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> BudgetSettingsOut:
    settings = await update_pool_pct(db, body)
    await db.commit()
    return BudgetSettingsOut(pool_pct=settings.pool_pct)


@router.post("/fill-from-last-month")
async def fill_from_last_month_endpoint(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    count = await fill_from_last_month(db, month=month, year=year)
    await db.commit()
    return {"copied": count}


@router.get("/", response_model=BudgetListResponse)
async def list_budgets(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> BudgetListResponse:
    result = await get_budgets_for_month(db, month=month, year=year)
    await db.commit()
    return result


@router.post("/")
async def create_or_upsert_budget(
    body: BudgetUpsert,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    result = await upsert_budget(db, body)
    await db.commit()
    return result


@router.post("/suggest", response_model=BudgetSuggestResponse)
async def suggest_budget_endpoint(
    body: BudgetSuggestRequest,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> BudgetSuggestResponse:
    """
    Use Groq to suggest a monthly budget across all non-excluded subcategories.
    Computes historical averages over the last months_back complete months,
    then asks Groq to allocate the given total across them.
    """
    months_back = max(1, min(12, body.months_back))

    # Load non-excluded active categories with their active subcategories
    cat_result = await db.execute(
        select(Category)
        .where(Category.is_active == True, Category.budget_excluded == False)  # noqa: E712
        .options(selectinload(Category.subcategories))
    )
    categories = cat_result.scalars().all()
    if not categories:
        return BudgetSuggestResponse(
            suggestions=[], total_suggested=Decimal("0"), allocation=body.allocation
        )

    # Date range: last months_back complete calendar months
    today = date.today()
    y, m = today.year, today.month
    m -= months_back
    while m <= 0:
        m += 12
        y -= 1
    start_date = date(y, m, 1)
    end_date = date(today.year, today.month, 1)

    cat_ids = [c.id for c in categories]
    spending_result = await db.execute(
        select(
            Transaction.subcategory_id,
            Transaction.category_id,
            func.sum(Transaction.amount).label("total"),
        )
        .where(
            and_(
                Transaction.amount > 0,
                Transaction.category_id.in_(cat_ids),
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date < end_date,
            )
        )
        .group_by(Transaction.subcategory_id, Transaction.category_id)
    )
    spending_rows = spending_result.all()

    sub_spending: dict[uuid.UUID, Decimal] = {}
    cat_spending: dict[uuid.UUID, Decimal] = {}
    for row in spending_rows:
        total = Decimal(str(row.total or 0))
        if row.subcategory_id:
            sub_spending[row.subcategory_id] = total
        else:
            cat_spending[row.category_id] = cat_spending.get(row.category_id, Decimal("0")) + total

    mb = Decimal(str(months_back))

    # Build items list for the AI prompt
    ai_items: list[dict] = []
    for cat in categories:
        active_subs = [s for s in cat.subcategories if s.is_active]
        if active_subs:
            for sub in active_subs:
                avg = (sub_spending.get(sub.id, Decimal("0")) / mb).quantize(Decimal("0.01"))
                ai_items.append({
                    "id": str(sub.id),
                    "subcategory_id": sub.id,
                    "subcategory_name": sub.name,
                    "category_id": cat.id,
                    "category_name": cat.name,
                    "monthly_avg": avg,
                })
        else:
            avg = (cat_spending.get(cat.id, Decimal("0")) / mb).quantize(Decimal("0.01"))
            ai_items.append({
                "id": str(cat.id),
                "subcategory_id": None,
                "subcategory_name": None,
                "category_id": cat.id,
                "category_name": cat.name,
                "monthly_avg": avg,
            })

    if not ai_items:
        return BudgetSuggestResponse(
            suggestions=[], total_suggested=Decimal("0"), allocation=body.allocation
        )

    try:
        raw = await ai_service.suggest_budget(ai_items, float(body.allocation), months_back)
    except ai_service.RateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable — please retry.",
        ) from exc

    # Normalize Groq output to sum exactly to allocation (guards against rounding drift)
    total_raw = sum(raw.values())
    if total_raw > 0:
        factor = float(body.allocation) / total_raw
        normalized = {k: v * factor for k, v in raw.items()}
    else:
        share = float(body.allocation) / len(ai_items)
        normalized = {item["id"]: share for item in ai_items}

    rounded: dict[str, Decimal] = {
        k: Decimal(str(round(v, 2))) for k, v in normalized.items()
    }
    # Fix any residual rounding drift on the last item
    diff = body.allocation - sum(rounded.values())
    if diff and rounded:
        last_key = list(rounded)[-1]
        rounded[last_key] = max(Decimal("0"), rounded[last_key] + diff)

    suggestions = [
        BudgetSuggestionItem(
            id=item["id"],
            subcategory_id=item["subcategory_id"],
            subcategory_name=item["subcategory_name"],
            category_id=item["category_id"],
            category_name=item["category_name"],
            monthly_avg=item["monthly_avg"],
            suggested_amount=rounded.get(item["id"], Decimal("0")),
        )
        for item in ai_items
    ]

    return BudgetSuggestResponse(
        suggestions=suggestions,
        total_suggested=sum(s.suggested_amount for s in suggestions),
        allocation=body.allocation,
    )


@router.put("/defaults/{category_id}")
async def update_default_budget(
    category_id: uuid.UUID,
    body: BudgetDefaultUpdate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    bd = await update_budget_default(db, category_id, body)
    await db.commit()
    return {
        "category_id": str(bd.category_id),
        "default_amount": str(bd.default_amount),
    }
