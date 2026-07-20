"""
Plaid integration service.

Wraps the (synchronous) plaid-python client for async FastAPI use and owns the
full sync pipeline: /transactions/sync → Transaction rows → the same post-save
plumbing the CSV confirm path runs (budget reconciliation, exclusion rules,
recurring detection, background AI enrichment).

Policies (per requirements):
  - Posted transactions only — pending ones are ignored entirely.
  - Synced rows land uncategorized (ai_enriched=False); background enrichment
    fills AI suggestions and the Categorize tab is the review surface.
  - Plaid sign convention (positive = money out) matches the app's
    positive_expense convention, so amounts are ingested as-is.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import plaid
from cryptography.fernet import Fernet
from jose import jwt as jose_jwt
from plaid.api import plaid_api
from plaid.api_client import ApiClient
from plaid.configuration import Configuration, Environment
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.link_token_transactions import LinkTokenTransactions
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.transactions_sync_request_options import (
    TransactionsSyncRequestOptions,
)
from plaid.model.webhook_verification_key_get_request import (
    WebhookVerificationKeyGetRequest,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.account import Account
from app.models.plaid_item import PlaidItem
from app.models.transaction import Transaction
from app.services import ai_service, budget_lifecycle, budget_service
from app.services.enrichment_service import run_background_enrichment

logger = logging.getLogger(__name__)

_SYNC_PAGE_COUNT = 500
_MAX_SYNC_PAGES = 40  # safety valve — 20k transactions per run is plenty


class PlaidNotConfigured(Exception):
    """Raised when PLAID_CLIENT_ID / PLAID_SECRET are missing."""


def is_configured() -> bool:
    return bool(settings.PLAID_CLIENT_ID and settings.PLAID_SECRET)


def get_client() -> plaid_api.PlaidApi:
    if not is_configured():
        raise PlaidNotConfigured(
            "PLAID_CLIENT_ID / PLAID_SECRET are not set in the environment."
        )
    host = (
        Environment.Production
        if settings.PLAID_ENV.lower() == "production"
        else Environment.Sandbox
    )
    configuration = Configuration(
        host=host,
        api_key={
            "clientId": settings.PLAID_CLIENT_ID,
            "secret": settings.PLAID_SECRET,
        },
    )
    return plaid_api.PlaidApi(ApiClient(configuration))


def plaid_error_code(exc: plaid.ApiException) -> str:
    """Extract error_code from a Plaid ApiException body."""
    try:
        return json.loads(exc.body).get("error_code", "")
    except (ValueError, TypeError, AttributeError):
        return ""


# ---------------------------------------------------------------------------
# Access-token encryption at rest
# ---------------------------------------------------------------------------

_ENC_PREFIX = "enc:"


def _fernet() -> Fernet | None:
    key = settings.PLAID_TOKEN_ENCRYPTION_KEY
    return Fernet(key.encode()) if key else None


def encrypt_token(token: str) -> str:
    f = _fernet()
    if f is None:
        return token
    return _ENC_PREFIX + f.encrypt(token.encode()).decode()


def decrypt_token(stored: str) -> str:
    if not stored.startswith(_ENC_PREFIX):
        return stored
    f = _fernet()
    if f is None:
        raise PlaidNotConfigured(
            "Stored Plaid token is encrypted but PLAID_TOKEN_ENCRYPTION_KEY is not set."
        )
    return f.decrypt(stored[len(_ENC_PREFIX):].encode()).decode()


# ---------------------------------------------------------------------------
# Link + exchange
# ---------------------------------------------------------------------------

async def create_link_token(user_id: str) -> str:
    """Create a Plaid Link token for the frontend Link flow."""
    client = get_client()
    kwargs: dict = {}
    if settings.PLAID_WEBHOOK_URL:
        kwargs["webhook"] = settings.PLAID_WEBHOOK_URL
    request = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="Household Expense Tracker",
        country_codes=[CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id=user_id),
        transactions=LinkTokenTransactions(days_requested=730),
        **kwargs,
    )
    response = await asyncio.to_thread(client.link_token_create, request)
    return response.link_token


def _map_account_type(plaid_account) -> str:
    """Prefer the specific subtype ('checking', 'savings', 'credit card');
    fall back to the broad type ('depository', 'credit')."""
    subtype = getattr(plaid_account, "subtype", None)
    if subtype is not None:
        return str(subtype)
    return str(getattr(plaid_account, "type", "") or "other")


async def exchange_public_token(db: AsyncSession, public_token: str) -> PlaidItem:
    """Exchange a Link public_token, store the Item, and create Account rows
    for every account the institution exposes."""
    client = get_client()

    exchange = await asyncio.to_thread(
        client.item_public_token_exchange,
        ItemPublicTokenExchangeRequest(public_token=public_token),
    )
    access_token = exchange.access_token
    item_id = exchange.item_id

    # Institution name (best-effort — purely cosmetic)
    institution_id: str | None = None
    institution_name = ""
    try:
        item_resp = await asyncio.to_thread(
            client.item_get, ItemGetRequest(access_token=access_token)
        )
        institution_id = item_resp.item.institution_id
        if institution_id:
            inst_resp = await asyncio.to_thread(
                client.institutions_get_by_id,
                InstitutionsGetByIdRequest(
                    institution_id=institution_id,
                    country_codes=[CountryCode("US")],
                ),
            )
            institution_name = inst_resp.institution.name
    except plaid.ApiException:
        logger.warning("Could not fetch institution details for item %s", item_id)

    # Idempotency: re-linking the same Item updates the stored token.
    existing = (
        await db.execute(select(PlaidItem).where(PlaidItem.item_id == item_id))
    ).scalar_one_or_none()
    if existing:
        existing.access_token = encrypt_token(access_token)
        existing.is_active = True
        item = existing
    else:
        item = PlaidItem(
            id=uuid.uuid4(),
            item_id=item_id,
            access_token=encrypt_token(access_token),
            institution_id=institution_id,
            institution_name=institution_name,
        )
        db.add(item)
    await db.flush()

    accounts_resp = await asyncio.to_thread(
        client.accounts_get, AccountsGetRequest(access_token=access_token)
    )
    await _upsert_accounts(db, item, accounts_resp.accounts)
    await db.commit()
    return item


async def _upsert_accounts(
    db: AsyncSession, item: PlaidItem, plaid_accounts
) -> dict[str, uuid.UUID]:
    """Create Account rows for unseen plaid_account_ids; return the full
    plaid_account_id → Account.id map for this item."""
    result = await db.execute(
        select(Account).where(Account.plaid_item_id == item.id)
    )
    by_plaid_id = {a.plaid_account_id: a for a in result.scalars().all()}

    for pa in plaid_accounts:
        if pa.account_id in by_plaid_id:
            continue
        mask = getattr(pa, "mask", None)
        display = f"{pa.name} ({mask})" if mask else pa.name
        account = Account(
            id=uuid.uuid4(),
            name=display[:100],
            type=_map_account_type(pa)[:50],
            institution=(item.institution_name or "Plaid")[:100],
            is_active=True,
            sign_convention="positive_expense",  # Plaid: positive = outflow
            plaid_item_id=item.id,
            plaid_account_id=pa.account_id,
        )
        db.add(account)
        by_plaid_id[pa.account_id] = account
    await db.flush()
    return {pid: acct.id for pid, acct in by_plaid_id.items()}


async def remove_item(db: AsyncSession, item: PlaidItem) -> None:
    """Revoke the Item at Plaid and mark it inactive locally. Accounts and
    already-imported transactions are kept."""
    client = get_client()
    try:
        await asyncio.to_thread(
            client.item_remove,
            ItemRemoveRequest(access_token=decrypt_token(item.access_token)),
        )
    except plaid.ApiException as exc:
        logger.warning(
            "Plaid item_remove failed for %s (%s) — marking inactive anyway",
            item.item_id, plaid_error_code(exc),
        )
    item.is_active = False
    await db.commit()


# ---------------------------------------------------------------------------
# Transaction sync
# ---------------------------------------------------------------------------

async def sync_item(db: AsyncSession, item: PlaidItem) -> dict:
    """Run /transactions/sync for one Item and apply the updates.

    Returns {"status": ..., "added": n, "modified": n, "removed": n,
    "skipped_pending": n}. status is "ok" or "not_ready" (initial pull still
    processing at Plaid — caller should retry later).
    """
    client = get_client()
    access_token = decrypt_token(item.access_token)

    added_raw: list = []
    modified_raw: list = []
    removed_raw: list = []
    cursor = item.sync_cursor
    pages = 0

    while True:
        kwargs: dict = {}
        if cursor:
            kwargs["cursor"] = cursor
        request = TransactionsSyncRequest(
            access_token=access_token,
            count=_SYNC_PAGE_COUNT,
            options=TransactionsSyncRequestOptions(
                include_original_description=True
            ),
            **kwargs,
        )
        try:
            resp = await asyncio.to_thread(client.transactions_sync, request)
        except plaid.ApiException as exc:
            code = plaid_error_code(exc)
            if code == "PRODUCT_NOT_READY":
                return {"status": "not_ready", "added": 0, "modified": 0,
                        "removed": 0, "skipped_pending": 0}
            if code == "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION":
                # Data changed mid-pagination — restart from the stored cursor.
                logger.info("Sync mutation during pagination for %s — restarting",
                            item.item_id)
                added_raw, modified_raw, removed_raw = [], [], []
                cursor = item.sync_cursor
                pages = 0
                continue
            raise

        added_raw.extend(resp.added)
        modified_raw.extend(resp.modified)
        removed_raw.extend(resp.removed)
        cursor = resp.next_cursor
        pages += 1
        if not resp.has_more or pages >= _MAX_SYNC_PAGES:
            break

    result = await _apply_sync_updates(
        db, item, added_raw, modified_raw, removed_raw, final_cursor=cursor
    )
    result["status"] = "ok"
    return result


def _to_amount(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


async def _apply_sync_updates(
    db: AsyncSession,
    item: PlaidItem,
    added_raw: list,
    modified_raw: list,
    removed_raw: list,
    final_cursor: str | None,
) -> dict:
    """Translate Plaid added/modified/removed into Transaction mutations and
    run the standard post-save plumbing. Commits (cursor saved atomically with
    the data, so a crash never skips or double-applies updates)."""
    account_map: dict[str, uuid.UUID] = {
        a.plaid_account_id: a.id
        for a in (
            await db.execute(
                select(Account).where(Account.plaid_item_id == item.id)
            )
        ).scalars().all()
        if a.plaid_account_id
    }

    # --- Added (posted only) ---
    posted = [t for t in added_raw if not t.pending]
    skipped_pending = len(added_raw) - len(posted)

    new_ids = [t.transaction_id for t in posted]
    existing_refs: set[str] = set()
    if new_ids:
        ref_rows = await db.execute(
            select(Transaction.external_reference).where(
                Transaction.external_reference.in_(new_ids)
            )
        )
        existing_refs = {r[0] for r in ref_rows.fetchall() if r[0]}

    import_batch_id = uuid.uuid4()
    new_txns: list[Transaction] = []
    for t in posted:
        if t.transaction_id in existing_refs:
            continue
        account_id = account_map.get(t.account_id)
        if account_id is None:
            logger.warning(
                "Plaid account %s not mapped for item %s — skipping txn",
                t.account_id, item.item_id,
            )
            continue
        original = getattr(t, "original_description", None)
        txn = Transaction(
            id=uuid.uuid4(),
            account_id=account_id,
            transaction_date=t.date,
            raw_description=(original or t.name or "")[:2000] or t.transaction_id,
            merchant_name=(t.merchant_name or t.name or "Unknown")[:200],
            amount=_to_amount(t.amount),
            ai_enriched=False,
            is_recurring=False,
            import_source="plaid",
            import_batch_id=import_batch_id,
            external_reference=t.transaction_id,
        )
        db.add(txn)
        new_txns.append(txn)

    # --- Modified / removed: look up by Plaid transaction_id ---
    snapshots: list[dict] = []
    modified_count = 0
    removed_count = 0

    async def _find(ref: str) -> Transaction | None:
        res = await db.execute(
            select(Transaction).where(Transaction.external_reference == ref)
        )
        return res.scalar_one_or_none()

    for t in modified_raw:
        if t.pending:
            continue
        txn = await _find(t.transaction_id)
        if txn is None:
            continue
        snapshots.append(budget_lifecycle.budget_snapshot(txn))
        txn.transaction_date = t.date
        txn.amount = _to_amount(t.amount)
        original = getattr(t, "original_description", None)
        txn.raw_description = (original or t.name or txn.raw_description)[:2000]
        snapshots.append(budget_lifecycle.budget_snapshot(txn))
        modified_count += 1

    for r in removed_raw:
        txn = await _find(r.transaction_id)
        if txn is None:
            continue  # usually a pending txn we never ingested
        snapshots.append(budget_lifecycle.budget_snapshot(txn))
        await db.delete(txn)
        removed_count += 1

    await db.flush()

    # Same post-save plumbing as the CSV confirm path.
    snapshots.extend(budget_lifecycle.budget_snapshot(t) for t in new_txns)
    await budget_lifecycle.reconcile_transaction_change(db, snapshots)
    await budget_service.apply_exclusion_rules(db, new_txns)

    item.sync_cursor = final_cursor
    item.last_synced_at = datetime.now(timezone.utc)
    await db.commit()

    if new_txns:
        new_txn_ids = [t.id for t in new_txns]
        asyncio.create_task(_detect_recurring_by_ids(new_txn_ids))
        asyncio.create_task(run_background_enrichment(new_txns))

    logger.info(
        "Plaid sync for %s: +%d added, ~%d modified, -%d removed, %d pending skipped",
        item.item_id, len(new_txns), modified_count, removed_count, skipped_pending,
    )
    return {
        "added": len(new_txns),
        "modified": modified_count,
        "removed": removed_count,
        "skipped_pending": skipped_pending,
    }


async def _detect_recurring_by_ids(txn_ids: list[uuid.UUID]) -> None:
    """Background task: recurring detection over newly synced rows.
    Opens its own session — safe after the request session closes."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Transaction).where(Transaction.id.in_(txn_ids))
            )
            txns = result.scalars().all()
            if not txns:
                return
            txn_dicts = [
                {
                    "id": str(t.id),
                    "merchant_name": t.merchant_name,
                    "amount": float(t.amount),
                    "transaction_date": t.transaction_date,
                }
                for t in txns
            ]
            recurring_ids = await ai_service.detect_recurring(txn_dicts)
            if recurring_ids:
                recurring_set = {uuid.UUID(rid) for rid in recurring_ids if rid}
                for t in txns:
                    if t.id in recurring_set:
                        t.is_recurring = True
                await db.commit()
    except Exception as exc:
        logger.warning("Recurring detection after Plaid sync failed: %s", exc)


