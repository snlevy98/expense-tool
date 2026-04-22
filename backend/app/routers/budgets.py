import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import require_auth
from app.schemas.budget import BudgetDefaultUpdate, BudgetOut, BudgetUpsert
from app.services.budget_service import (
    get_budgets_for_month,
    update_budget_default,
    upsert_budget,
)

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("/", response_model=list[BudgetOut])
async def list_budgets(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> list[BudgetOut]:
    return await get_budgets_for_month(db, month=month, year=year)


@router.post("/", response_model=BudgetOut)
async def create_or_upsert_budget(
    body: BudgetUpsert,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> BudgetOut:
    return await upsert_budget(db, body)


@router.put("/defaults/{category_id}")
async def update_default_budget(
    category_id: uuid.UUID,
    body: BudgetDefaultUpdate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    bd = await update_budget_default(db, category_id, body)
    return {
        "category_id": str(bd.category_id),
        "default_amount": str(bd.default_amount),
    }
