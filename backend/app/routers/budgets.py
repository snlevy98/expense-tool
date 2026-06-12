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
    BudgetDashboardResponse,
    BudgetSuggestRequest,
    BudgetSuggestResponse,
    BudgetSuggestionItem,
    CapUpdate,
    ExclusionRuleCreate,
    ExclusionRuleOut,
    LockUpdate,
    SavedBalanceOut,
    SavedBalanceReset,
)
from app.services import ai_service, budget_lifecycle
from app.services.budget_service import (
    create_exclusion_rule,
    delete_exclusion_rule,
    get_budget_dashboard,
    list_exclusion_rules,
    list_saved_balances,
    remove_subcategory_budget,
    reset_saved_balance,
    set_subcategory_cap,
    set_subcategory_lock,
)

router = APIRouter(prefix="/budgets", tags=["budgets"])

_MONTH = Query(..., ge=1, le=12)
_YEAR = Query(..., ge=2000, le=2100)


def _guard_closed_month(month: int, year: int) -> None:
    """Caps and locks in closed months are read-only (FR-2.4)."""
    if budget_lifecycle.is_closed_month(month, year):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This month is closed — caps and locks can no longer be edited.",
        )


# ---------------------------------------------------------------------------
# Saved balances (FR-3.4, FR-3.5)
# ---------------------------------------------------------------------------

@router.get("/saved-balances", response_model=list[SavedBalanceOut])
async def get_saved_balances(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> list[SavedBalanceOut]:
    return await list_saved_balances(db)


@router.post("/saved-balances/{subcategory_id}/reset", response_model=SavedBalanceOut)
async def reset_saved_balance_endpoint(
    subcategory_id: uuid.UUID,
    body: SavedBalanceReset,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> SavedBalanceOut:
    row = await reset_saved_balance(db, subcategory_id, body.value)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No saved balance for this subcategory (is it budgeted?).",
        )
    await db.commit()
    return SavedBalanceOut(
        subcategory_id=subcategory_id,
        subcategory_name=row.subcategory.name if row.subcategory else "",
        balance=Decimal(str(row.balance)),
    )


# ---------------------------------------------------------------------------
# Exclusion rules (FR-4.3)
# ---------------------------------------------------------------------------

@router.get("/exclusion-rules", response_model=list[ExclusionRuleOut])
async def get_exclusion_rules(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> list[ExclusionRuleOut]:
    rules = await list_exclusion_rules(db)
    return [ExclusionRuleOut.model_validate(r) for r in rules]


@router.post(
    "/exclusion-rules",
    response_model=ExclusionRuleOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_exclusion_rule_endpoint(
    body: ExclusionRuleCreate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> ExclusionRuleOut:
    rule = await create_exclusion_rule(db, body)
    await db.commit()
    return ExclusionRuleOut.model_validate(rule)


@router.delete("/exclusion-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exclusion_rule_endpoint(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> None:
    deleted = await delete_exclusion_rule(db, rule_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found"
        )
    await db.commit()


# ---------------------------------------------------------------------------
# AI suggestion — legacy allocation-based shape, replaced in suggestions v2
# ---------------------------------------------------------------------------

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
    # Netted spend (refunds reduce it, FR-4.1), excluding flagged transactions
    # (FR-4.2 / FR-5.2)
    spending_result = await db.execute(
        select(
            Transaction.subcategory_id,
            Transaction.category_id,
            func.sum(Transaction.amount).label("total"),
        )
        .where(
            and_(
                Transaction.budget_excluded == False,  # noqa: E712
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


# ---------------------------------------------------------------------------
# Dashboard + cap/lock/unbudget
# ---------------------------------------------------------------------------

@router.get("/", response_model=BudgetDashboardResponse)
async def get_dashboard_endpoint(
    month: int = _MONTH,
    year: int = _YEAR,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> BudgetDashboardResponse:
    """Envelope dashboard payload; lazily materializes the month (FR-2.2)."""
    result = await get_budget_dashboard(db, month=month, year=year)
    await db.commit()
    return result


@router.put("/subcategories/{subcategory_id}")
async def set_cap_endpoint(
    subcategory_id: uuid.UUID,
    body: CapUpdate,
    month: int = _MONTH,
    year: int = _YEAR,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    _guard_closed_month(month, year)
    await budget_lifecycle.ensure_month(db, month, year)
    budget = await set_subcategory_cap(db, subcategory_id, month, year, body.amount)
    if budget is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subcategory not found or cannot be budgeted (FR-1.8).",
        )
    await db.commit()
    return {
        "budget_id": str(budget.id),
        "subcategory_id": str(subcategory_id),
        "month": month,
        "year": year,
        "amount": str(budget.amount),
        "locked": budget.locked,
    }


@router.patch("/subcategories/{subcategory_id}/lock")
async def set_lock_endpoint(
    subcategory_id: uuid.UUID,
    body: LockUpdate,
    month: int = _MONTH,
    year: int = _YEAR,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    _guard_closed_month(month, year)
    budget = await set_subcategory_lock(db, subcategory_id, month, year, body.locked)
    if budget is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No budget for this subcategory in this month.",
        )
    await db.commit()
    return {"subcategory_id": str(subcategory_id), "locked": budget.locked}


@router.delete("/subcategories/{subcategory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unbudget_endpoint(
    subcategory_id: uuid.UUID,
    month: int = _MONTH,
    year: int = _YEAR,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> None:
    _guard_closed_month(month, year)
    removed = await remove_subcategory_budget(db, subcategory_id, month, year)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No budget for this subcategory in this month.",
        )
    await db.commit()