async def sync_all_items(db: AsyncSession) -> list[dict]:
    """Sync every active Item; used by the manual sync endpoint."""
    items = (
        await db.execute(select(PlaidItem).where(PlaidItem.is_active == True))  # noqa: E712
    ).scalars().all()
    results = []
    for item in items:
        try:
            r = await sync_item(db, item)
        except plaid.ApiException as exc:
            r = {"status": "error", "error_code": plaid_error_code(exc)}
            logger.exception("Plaid sync failed for item %s", item.item_id)
        r["item_id"] = item.item_id
        r["institution_name"] = item.institution_name
        results.append(r)
    return results


# ---------------------------------------------------------------------------
# Webhook verification (Plaid signs webhooks with a JWT in Plaid-Verification)
# ---------------------------------------------------------------------------

async def verify_webhook(body: bytes, verification_jwt: str | None) -> bool:
    """Verify a Plaid webhook signature. Enforced in production; in
    development, unsigned webhooks are accepted (for local testing)."""
    if settings.ENVIRONMENT != "production":
        return True
    if not verification_jwt:
        return False
    try:
        header = jose_jwt.get_unverified_header(verification_jwt)
        if header.get("alg") != "ES256":
            return False
        client = get_client()
        key_resp = await asyncio.to_thread(
            client.webhook_verification_key_get,
            WebhookVerificationKeyGetRequest(key_id=header["kid"]),
        )
        key = key_resp.key.to_dict()
        claims = jose_jwt.decode(
            verification_jwt, key, algorithms=["ES256"],
            options={"verify_aud": False},
        )
        if time.time() - claims.get("iat", 0) > 300:
            return False  # stale webhook
        expected = claims.get("request_body_sha256", "")
        actual = hashlib.sha256(body).hexdigest()
        return hmac.compare_digest(expected, actual)
    except Exception:
        logger.exception("Plaid webhook verification failed")
        return False
