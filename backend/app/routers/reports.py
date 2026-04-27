import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import require_auth
from app.schemas.report import (
    DashboardResponse,
    TopMerchantRow,
    TrendResponse,
    YTDResponse,
)
from app.schemas.transaction import TransactionOut
from app.services.report_service import (
    get_dashboard,
    get_recurring,
    get_top_merchants,
    get_trends,
    get_ytd,
)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> DashboardResponse:
    result = await get_dashboard(db, month=month, year=year)
    await db.commit()
    return result


@router.get("/trends", response_model=TrendResponse)
async def trends(
    months: int = Query(12, ge=1, le=60),
    category_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> TrendResponse:
    return await get_trends(db, months=months, category_id=category_id)


@router.get("/top-merchants", response_model=list[TopMerchantRow])
async def top_merchants(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> list[TopMerchantRow]:
    return await get_top_merchants(db, month=month, year=year, limit=limit)


@router.get("/ytd", response_model=YTDResponse)
async def ytd(
    year: int = Query(..., ge=2000, le=2100),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> YTDResponse:
    return await get_ytd(db, year=year)


@router.get("/recurring", response_model=list[TransactionOut])
async def recurring(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> list[TransactionOut]:
    return await get_recurring(db)
