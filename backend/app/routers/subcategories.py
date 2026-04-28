import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import require_auth
from app.models.subcategory import Subcategory
from app.models.transaction import Transaction
from app.schemas.subcategory import SubcategoryCreate, SubcategoryOut, SubcategoryUpdate

router = APIRouter(prefix="/subcategories", tags=["subcategories"])


@router.post("/", response_model=SubcategoryOut, status_code=status.HTTP_201_CREATED)
async def create_subcategory(
    body: SubcategoryCreate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> SubcategoryOut:
    # Assign sort_order = max existing + 1 within this category
    max_result = await db.execute(
        select(func.max(Subcategory.sort_order)).where(
            Subcategory.category_id == body.category_id
        )
    )
    max_order = max_result.scalar() or -1
    subcategory = Subcategory(
        id=uuid.uuid4(),
        category_id=body.category_id,
        name=body.name,
        sort_order=max_order + 1,
    )
    db.add(subcategory)
    await db.flush()
    await db.refresh(subcategory)
    return subcategory


@router.put("/{subcategory_id}/move", response_model=SubcategoryOut)
async def move_subcategory(
    subcategory_id: uuid.UUID,
    direction: str = Query(..., pattern="^(up|down)$"),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> SubcategoryOut:
    """Swap this subcategory's sort_order with its neighbour (up = lower index, down = higher)."""
    result = await db.execute(
        select(Subcategory).where(Subcategory.id == subcategory_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subcategory not found")

    # Fetch all siblings sorted by (sort_order, created_at)
    siblings_result = await db.execute(
        select(Subcategory)
        .where(Subcategory.category_id == sub.category_id)
        .order_by(Subcategory.sort_order, Subcategory.created_at)
    )
    siblings = siblings_result.scalars().all()

    idx = next((i for i, s in enumerate(siblings) if s.id == subcategory_id), None)
    if idx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subcategory not found in siblings")

    if direction == "up" and idx > 0:
        neighbour = siblings[idx - 1]
    elif direction == "down" and idx < len(siblings) - 1:
        neighbour = siblings[idx + 1]
    else:
        # Already at boundary — no-op, return current state
        return sub

    # Swap sort_order values
    sub.sort_order, neighbour.sort_order = neighbour.sort_order, sub.sort_order
    await db.flush()
    await db.refresh(sub)
    return sub


@router.put("/{subcategory_id}", response_model=SubcategoryOut)
async def update_subcategory(
    subcategory_id: uuid.UUID,
    body: SubcategoryUpdate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> SubcategoryOut:
    result = await db.execute(
        select(Subcategory).where(Subcategory.id == subcategory_id)
    )
    subcategory = result.scalar_one_or_none()
    if not subcategory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Subcategory not found"
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(subcategory, field, value)

    await db.flush()
    await db.refresh(subcategory)
    return subcategory


@router.delete("/{subcategory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subcategory(
    subcategory_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> None:
    result = await db.execute(
        select(Subcategory).where(Subcategory.id == subcategory_id)
    )
    subcategory = result.scalar_one_or_none()
    if not subcategory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Subcategory not found"
        )

    # 1. Null out subcategory_id on all affected transactions
    await db.execute(
        update(Transaction)
        .where(Transaction.subcategory_id == subcategory_id)
        .values(subcategory_id=None)
    )

    # 2. Hard-delete the subcategory
    await db.delete(subcategory)
    await db.flush()
