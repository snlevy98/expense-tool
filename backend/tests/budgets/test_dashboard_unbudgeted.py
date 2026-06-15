"""
The reports dashboard surfaces spending in subcategories that have no budget cap
for the month (report_service.get_dashboard → unbudgeted_spending).
"""

from decimal import Decimal

import pytest

from app.services import report_service


def D(v) -> Decimal:
    return Decimal(str(v))


def _unbudgeted(resp):
    return {r.subcategory_id: D(r.spent) for r in resp.unbudgeted_spending}


class TestDashboardUnbudgetedSpending:
    async def test_lists_only_uncapped_subcategories_with_spend(
        self, db_session, make_account, make_category, make_subcategory,
        make_budget, make_transaction,
    ):
        acct = await make_account()
        cat = await make_category()
        capped = await make_subcategory(cat, name="Capped")
        loose = await make_subcategory(cat, name="Loose")
        await make_budget(cat, capped, 6, 2026, amount=D("100"))  # capped
        await make_transaction(acct, capped, "2026-06-05", amount=D("50"))
        await make_transaction(acct, loose, "2026-06-06", amount=D("80"))

        resp = await report_service.get_dashboard(db_session, 6, 2026)

        ub = _unbudgeted(resp)
        assert ub == {str(loose.id): D("80")}
        assert D(resp.total_unbudgeted_spent) == D("80")

    async def test_excluded_transactions_and_refund_only_subs_omitted(
        self, db_session, make_account, make_category, make_subcategory, make_transaction,
    ):
        acct = await make_account()
        cat = await make_category()
        excluded_only = await make_subcategory(cat, name="ExcludedOnly")
        refund_only = await make_subcategory(cat, name="RefundOnly")
        await make_transaction(acct, excluded_only, "2026-06-05", amount=D("200"), budget_excluded=True)
        await make_transaction(acct, refund_only, "2026-06-06", amount=D("-30"))  # net < 0

        resp = await report_service.get_dashboard(db_session, 6, 2026)

        assert resp.unbudgeted_spending == []
        assert D(resp.total_unbudgeted_spent) == D("0")

    async def test_sorted_by_spend_descending(
        self, db_session, make_account, make_category, make_subcategory, make_transaction,
    ):
        acct = await make_account()
        cat = await make_category()
        small = await make_subcategory(cat, name="Small")
        big = await make_subcategory(cat, name="Big")
        await make_transaction(acct, small, "2026-06-05", amount=D("40"))
        await make_transaction(acct, big, "2026-06-06", amount=D("400"))

        resp = await report_service.get_dashboard(db_session, 6, 2026)

        assert [r.subcategory_id for r in resp.unbudgeted_spending] == [str(big.id), str(small.id)]
