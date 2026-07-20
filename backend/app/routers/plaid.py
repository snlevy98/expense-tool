"""
Plaid router: Link-token creation, public-token exchange, manual sync,
item management, and the Plaid webhook receiver.

POST /plaid/link-token   — create a Link token for the frontend Link flow
POST /plaid/exchange     — exchange public_token, create Item + Accounts,
                           kick off the initial sync in the background
POST /plaid/sync         — sync one Item (body.item_id) or all active Items
GET  /plaid/items        — list connected Items with their accounts
DELETE /plaid/items/{id} — revoke at Plaid, mark inactive locally
POST /plaid/webhook      — Plaid → us: SYNC_UPDATES_AVAILABLE triggers a sync
"""

import asyncio
import logging
import uuid
from datetime import datetime

import plaid
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal, get_db
from app.middleware.auth import require_auth
from app.models.plaid_item import PlaidItem
from app.services import plaid_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/plaid", tags=["plaid"])

_INITIAL_SYNC_RETRIES = 10
_INITIAL_SYNC_DELAY_SECONDS = 15


def _require_configured() -> None:
    if not plaid_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plaid is not configured (PLAID_CLIENT_ID / PLAID_SECRET missing).",
        )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LinkTokenResponse(BaseModel):
    link_token: str


class ExchangeRequest(BaseModel):
    public_token: str


class SyncRequest(BaseModel):
    item_id: uuid.UUID | None = None


class PlaidAccountOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str

    model_config = {"from_attributes": True}


class PlaidItemOut(BaseModel):
    id: uuid.UUID
    item_id: str
    institution_name: str
    last_synced_at: datetime | None
    is_active: bool
    accounts: list[PlaidAccountOut]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/link-token", response_model=LinkTokenResponse)
async def create_link_token(
    auth: dict = Depends(require_auth),
) -> LinkTokenResponse:
    _require_configured()
    try:
        token = await plaid_service.create_link_token(
            user_id=str(auth.get("sub", "user"))
        )
    except plaid.ApiException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Plaid error: {plaid_service.plaid_error_code(exc)}",
        ) from exc
    return LinkTokenResponse(link_token=token)


@router.post("/exchange", response_model=PlaidItemOut, status_code=201)
async def exchange_public_token(
    body: ExchangeRequest,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> PlaidItemOut:
    _require_configured()
    try:
        item = await plaid_service.exchange_public_token(db, body.public_token)
    except plaid.ApiException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Plaid error: {plaid_service.plaid_error_code(exc)}",
        ) from exc

    # Initial transaction pull happens asynchronously — Plaid needs a little
    # time after linking before /transactions/sync has data (PRODUCT_NOT_READY).
    asyncio.create_task(_initial_sync_with_retry(item.id))

    loaded = (
        await db.execute(
            select(PlaidItem)
            .options(selectinload(PlaidItem.accounts))
            .where(PlaidItem.id == item.id)
        )
    ).scalar_one()
    return PlaidItemOut.model_validate(loaded)


@router.post("/sync")
async def sync_now(
    body: SyncRequest | None = None,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    _require_configured()
    if body and body.item_id:
        item = (
            await db.execute(select(PlaidItem).where(PlaidItem.id == body.item_id))
        ).scalar_one_or_none()
        if item is None:
            raise HTTPException(status_code=404, detail="Plaid item not found")
        try:
            result = await plaid_service.sync_item(db, item)
        except plaid.ApiException as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Plaid error: {plaid_service.plaid_error_code(exc)}",
            ) from exc
        return {"results": [result]}
    return {"results": await plaid_service.sync_all_items(db)}


@router.get("/items", response_model=list[PlaidItemOut])
async def list_items(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> list[PlaidItemOut]:
    items = (
        await db.execute(
            select(PlaidItem)
            .options(selectinload(PlaidItem.accounts))
            .order_by(PlaidItem.created_at)
        )
    ).scalars().all()
    return [PlaidItemOut.model_validate(i) for i in items]


@router.delete("/items/{item_pk}")
async def delete_item(
    item_pk: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    _require_configured()
    item = (
        await db.execute(select(PlaidItem).where(PlaidItem.id == item_pk))
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Plaid item not found")
    await plaid_service.remove_item(db, item)
    return {"removed": True}


@router.post("/webhook")
async def plaid_webhook(request: Request) -> dict:
    """Receiver for Plaid webhooks. Unauthenticated by design — verified via
    the Plaid-Verification signature header in production."""
    body = await request.body()
    verified = await plaid_service.verify_webhook(
        body, request.headers.get("Plaid-Verification")
    )
    if not verified:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception:
        return {"ok": True}

    webhook_type = payload.get("webhook_type", "")
    webhook_code = payload.get("webhook_code", "")
    plaid_item_id = payload.get("item_id", "")
    logger.info("Plaid webhook: %s / %s (item %s)",
                webhook_type, webhook_code, plaid_item_id)

    if webhook_type == "TRANSACTIONS" and webhook_code in (
        "SYNC_UPDATES_AVAILABLE", "INITIAL_UPDATE", "HISTORICAL_UPDATE",
        "DEFAULT_UPDATE",
    ):
        asyncio.create_task(_sync_by_plaid_item_id(plaid_item_id))
    elif webhook_type == "ITEM" and webhook_code == "ERROR":
        logger.warning("Plaid item %s reported an error: %s",
                       plaid_item_id, payload.get("error"))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Background helpers (own sessions — request session is gone by run time)
# ---------------------------------------------------------------------------

async def _sync_by_plaid_item_id(plaid_item_id: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            item = (
                await db.execute(
                    select(PlaidItem).where(PlaidItem.item_id == plaid_item_id)
                )
            ).scalar_one_or_none()
            if item is None or not item.is_active:
                logger.warning("Webhook for unknown/inactive item %s", plaid_item_id)
                return
            await plaid_service.sync_item(db, item)
    except Exception:
        logger.exception("Webhook-triggered sync failed for %s", plaid_item_id)


async def _initial_sync_with_retry(item_pk: uuid.UUID) -> None:
    """Poll until Plaid's initial transaction pull is ready, then sync.

    Two retry conditions: PRODUCT_NOT_READY (error), and an "ok" sync that
    returned nothing while this item has never produced data — right after
    linking, /transactions/sync can legitimately return an empty page before
    the initial pull lands, without raising. The cursor still guarantees
    eventual delivery, so re-polling picks the history up.
    """
    for attempt in range(_INITIAL_SYNC_RETRIES):
        try:
            async with AsyncSessionLocal() as db:
                item = (
                    await db.execute(
                        select(PlaidItem).where(PlaidItem.id == item_pk)
                    )
                ).scalar_one_or_none()
                if item is None or not item.is_active:
                    return
                result = await plaid_service.sync_item(db, item)
                got_data = (
                    result["added"] or result["modified"] or result["removed"]
                    or result["skipped_pending"] or result.get("skipped_old", 0)
                )
                if result["status"] == "ok" and got_data:
                    logger.info("Initial Plaid sync done for %s: %s",
                                item.item_id, result)
                    return
        except Exception:
            logger.exception("Initial Plaid sync attempt %d failed", attempt + 1)
        await asyncio.sleep(_INITIAL_SYNC_DELAY_SECONDS)
    logger.warning(
        "Initial Plaid sync got no data after %d attempts (item %s) — history "
        "will arrive via webhook or the next manual sync",
        _INITIAL_SYNC_RETRIES, item_pk,
    )
