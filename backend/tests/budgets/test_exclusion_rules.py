"""
Integration tests for the exclusion rules engine (budget_service.apply_exclusion_rules, FR-4.3).

Covers matching by each rule type, the manual-flag-always-wins guarantee, the
clear-when-no-longer-matched path, and re-settlement of a settled month when an
exclusion changes its netted spend.
"""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.exclusion_rule import BudgetExclusionRule
from app.models.saved_balance import SavedBalance, SavedBalanceEvent
from app.services import budget_lifecycle, budget_service


def D(v) -> Decimal:
    return Decimal(str(v))


async def _add_rule(db, rule_type, match_value, active=True):
    rule = BudgetExclusionRule(
        rule_type=rule_type, match_value=str(match_value), active=active
    )
    db.add(rule)
    await db.flush()
    return rule


async def _balance(db, subcategory_id):
    row = await db.execute(
        select(SavedBalance.balance).where(
            SavedBalance.subcategory_id == subcategory_id
        )
    )
    val = row.scalar_one_or_none()
    return D(val) if val is not None else None


class TestRuleMatching:
    async def test_merchant_match_by_merchant_name(
        self, db_session, make_account, make_category, make_subcategory, make_transaction
    ):
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        txn = await make_transaction(
            acct, sub, "2026-06-10", amount=D("40"), merchant_name="Robinhood"
        )
        await _add_rule(db_session, "merchant_match", "robinhood")

        changed = await budget_service.apply_exclusion_rules(db_session, [txn])

        assert changed == 1
        assert txn.budget_excluded is True
        assert txn.budget_excluded_source == "rule"

    async def test_merchant_match_by_raw_description(
        self, db_session, make_account, make_category, make_subcategory, make_transaction
    ):
        # Matches raw_description even when merchant_name doesn't contain it —
        # this is what keeps a rule stable across enrichment renames.
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        txn = await make_transaction(
            acct, sub, "2026-06-10", amount=D("40"),
            merchant_name="Acme", raw_description="VENMO PAYMENT 123",
        )
        await _add_rule(db_session, "merchant_match", "venmo")

        changed = await budget_service.apply_exclusion_rules(db_session, [txn])

        assert changed == 1
        assert txn.budget_excluded is True

    async def test_category_rule(
        self, db_session, make_account, make_category, make_subcategory, make_transaction
    ):
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        txn = await make_transaction(acct, sub, "2026-06-10", amount=D("40"))
        await _add_rule(db_session, "category", cat.id)

        changed = await budget_service.apply_exclusion_rules(db_session, [txn])

        assert changed == 1
        assert txn.budget_excluded is True

    async def test_subcategory_rule(
        self, db_session, make_account, make_category, make_subcategory, make_transaction
    ):
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        other = await make_subcategory(cat, name="Other")
        txn = await make_transaction(acct, sub, "2026-06-10", amount=D("40"))
        other_txn = await make_transaction(acct, other, "2026-06-10", amount=D("40"))
        await _add_rule(db_session, "subcategory", sub.id)

        changed = await budget_service.apply_exclusion_rules(db_session, [txn, other_txn])

        assert changed == 1
        assert txn.budget_excluded is True
        assert other_txn.budget_excluded is False

    async def test_no_active_rules_is_noop(
        self, db_session, make_account, make_category, make_subcategory, make_transaction
    ):
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        txn = await make_transaction(acct, sub, "2026-06-10", amount=D("40"))
        await _add_rule(db_session, "merchant_match", "robinhood", active=False)

        changed = await budget_service.apply_exclusion_rules(db_session, [txn])

        assert changed == 0
        assert txn.budget_excluded is False


class TestManualOverride:
    async def test_manual_excluded_not_touched_when_rule_would_clear(
        self, db_session, make_account, make_category, make_subcategory, make_transaction
    ):
        # A hand-excluded txn stays excluded even though no rule matches it.
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        txn = await make_transaction(acct, sub, "2026-06-10", amount=D("40"))
        txn.budget_excluded = True
        txn.budget_excluded_source = "manual"
        await db_session.flush()
        await _add_rule(db_session, "merchant_match", "something-else")

        changed = await budget_service.apply_exclusion_rules(db_session, [txn])

        assert changed == 0
        assert txn.budget_excluded is True
        assert txn.budget_excluded_source == "manual"

    async def test_manual_included_not_overwritten_by_matching_rule(
        self, db_session, make_account, make_category, make_subcategory, make_transaction
    ):
        # A hand-included txn (source manual, not excluded) is never re-excluded
        # by a matching rule — the manual choice wins.
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        txn = await make_transaction(
            acct, sub, "2026-06-10", amount=D("40"), merchant_name="Robinhood"
        )
        txn.budget_excluded = False
        txn.budget_excluded_source = "manual"
        await db_session.flush()
        await _add_rule(db_session, "merchant_match", "robinhood")

        changed = await budget_service.apply_exclusion_rules(db_session, [txn])

        assert changed == 0
        assert txn.budget_excluded is False
        assert txn.budget_excluded_source == "manual"


class TestClearPath:
    async def test_rule_excluded_cleared_when_no_rule_matches(
        self, db_session, make_account, make_category, make_subcategory, make_transaction
    ):
        # A txn previously excluded by a rule is re-included when re-evaluated
        # against rules that no longer match it.
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        txn = await make_transaction(acct, sub, "2026-06-10", amount=D("40"))
        txn.budget_excluded = True
        txn.budget_excluded_source = "rule"
        await db_session.flush()
        await _add_rule(db_session, "merchant_match", "does-not-match")

        changed = await budget_service.apply_exclusion_rules(db_session, [txn])

        assert changed == 1
        assert txn.budget_excluded is False
        assert txn.budget_excluded_source is None


class TestReconcileOnExclusion:
    async def test_excluding_in_settled_month_resettles(
        self, db_session, make_account, make_category, make_subcategory,
        make_budget, make_budget_month, make_transaction,
    ):
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        await make_budget_month(5, 2026)
        await make_budget(cat, sub, 5, 2026, amount=D("300"))
        txn = await make_transaction(
            acct, sub, "2026-05-10", amount=D("250"), merchant_name="Robinhood"
        )
        await budget_lifecycle.settle_month(db_session, 5, 2026)
        assert await _balance(db_session, sub.id) == D("50")  # 300 - 250 surplus

        await _add_rule(db_session, "merchant_match", "robinhood")
        changed = await budget_service.apply_exclusion_rules(db_session, [txn])

        # Excluding the $250 spend lifts netted spend to 0 → full $300 surplus.
        assert changed == 1
        assert await _balance(db_session, sub.id) == D("300")
        recompute = await db_session.scalar(
            select(func.count())
            .select_from(SavedBalanceEvent)
            .where(SavedBalanceEvent.reason == SavedBalanceEvent.REASON_RECOMPUTE)
        )
        assert recompute == 1
