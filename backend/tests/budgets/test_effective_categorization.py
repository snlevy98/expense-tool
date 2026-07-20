"""
Effective categorization: unreviewed transactions (category_id IS NULL) count
under their AI-suggested subcategory until reviewed; confirmed fields always
win; a reviewed category-only transaction never falls back to a stale AI
suggestion.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.transaction import Transaction
from app.services import budget_lifecycle, budget_math, budget_service

MONTH, YEAR = 6, 2026
WHEN = date(2026, 6, 15)


async def _make_txn(
    db_session,
    account,
    amount,
    *,
    category_id=None,
    subcategory_id=None,
    ai_category_id=None,
    ai_subcategory_id=None,
    budget_excluded=False,
):
    txn = Transaction(
        id=uuid.uuid4(),
        account_id=account.id,
        category_id=category_id,
        subcategory_id=subcategory_id,
        ai_suggested_category_id=ai_category_id,
        ai_suggested_subcategory_id=ai_subcategory_id,
        transaction_date=WHEN,
        raw_description="Effective test txn",
        merchant_name="Effective Merchant",
        amount=Decimal(str(amount)),
        budget_excluded=budget_excluded,
    )
    db_session.add(txn)
    await db_session.flush()
    return txn


@pytest.fixture
async def setup(db_session, make_account, make_category, make_subcategory):
    account = await make_account()
    cat = await make_category(name="Food")
    sub_a = await make_subcategory(cat, name="Groceries")
    sub_b = await make_subcategory(cat, name="Dining Out")
    return account, cat, sub_a, sub_b


async def test_unreviewed_counts_under_ai_suggestion(db_session, setup):
    account, cat, sub_a, _ = setup
    await _make_txn(
        db_session, account, "25.00",
        ai_category_id=cat.id, ai_subcategory_id=sub_a.id,
    )
    spent = await budget_math.get_spent_by_subcategory(db_session, MONTH, YEAR)
    assert spent.get(sub_a.id) == Decimal("25.00")

    single = await budget_math.get_spent_for_subcategory_month(
        db_session, sub_a.id, MONTH, YEAR
    )
    assert single == Decimal("25.00")


async def test_confirmed_wins_over_differing_ai_suggestion(db_session, setup):
    account, cat, sub_a, sub_b = setup
    # Reviewed as Dining Out even though AI said Groceries
    await _make_txn(
        db_session, account, "40.00",
        category_id=cat.id, subcategory_id=sub_b.id,
        ai_category_id=cat.id, ai_subcategory_id=sub_a.id,
    )
    spent = await budget_math.get_spent_by_subcategory(db_session, MONTH, YEAR)
    assert spent.get(sub_b.id) == Decimal("40.00")
    assert sub_a.id not in spent


async def test_reviewed_category_only_does_not_fall_back_to_stale_ai(
    db_session, setup
):
    account, cat, sub_a, _ = setup
    # User confirmed the category but chose no subcategory; AI had suggested one.
    await _make_txn(
        db_session, account, "18.00",
        category_id=cat.id, subcategory_id=None,
        ai_category_id=cat.id, ai_subcategory_id=sub_a.id,
    )
    spent = await budget_math.get_spent_by_subcategory(db_session, MONTH, YEAR)
    assert sub_a.id not in spent


async def test_budget_excluded_unreviewed_not_counted(db_session, setup):
    account, cat, sub_a, _ = setup
    await _make_txn(
        db_session, account, "99.00",
        ai_category_id=cat.id, ai_subcategory_id=sub_a.id,
        budget_excluded=True,
    )
    spent = await budget_math.get_spent_by_subcategory(db_session, MONTH, YEAR)
    assert sub_a.id not in spent


async def test_pending_spent_is_only_the_unreviewed_slice(db_session, setup):
    account, cat, sub_a, _ = setup
    await _make_txn(   # unreviewed → pending
        db_session, account, "10.00",
        ai_category_id=cat.id, ai_subcategory_id=sub_a.id,
    )
    await _make_txn(   # reviewed → not pending
        db_session, account, "30.00",
        category_id=cat.id, subcategory_id=sub_a.id,
    )
    spent = await budget_math.get_spent_by_subcategory(db_session, MONTH, YEAR)
    pending = await budget_math.get_pending_spent_by_subcategory(
        db_session, MONTH, YEAR
    )
    assert spent.get(sub_a.id) == Decimal("40.00")
    assert pending.get(sub_a.id) == Decimal("10.00")


async def test_budget_snapshot_uses_effective_subcategory(db_session, setup):
    account, cat, sub_a, sub_b = setup
    unreviewed = await _make_txn(
        db_session, account, "5.00",
        ai_category_id=cat.id, ai_subcategory_id=sub_a.id,
    )
    assert budget_lifecycle.budget_snapshot(unreviewed)["subcategory_id"] == sub_a.id

    # Review it: confirmed subcategory takes over in the snapshot
    unreviewed.category_id = cat.id
    unreviewed.subcategory_id = sub_b.id
    assert budget_lifecycle.budget_snapshot(unreviewed)["subcategory_id"] == sub_b.id

    # Reviewed category-only: snapshot must NOT fall back to the AI suggestion
    unreviewed.subcategory_id = None
    assert budget_lifecycle.budget_snapshot(unreviewed)["subcategory_id"] is None


async def test_dashboard_row_reports_pending_review_slice(
    db_session, setup, make_budget
):
    account, cat, sub_a, _ = setup
    await make_budget(cat, sub_a, MONTH, YEAR, Decimal("100.00"))
    await _make_txn(
        db_session, account, "20.00",
        ai_category_id=cat.id, ai_subcategory_id=sub_a.id,
    )
    await _make_txn(
        db_session, account, "50.00",
        category_id=cat.id, subcategory_id=sub_a.id,
    )

    dashboard = await budget_service.get_budget_dashboard(db_session, MONTH, YEAR)
    row = next(
        r for g in dashboard.categories for r in g.subcategories
        if r.subcategory_id == sub_a.id
    )
    assert row.spent == Decimal("70.00")
    assert row.spent_pending_review == Decimal("20.00")
    assert row.remaining == Decimal("30.00")
    assert dashboard.summary.total_spent_pending_review == Decimal("20.00")
