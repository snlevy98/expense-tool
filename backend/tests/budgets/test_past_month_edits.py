"""
Edits to a closed (settled) month's cap are recorded but do not propagate into
saved balances. The one documented exception: a *later transaction edit* in that
month re-settles against the now-current cap.
"""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.budget import Budget
from app.models.saved_balance import SavedBalanceEvent
from app.services import budget_lifecycle, budget_service


def D(v) -> Decimal:
    return Decimal(str(v))


async def _balance(db, subcategory_id):
    from app.models.saved_balance import SavedBalance
    row = await db.execute(
        select(SavedBalance.balance).where(SavedBalance.subcategory_id == subcategory_id)
    )
    val = row.scalar_one_or_none()
    return D(val) if val is not None else None


async def _event_count(db, subcategory_id):
    return await db.scalar(
        select(func.count())
        .select_from(SavedBalanceEvent)
        .where(SavedBalanceEvent.subcategory_id == subcategory_id)
    )


async def _settle_may(db, make_account, make_category, make_subcategory,
                      make_budget, make_budget_month, make_transaction):
    acct = await make_account()
    cat = await make_category()
    sub = await make_subcategory(cat)
    await make_budget_month(5, 2026)
    await make_budget(cat, sub, 5, 2026, amount=D("300"))
    await make_transaction(acct, sub, "2026-05-10", amount=D("250"))
    await budget_lifecycle.settle_month(db, 5, 2026)  # surplus 50 → balance 50
    return acct, cat, sub


class TestPastMonthCapEdit:
    async def test_editing_settled_cap_does_not_touch_saved_balance(
        self, db_session, make_account, make_category, make_subcategory,
        make_budget, make_budget_month, make_transaction,
    ):
        acct, cat, sub = await _settle_may(
            db_session, make_account, make_category, make_subcategory,
            make_budget, make_budget_month, make_transaction,
        )
        assert await _balance(db_session, sub.id) == D("50")
        assert await _event_count(db_session, sub.id) == 1

        # Retroactively raise the May cap to 400.
        budget = await budget_service.set_subcategory_cap(db_session, sub.id, 5, 2026, D("400"))

        # The cap edit is recorded …
        assert D(budget.amount) == D("400")
        # … but the saved balance and event ledger are untouched.
        assert await _balance(db_session, sub.id) == D("50")
        assert await _event_count(db_session, sub.id) == 1

    async def test_later_transaction_edit_resyncs_to_new_cap(
        self, db_session, make_account, make_category, make_subcategory,
        make_budget, make_budget_month, make_transaction,
    ):
        # Documents the accepted edge case: after a retroactive cap edit, the
        # next transaction change in that month re-settles against the new cap.
        acct, cat, sub = await _settle_may(
            db_session, make_account, make_category, make_subcategory,
            make_budget, make_budget_month, make_transaction,
        )
        await budget_service.set_subcategory_cap(db_session, sub.id, 5, 2026, D("400"))
        assert await _balance(db_session, sub.id) == D("50")  # still inert

        # A late $10 May expense triggers reconcile, which uses the new cap (400):
        # expected surplus 400-260=140, already applied 50 → +90 → balance 140.
        late = await make_transaction(acct, sub, "2026-05-28", amount=D("10"))
        await budget_lifecycle.reconcile_transaction_change(
            db_session, [None, budget_lifecycle.budget_snapshot(late)]
        )

        assert await _balance(db_session, sub.id) == D("140")
