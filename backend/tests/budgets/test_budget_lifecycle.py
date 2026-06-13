"""
Integration tests for app.services.budget_lifecycle against a real Postgres.

These cover the highest-risk surface of the envelope budgeting system — the
DB-level lifecycle the pure-math tests can't reach:

  - lazy month materialization + copy-forward (FR-2.1, FR-2.2)
  - month-close settlement and its settle-once guarantees (FR-2.3, NFR-2),
    including the uq_sbe_settlement index backstop
  - late-edit reconciliation against an already-settled month (FR-4.4),
    acceptance scenarios #9 and #12

`current_month_tuple` is monkeypatched so tests don't depend on the wall clock;
all months are positioned relative to a frozen "today" of June 2026.
"""

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.budget import Budget
from app.models.budget_month import BudgetMonth
from app.models.saved_balance import SavedBalance, SavedBalanceEvent
from app.services import budget_lifecycle


def D(v) -> Decimal:
    return Decimal(str(v))


@pytest.fixture
def freeze_current_month(monkeypatch):
    """Pin budget_lifecycle's notion of 'now' so future/closed-month logic is
    deterministic. Returns a setter: freeze(month, year)."""
    def _freeze(month: int, year: int):
        monkeypatch.setattr(
            budget_lifecycle, "current_month_tuple", lambda: (month, year)
        )
    return _freeze


async def _budget_months(db) -> set[tuple[int, int]]:
    rows = await db.execute(select(BudgetMonth.month, BudgetMonth.year))
    return {(r.month, r.year) for r in rows.all()}


async def _events(db, subcategory_id) -> list[SavedBalanceEvent]:
    rows = await db.execute(
        select(SavedBalanceEvent)
        .where(SavedBalanceEvent.subcategory_id == subcategory_id)
        .order_by(SavedBalanceEvent.created_at)
    )
    return list(rows.scalars().all())


async def _balance(db, subcategory_id) -> Decimal | None:
    row = await db.execute(
        select(SavedBalance.balance).where(
            SavedBalance.subcategory_id == subcategory_id
        )
    )
    val = row.scalar_one_or_none()
    return D(val) if val is not None else None


# ---------------------------------------------------------------------------
# ensure_month — lazy creation + copy-forward (FR-2.1, FR-2.2)
# ---------------------------------------------------------------------------

class TestEnsureMonth:
    async def test_first_ever_month_created_empty(self, db_session, freeze_current_month):
        freeze_current_month(6, 2026)
        await budget_lifecycle.ensure_month(db_session, 6, 2026)

        assert await _budget_months(db_session) == {(6, 2026)}
        # No caps invented for a fresh-start first month.
        count = await db_session.scalar(select(func.count()).select_from(Budget))
        assert count == 0

    async def test_future_month_not_materialized(self, db_session, freeze_current_month):
        freeze_current_month(6, 2026)
        await budget_lifecycle.ensure_month(db_session, 8, 2026)
        assert await _budget_months(db_session) == set()

    async def test_copy_forward_carries_caps_and_lock_states(
        self, db_session, freeze_current_month, make_category, make_subcategory,
        make_budget, make_budget_month,
    ):
        freeze_current_month(6, 2026)
        cat = await make_category()
        sub_a = await make_subcategory(cat, name="Dining Out")
        sub_b = await make_subcategory(cat, name="Groceries")
        await make_budget_month(5, 2026)
        await make_budget(cat, sub_a, 5, 2026, amount=D("300"), locked=False)
        await make_budget(cat, sub_b, 5, 2026, amount=D("500"), locked=True)

        await budget_lifecycle.ensure_month(db_session, 6, 2026)

        june = await db_session.execute(
            select(Budget).where(Budget.month == 6, Budget.year == 2026)
        )
        by_sub = {b.subcategory_id: b for b in june.scalars().all()}
        assert D(by_sub[sub_a.id].amount) == D("300")
        assert by_sub[sub_a.id].locked is False
        assert D(by_sub[sub_b.id].amount) == D("500")
        assert by_sub[sub_b.id].locked is True

    async def test_copy_forward_skips_preexisting_cap(
        self, db_session, freeze_current_month, make_category, make_subcategory,
        make_budget, make_budget_month,
    ):
        # A cap set ahead of time for June must win over the May→June copy.
        freeze_current_month(6, 2026)
        cat = await make_category()
        sub = await make_subcategory(cat)
        await make_budget_month(5, 2026)
        await make_budget(cat, sub, 5, 2026, amount=D("300"))
        await make_budget(cat, sub, 6, 2026, amount=D("999"))  # pre-set

        await budget_lifecycle.ensure_month(db_session, 6, 2026)

        june = await db_session.execute(
            select(Budget).where(
                Budget.month == 6, Budget.year == 2026, Budget.subcategory_id == sub.id
            )
        )
        rows = june.scalars().all()
        assert len(rows) == 1
        assert D(rows[0].amount) == D("999")

    async def test_walk_materializes_and_settles_intermediate_months(
        self, db_session, freeze_current_month, make_account, make_category,
        make_subcategory, make_budget, make_budget_month, make_transaction,
    ):
        # First month March; jumping to June must create Apr/May/Jun and settle
        # Mar/Apr/May exactly once each, leaving the current month (June) open.
        freeze_current_month(6, 2026)
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        await make_budget_month(3, 2026)
        await make_budget(cat, sub, 3, 2026, amount=D("300"))
        # Spend $250 in March → a $50 surplus to settle.
        await make_transaction(acct, sub, "2026-03-10", amount=D("250"))

        await budget_lifecycle.ensure_month(db_session, 6, 2026)

        assert await _budget_months(db_session) == {
            (3, 2026), (4, 2026), (5, 2026), (6, 2026)
        }
        settled = await db_session.execute(
            select(BudgetMonth.month, BudgetMonth.year).where(
                BudgetMonth.settled_at.isnot(None)
            )
        )
        assert {(r.month, r.year) for r in settled.all()} == {
            (3, 2026), (4, 2026), (5, 2026)
        }
        # Each settled month rolls its unspent cap into savings: March has a
        # $50 surplus (cap 300, spent 250); April and May copied the $300 cap
        # forward but have no spend, so each settles a full $300 surplus.
        assert await _balance(db_session, sub.id) == D("650")  # 50 + 300 + 300


