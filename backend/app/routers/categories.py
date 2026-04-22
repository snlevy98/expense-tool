import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.middleware.auth import require_auth
from app.models.category import Category
from app.models.subcategory import Subcategory
from app.models.transaction import Transaction
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("/", response_model=list[CategoryOut])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> list[CategoryOut]:
    result = await db.execute(
        select(Category)
        .options(selectinload(Category.subcategories))
    )
    categories = result.scalars().all()
    return list(categories)


@router.post("/", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> CategoryOut:
    category = Category(
        id=uuid.uuid4(),
        name=body.name,
        color=body.color,
    )
    db.add(category)
    await db.flush()
    await db.refresh(category)
    return category


@router.put("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: uuid.UUID,
    body: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> CategoryOut:
    result = await db.execute(
        select(Category)
        .where(Category.id == category_id)
        .options(selectinload(Category.subcategories))
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    await db.flush()
    await db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> None:
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    # 1. Null out category_id and subcategory_id on all affected transactions
    await db.execute(
        update(Transaction)
        .where(Transaction.category_id == category_id)
        .values(category_id=None, subcategory_id=None)
    )

    # 2. Hard-delete all subcategories belonging to this category
    await db.execute(delete(Subcategory).where(Subcategory.category_id == category_id))

    # 3. Hard-delete the category itself
    await db.delete(category)
    await db.flush()
