import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import require_auth
from app.schemas.budget import (
    ApplySuggestionsRequest,
    ApplySuggestionsResponse,
    BudgetDashboardResponse,
    BudgetSuggestResponse,
    CapUpdate,
    ExclusionRuleCreate,
    ExclusionRuleOut,
    LockUpdate,
    SavedBalanceOut,
    SavedBalanceReset,
)
from app.services import budget_lifecycle
from app.services.budget_service import (
    apply_suggestions,
    create_exclusion_rule,
    delete_exclusion_rule,
    get_budget_dashboard,
    list_exclusion_rules,
    list_saved_balances,
    remove_subcategory_budget,
    reset_saved_balance,
    set_subcategory_cap,
    set_subcategory_lock,
    suggest_budget_v2,
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
# AI suggestions v2 (FR-5)
# ---------------------------------------------------------------------------

@router.post("/suggest", response_model=BudgetSuggestResponse)
async def suggest_budget_endpoint(
    month: int = _MONTH,
    year: int = _YEAR,
    months_back: int = Query(6, ge=3, le=6),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> BudgetSuggestResponse:
    """History-driven cap suggestions (no allocation input). Uses AI with a
    deterministic heuristic fallback; the response labels which was used."""
    return await suggest_budget_v2(db, month=month, year=year, months_back=months_back)


@router.post("/apply-suggestions", response_model=ApplySuggestionsResponse)
async def apply_suggestions_endpoint(
    body: ApplySuggestionsRequest,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> ApplySuggestionsResponse:
    """Bulk-apply accepted suggestions as caps (replaces N sequential PUTs)."""
    _guard_closed_month(body.month, body.year)
    await budget_lifecycle.ensure_month(db, body.month, body.year)
    applied = await apply_suggestions(db, body.month, body.year, body.items)
    await db.commit()
    return ApplySuggestionsResponse(applied=applied)


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