# ---------------------------------------------------------------------------
# settle_month — month-close settlement (FR-2.3) + idempotency (NFR-2)
# ---------------------------------------------------------------------------

class TestSettleMonth:
    async def test_surplus_adds_to_saved_balance(
        self, db_session, make_account, make_category, make_subcategory,
        make_budget, make_budget_month, make_transaction,
    ):
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        await make_budget_month(5, 2026)
        await make_budget(cat, sub, 5, 2026, amount=D("300"))
        await make_transaction(acct, sub, "2026-05-04", amount=D("250"))

        await budget_lifecycle.settle_month(db_session, 5, 2026)

        assert await _balance(db_session, sub.id) == D("50")
        events = await _events(db_session, sub.id)
        assert len(events) == 1
        assert events[0].reason == SavedBalanceEvent.REASON_SURPLUS
        assert D(events[0].delta) == D("50")

    async def test_coverage_deducts_floored_at_balance(
        self, db_session, make_account, make_category, make_subcategory,
        make_budget, make_budget_month, make_transaction,
    ):
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        # Pre-existing $40 saved; overspend by $80 → only $40 drawable, floor 0.
        db_session.add(SavedBalance(subcategory_id=sub.id, balance=D("40")))
        await db_session.flush()
        await make_budget_month(5, 2026)
        await make_budget(cat, sub, 5, 2026, amount=D("300"))
        await make_transaction(acct, sub, "2026-05-09", amount=D("380"))

        await budget_lifecycle.settle_month(db_session, 5, 2026)

        assert await _balance(db_session, sub.id) == D("0")
        events = await _events(db_session, sub.id)
        assert len(events) == 1
        assert events[0].reason == SavedBalanceEvent.REASON_COVERAGE
        assert D(events[0].delta) == D("-40")

    async def test_refund_netting_excludes_flagged_transactions(
        self, db_session, make_account, make_category, make_subcategory,
        make_budget, make_budget_month, make_transaction,
    ):
        # Spent = signed sum of non-excluded txns: 300 - 60 refund = 240,
        # the +1000 excluded txn is ignored → surplus 60. (FR-4.1, FR-4.2)
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        await make_budget_month(5, 2026)
        await make_budget(cat, sub, 5, 2026, amount=D("300"))
        await make_transaction(acct, sub, "2026-05-02", amount=D("300"))
        await make_transaction(acct, sub, "2026-05-15", amount=D("-60"))  # refund
        await make_transaction(
            acct, sub, "2026-05-20", amount=D("1000"), budget_excluded=True
        )

        await budget_lifecycle.settle_month(db_session, 5, 2026)

        assert await _balance(db_session, sub.id) == D("60")

    async def test_settle_is_idempotent(
        self, db_session, make_account, make_category, make_subcategory,
        make_budget, make_budget_month, make_transaction,
    ):
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        await make_budget_month(5, 2026)
        await make_budget(cat, sub, 5, 2026, amount=D("300"))
        await make_transaction(acct, sub, "2026-05-04", amount=D("250"))

        await budget_lifecycle.settle_month(db_session, 5, 2026)
        await budget_lifecycle.settle_month(db_session, 5, 2026)  # second call

        # The settled_at claim makes the second call a no-op.
        assert await _balance(db_session, sub.id) == D("50")
        assert len(await _events(db_session, sub.id)) == 1

    async def test_unsettled_month_is_noop_when_no_budgets(
        self, db_session, make_budget_month,
    ):
        await make_budget_month(5, 2026)
        await budget_lifecycle.settle_month(db_session, 5, 2026)
        # Claim is taken but there is nothing to settle; no events anywhere.
        count = await db_session.scalar(
            select(func.count()).select_from(SavedBalanceEvent)
        )
        assert count == 0

    async def test_settlement_unique_index_blocks_duplicate(
        self, db_session, make_category, make_subcategory,
    ):
        # Direct DB-level proof of the settle-once backstop (uq_sbe_settlement):
        # a second settlement event for the same (subcategory, year, month)
        # is rejected even if application logic were bypassed.
        cat = await make_category()
        sub = await make_subcategory(cat)
        db_session.add(SavedBalance(subcategory_id=sub.id, balance=D("0")))
        await db_session.flush()

        def _evt():
            return SavedBalanceEvent(
                subcategory_id=sub.id,
                delta=D("10"),
                balance_after=D("10"),
                reason=SavedBalanceEvent.REASON_SURPLUS,
                month=5,
                year=2026,
            )

        db_session.add(_evt())
        await db_session.flush()
        db_session.add(_evt())
        with pytest.raises(IntegrityError):
            await db_session.flush()


