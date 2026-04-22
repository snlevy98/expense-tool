import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import require_auth
from app.models.account import Account
from app.models.transaction import Transaction
from app.schemas.account import AccountCreate, AccountOut, AccountUpdate

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/", response_model=list[AccountOut])
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> list[AccountOut]:
    result = await db.execute(select(Account).where(Account.is_active == True))
    accounts = result.scalars().all()
    return list(accounts)


@router.post("/", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    body: AccountCreate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> AccountOut:
    account = Account(
        id=uuid.uuid4(),
        name=body.name,
        type=body.type,
        institution=body.institution,
    )
    db.add(account)
    await db.flush()
    await db.refresh(account)
    return account


@router.put("/{account_id}", response_model=AccountOut)
async def update_account(
    account_id: uuid.UUID,
    body: AccountUpdate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> AccountOut:
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(account, field, value)

    await db.flush()
    await db.refresh(account)
    return account


@router.get("/{account_id}/last-transaction-date")
async def last_transaction_date(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    """Return the most recent transaction date for an account, or null if none."""
    result = await db.execute(
        select(func.max(Transaction.transaction_date)).where(
            Transaction.account_id == account_id
        )
    )
    latest: date | None = result.scalar_one_or_none()
    return {"last_transaction_date": latest.isoformat() if latest else None}


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> None:
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    account.is_active = False
    await db.flush()
