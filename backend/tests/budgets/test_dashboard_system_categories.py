"""
The reports dashboard surfaces monthly activity in budget-excluded ("System")
categories like Income and Investments (report_service.get_dashboard →
system_categories).
"""

from decimal import Decimal

import pytest

from app.services import report_service


def D(v) -> Decimal:
    return Decimal(str(v))


def _by_name(resp):
    return {r.category_name: r for r in resp.system_categories}


class TestDashboardSystemCategories:
    async def test_lists_excluded_categories_with_signed_activity(
        self, db_session, make_account, make_category, make_subcategory, make_transaction,
    ):
        acct = await make_account()
        # Income is excluded; receipts are stored as negative amounts and stay
        # negative here (signed), matching the app-wide sign convention.
        income = await make_category(name="Income", budget_excluded=True)
        salary = await make_subcategory(income, name="Salary")
        invest = await make_category(name="Investments", budget_excluded=True)
        brokerage = await make_subcategory(invest, name="Brokerage")
        # A normal (budgeted) category should NOT appear here.
        food = await make_category(name="Food")
        dining = await make_subcategory(food, name="Dining")

        await make_transaction(acct, salary, "2026-06-01", amount=D("-5000"), category=income)
        await make_transaction(acct, brokerage, "2026-06-03", amount=D("1200"), category=invest)
        await make_transaction(acct, dining, "2026-06-04", amount=D("80"), category=food)

        resp = await report_service.get_dashboard(db_session, 6, 2026)

        rows = _by_name(resp)
        assert set(rows) == {"Income", "Investments"}
        assert rows["Income"].amount == D("-5000")          # signed net
        assert rows["Investments"].amount == D("1200")
        assert rows["Income"].subcategories[0].subcategory_name == "Salary"
        assert rows["Income"].subcategories[0].amount == D("-5000")

    async def test_excluded_category_with_no_activity_is_omitted(
        self, db_session, make_account, make_category, make_subcategory, make_transaction,
    ):
        acct = await make_account()
        income = await make_category(name="Income", budget_excluded=True)
        salary = await make_subcategory(income, name="Salary")
        await make_category(name="Investments", budget_excluded=True)  # no activity
        await make_transaction(acct, salary, "2026-06-01", amount=D("-3000"), category=income)

        resp = await report_service.get_dashboard(db_session, 6, 2026)

        assert [r.category_name for r in resp.system_categories] == ["Income"]

    async def test_sorted_by_amount_descending(
        self, db_session, make_account, make_category, make_subcategory, make_transaction,
    ):
        acct = await make_account()
        income = await make_category(name="Income", budget_excluded=True)
        salary = await make_subcategory(income, name="Salary")
        invest = await make_category(name="Investments", budget_excluded=True)
        brokerage = await make_subcategory(invest, name="Brokerage")
        await make_transaction(acct, salary, "2026-06-01", amount=D("-6000"), category=income)
        await make_transaction(acct, brokerage, "2026-06-03", amount=D("500"), category=invest)

        resp = await report_service.get_dashboard(db_session, 6, 2026)

        assert [r.category_name for r in resp.system_categories] == ["Income", "Investments"]