# ---------------------------------------------------------------------------
# reconcile_transaction_change — late edits to settled months (FR-4.4)
# ---------------------------------------------------------------------------

class TestReconcile:
    async def test_late_expense_in_settled_month_draws_down(
        self, db_session, make_account, make_category, make_subcategory,
        make_budget, make_budget_month, make_transaction,
    ):
        # May settled with a $50 surplus (cap 300, spent 250). A $40 May expense
        # posts late → spent 290, expected surplus 10, compensating delta -40.
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        await make_budget_month(5, 2026)
        await make_budget(cat, sub, 5, 2026, amount=D("300"))
        await make_transaction(acct, sub, "2026-05-04", amount=D("250"))
        await budget_lifecycle.settle_month(db_session, 5, 2026)
        assert await _balance(db_session, sub.id) == D("50")

        late = await make_transaction(acct, sub, "2026-05-28", amount=D("40"))
        after = budget_lifecycle.budget_snapshot(late)
        await budget_lifecycle.reconcile_transaction_change(db_session, [None, after])

        assert await _balance(db_session, sub.id) == D("10")
        events = await _events(db_session, sub.id)
        assert events[-1].reason == SavedBalanceEvent.REASON_RECOMPUTE
        assert D(events[-1].delta) == D("-40")

    async def test_open_month_edit_is_noop(
        self, db_session, make_account, make_category, make_subcategory,
        make_budget, make_budget_month, make_transaction,
    ):
        # June is open (not settled) → reconcile touches nothing; June figures
        # are computed at query time, not carried in saved balances.
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        await make_budget_month(6, 2026)
        await make_budget(cat, sub, 6, 2026, amount=D("300"))
        txn = await make_transaction(acct, sub, "2026-06-10", amount=D("120"))

        after = budget_lifecycle.budget_snapshot(txn)
        await budget_lifecycle.reconcile_transaction_change(db_session, [None, after])

        count = await db_session.scalar(
            select(func.count()).select_from(SavedBalanceEvent)
        )
        assert count == 0
