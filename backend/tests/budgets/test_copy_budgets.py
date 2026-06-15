"""
Integration tests for copying a month's budget into another month
(budget_service.copy_budgets).
"""

from decimal import Decimal

import pytest
from sqlalchemy import and_, select

from app.models.budget import Budget
from app.services import budget_service


def D(v) -> Decimal:
    return Decimal(str(v))


async def _caps(db, month, year):
    res = await db.execute(
        select(Budget).where(
            and_(Budget.month == month, Budget.year == year, Budget.subcategory_id.isnot(None))
        )
    )
    return {b.subcategory_id: (D(b.amount), b.locked) for b in res.scalars().all()}


class TestCopyBudgets:
    async def test_copies_caps_and_locks_to_empty_target(
        self, db_session, make_category, make_subcategory, make_budget, make_budget_month,
    ):
        cat = await make_category()
        sub_a = await make_subcategory(cat, name="A")
        sub_b = await make_subcategory(cat, name="B")
        await make_budget_month(5, 2026)
        await make_budget(cat, sub_a, 5, 2026, amount=D("300"), locked=True)
        await make_budget(cat, sub_b, 5, 2026, amount=D("150"))

        copied = await budget_service.copy_budgets(db_session, 5, 2026, 6, 2026)

        assert copied == 2
        target = await _caps(db_session, 6, 2026)
        assert target[sub_a.id] == (D("300"), True)
        assert target[sub_b.id] == (D("150"), False)

    async def test_overwrite_replaces_existing_target_caps(
        self, db_session, make_category, make_subcategory, make_budget, make_budget_month,
    ):
        cat = await make_category()
        sub = await make_subcategory(cat)
        await make_budget_month(5, 2026)
        await make_budget(cat, sub, 5, 2026, amount=D("300"))
        await make_budget(cat, sub, 6, 2026, amount=D("999"))  # pre-existing target

        copied = await budget_service.copy_budgets(db_session, 5, 2026, 6, 2026, overwrite=True)

        assert copied == 1
        assert (await _caps(db_session, 6, 2026))[sub.id][0] == D("300")

    async def test_no_overwrite_only_fills_gaps(
        self, db_session, make_category, make_subcategory, make_budget, make_budget_month,
    ):
        cat = await make_category()
        sub_existing = await make_subcategory(cat, name="Existing")
        sub_new = await make_subcategory(cat, name="New")
        await make_budget_month(5, 2026)
        await make_budget(cat, sub_existing, 5, 2026, amount=D("300"))
        await make_budget(cat, sub_new, 5, 2026, amount=D("100"))
        await make_budget(cat, sub_existing, 6, 2026, amount=D("999"))  # keep this

        copied = await budget_service.copy_budgets(db_session, 5, 2026, 6, 2026, overwrite=False)

        assert copied == 1  # only sub_new added
        target = await _caps(db_session, 6, 2026)
        assert target[sub_existing.id][0] == D("999")  # untouched
        assert target[sub_new.id][0] == D("100")

    async def test_same_month_is_noop(
        self, db_session, make_category, make_subcategory, make_budget, make_budget_month,
    ):
        cat = await make_category()
        sub = await make_subcategory(cat)
        await make_budget_month(5, 2026)
        await make_budget(cat, sub, 5, 2026, amount=D("300"))

        copied = await budget_service.copy_budgets(db_session, 5, 2026, 5, 2026)
        assert copied == 0

    async def test_empty_source_copies_nothing(
        self, db_session, make_category, make_subcategory,
    ):
        cat = await make_category()
        await make_subcategory(cat)
        copied = await budget_service.copy_budgets(db_session, 5, 2026, 6, 2026)
        assert copied == 0
