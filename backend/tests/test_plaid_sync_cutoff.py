"""
PLAID_SYNC_START_DATE cutoff: transactions dated before the configured date
are never ingested by the sync pipeline; on/after the date they import
normally. Unset or malformed values mean no cutoff.
"""

import datetime
import uuid
from types import SimpleNamespace

import pytest

from app.models.account import Account
from app.models.plaid_item import PlaidItem
from app.models.transaction import Transaction
from app.services import plaid_service


def _fake_txn(ref, day, amount="10.00"):
    return SimpleNamespace(
        transaction_id=ref,
        account_id="plaid-acct-cutoff",
        amount=float(amount),
        date=datetime.date(2026, 1, 1) + datetime.timedelta(days=day),
        name=f"Merchant {ref}",
        merchant_name=f"Merchant {ref}",
        original_description=f"POS {ref}",
        pending=False,
    )


@pytest.fixture
def no_background_tasks(monkeypatch):
    """The sync pipeline fires AI enrichment / recurring detection tasks —
    irrelevant here and they'd open sessions against the real engine."""
    async def _noop(*args, **kwargs):
        return None
    monkeypatch.setattr(plaid_service, "run_background_enrichment", _noop)
    monkeypatch.setattr(plaid_service, "_detect_recurring_by_ids", _noop)


@pytest.fixture
async def plaid_item_with_account(db_session):
    item = PlaidItem(
        id=uuid.uuid4(), item_id=f"cutoff-{uuid.uuid4().hex[:8]}",
        access_token="tok", institution_name="Cutoff Bank",
    )
    db_session.add(item)
    await db_session.flush()
    account = Account(
        id=uuid.uuid4(), name="Cutoff Checking", type="checking",
        institution="Cutoff Bank", plaid_item_id=item.id,
        plaid_account_id="plaid-acct-cutoff",
    )
    db_session.add(account)
    await db_session.flush()
    return item, account


def test_sync_start_date_parsing(monkeypatch):
    monkeypatch.setattr(plaid_service.settings, "PLAID_SYNC_START_DATE", "")
    assert plaid_service.sync_start_date() is None
    monkeypatch.setattr(plaid_service.settings, "PLAID_SYNC_START_DATE", "2026-01-01")
    assert plaid_service.sync_start_date() == datetime.date(2026, 1, 1)
    monkeypatch.setattr(plaid_service.settings, "PLAID_SYNC_START_DATE", "not-a-date")
    assert plaid_service.sync_start_date() is None


async def test_cutoff_filters_old_transactions(
    db_session, plaid_item_with_account, no_background_tasks, monkeypatch
):
    item, account = plaid_item_with_account
    monkeypatch.setattr(
        plaid_service.settings, "PLAID_SYNC_START_DATE", "2026-01-10"
    )

    added = [
        _fake_txn("old-1", day=0),    # 2026-01-01 — before cutoff
        _fake_txn("old-2", day=8),    # 2026-01-09 — before cutoff
        _fake_txn("edge", day=9),     # 2026-01-10 — ON the cutoff (kept)
        _fake_txn("new-1", day=15),   # 2026-01-16 — after (kept)
    ]
    result = await plaid_service._apply_sync_updates(
        db_session, item, added, [], [], final_cursor="c1"
    )
    assert result["added"] == 2
    assert result["skipped_old"] == 2

    from sqlalchemy import select
    refs = {
        t.external_reference
        for t in (await db_session.execute(
            select(Transaction).where(Transaction.account_id == account.id)
        )).scalars().all()
    }
    assert refs == {"edge", "new-1"}


async def test_no_cutoff_ingests_everything(
    db_session, plaid_item_with_account, no_background_tasks, monkeypatch
):
    item, account = plaid_item_with_account
    monkeypatch.setattr(plaid_service.settings, "PLAID_SYNC_START_DATE", "")

    added = [_fake_txn("a", day=0), _fake_txn("b", day=100)]
    result = await plaid_service._apply_sync_updates(
        db_session, item, added, [], [], final_cursor="c1"
    )
    assert result["added"] == 2
    assert result["skipped_old"] == 0
