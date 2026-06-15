"""
Integration tests for the budget history endpoint logic
(budget_service.get_budget_history).
"""

from decimal import Decimal

import pytest

from app.services import budget_lifecycle, budget_service


def D(v) -> Decimal:
    return Decimal(str(v))


def _point(resp, month, year):
    return next(p for p in resp.points if p.month == month and p.year == year)


class TestBudgetHistory:
    async def test_budget_vs_actual_with_coverage_and_trajectory(
        self, db_session, make_account, make_category, make_subcategory,
        make_budget, make_budget_month, make_transaction,
    ):
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)

        # May: cap 300, spent 250 → $50 surplus.
        await make_budget_month(5, 2026)
        await make_budget(cat, sub, 5, 2026, amount=D("300"))
        await make_transaction(acct, sub, "2026-05-10", amount=D("250"))
        # June: cap 300, spent 380 → $80 overage; $50 covered from May surplus.
        await make_budget_month(6, 2026)
        await make_budget(cat, sub, 6, 2026, amount=D("300"))
        await make_transaction(acct, sub, "2026-06-12", amount=D("380"))

        await budget_lifecycle.settle_month(db_session, 5, 2026)
        await budget_lifecycle.settle_month(db_session, 6, 2026)

        resp = await budget_service.get_budget_history(
            db_session, 5, 2026, 6, 2026, subcategory_id=sub.id
        )

        assert resp.scope == "subcategory"
        assert [(p.month, p.year) for p in resp.points] == [(5, 2026), (6, 2026)]

        may = _point(resp, 5, 2026)
        assert may.budget == D("300")
        assert may.spent == D("250")
        assert may.surplus == D("50")
        assert may.overage == D("0")
        assert may.saved_balance == D("50")  # after May settlement

        jun = _point(resp, 6, 2026)
        assert jun.budget == D("300")
        assert jun.spent == D("380")
        assert jun.overage == D("80")
        assert jun.covered_overage == D("50")
        assert jun.net_overage == D("30")
        assert jun.saved_balance == D("0")  # drained covering June

    async def test_label_and_empty_scope(
        self, db_session, make_category, make_subcategory,
    ):
        cat = await make_category()
        sub = await make_subcategory(cat)  # no budget, no spend

        resp = await budget_service.get_budget_history(
            db_session, 1, 2026, 3, 2026, subcategory_id=sub.id
        )

        # Three months, all zeroed, labels formatted.
        assert [p.label for p in resp.points] == ["Jan 2026", "Feb 2026", "Mar 2026"]
        assert all(p.budget == D("0") and p.spent == D("0") for p in resp.points)

    async def test_all_scope_aggregates_subcategories(
        self, db_session, make_account, make_category, make_subcategory,
        make_budget, make_budget_month, make_transaction,
    ):
        acct = await make_account()
        cat = await make_category()
        sub_a = await make_subcategory(cat, name="A")
        sub_b = await make_subcategory(cat, name="B")
        await make_budget_month(6, 2026)
        await make_budget(cat, sub_a, 6, 2026, amount=D("200"))
        await make_budget(cat, sub_b, 6, 2026, amount=D("100"))
        await make_transaction(acct, sub_a, "2026-06-05", amount=D("150"))
        await make_transaction(acct, sub_b, "2026-06-06", amount=D("90"))

        resp = await budget_service.get_budget_history(db_session, 6, 2026, 6, 2026)

        assert resp.scope == "all"
        jun = _point(resp, 6, 2026)
        assert jun.budget == D("300")   # 200 + 100
        assert jun.spent == D("240")    # 150 + 90
        assert jun.surplus == D("60")   # (200-150) + (100-90)
