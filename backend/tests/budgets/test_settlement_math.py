"""
Unit tests for the pure settlement math in app.services.budget_math.

Covers the requirements doc's key acceptance scenarios:
  #1 Rollover, #2 Coverage, #3 Net overage, #4 Refund recovers coverage,
  #9 Late edit (compensating recompute deltas).
"""

from datetime import date
from decimal import Decimal

from app.services.budget_math import (
    month_range,
    next_month,
    prev_month,
    recompute_delta,
    settlement_outcome,
)


def D(v: str) -> Decimal:
    return Decimal(v)


# ---------------------------------------------------------------------------
# Month helpers
# ---------------------------------------------------------------------------


class TestMonthHelpers:
    def test_month_range_mid_year(self):
        assert month_range(6, 2026) == (date(2026, 6, 1), date(2026, 7, 1))

    def test_month_range_december_wraps_year(self):
        assert month_range(12, 2026) == (date(2026, 12, 1), date(2027, 1, 1))

    def test_prev_month_january_wraps(self):
        assert prev_month(1, 2026) == (12, 2025)

    def test_next_month_december_wraps(self):
        assert next_month(12, 2026) == (1, 2027)

    def test_prev_next_roundtrip(self):
        for m in range(1, 13):
            nm, ny = next_month(m, 2026)
            assert prev_month(nm, ny) == (m, 2026)


# ---------------------------------------------------------------------------
# settlement_outcome (FR-2.3)
# ---------------------------------------------------------------------------


class TestSettlementOutcome:
    def test_scenario_1_rollover_surplus(self):
        # Dining Out capped at $300, spend $250 → saved balance +$50
        delta, reason = settlement_outcome(D("300"), D("250"), D("0"))
        assert delta == D("50")
        assert reason == "month_close_surplus"

    def test_scenario_2_coverage_partial_draw(self):
        # $50 saved, spend $330 against $300 → $30 covered; balance settles to $20
        delta, reason = settlement_outcome(D("300"), D("330"), D("50"))
        assert delta == D("-30")
        assert reason == "month_close_coverage"

    def test_scenario_3_net_overage_caps_at_balance(self):
        # Spend $380 against $300 with $50 saved → $50 covered, $30 net;
        # balance floors at 0, nothing carries as debt
        delta, reason = settlement_outcome(D("300"), D("380"), D("50"))
        assert delta == D("-50")
        assert reason == "month_close_coverage"

    def test_scenario_4_refund_recovers_before_close(self):
        # Mid-month overage erased by a refund before close: spent ends below
        # cap, so the close yields a surplus, not a deduction
        delta, reason = settlement_outcome(D("300"), D("290"), D("50"))
        assert delta == D("10")
        assert reason == "month_close_surplus"

    def test_exact_cap_is_noop(self):
        delta, reason = settlement_outcome(D("300"), D("300"), D("50"))
        assert delta == D("0")
        assert reason is None

    def test_overage_with_zero_balance_is_noop(self):
        delta, reason = settlement_outcome(D("300"), D("380"), D("0"))
        assert delta == D("0")
        assert reason is None

    def test_negative_spent_full_refund_month(self):
        # Refund-heavy month: spent is negative → surplus = cap - spent > cap
        delta, reason = settlement_outcome(D("100"), D("-25"), D("0"))
        assert delta == D("125")
        assert reason == "month_close_surplus"


# ---------------------------------------------------------------------------
# recompute_delta (FR-4.4)
# ---------------------------------------------------------------------------


class TestRecomputeDelta:
    def test_scenario_9_deleted_transaction_increases_surplus(self):
        # June settled with +50 surplus; a $40 June expense is deleted in July
        # → spent drops 250→210, expected surplus 90, compensating +40
        actual, discrepancy = recompute_delta(D("300"), D("210"), D("50"), D("50"))
        assert actual == D("40")
        assert discrepancy == D("0")

    def test_late_refund_returns_overdrawn_coverage(self):
        # Settled: spend 380 vs cap 300, coverage -50 applied (balance 50→0).
        # A $40 refund posts late → spent 340, expected -40 → give back +10
        actual, discrepancy = recompute_delta(D("300"), D("340"), D("-50"), D("0"))
        assert actual == D("10")
        assert discrepancy == D("0")

    def test_late_expense_flips_surplus_to_coverage_clamped(self):
        # Settled: surplus +50 applied (balance 0→50). A late $100 expense
        # makes the month an overage month: expected -50, delta -100, but only
        # 50 is drawable — balance floors at 0 and the rest is a discrepancy.
        actual, discrepancy = recompute_delta(D("300"), D("350"), D("50"), D("50"))
        assert actual == D("-50")
        assert discrepancy == D("-50")

    def test_no_change_is_noop(self):
        actual, discrepancy = recompute_delta(D("300"), D("250"), D("50"), D("50"))
        assert actual == D("0")
        assert discrepancy == D("0")

    def test_clamp_uses_current_balance(self):
        # Balance has grown since (later surpluses): a deeper correction can draw
        # against the current pool
        actual, discrepancy = recompute_delta(D("300"), D("381"), D("-50"), D("100"))
        # expected = -81, applied = -50, delta = -31, drawable within 100
        assert actual == D("-31")
        assert discrepancy == D("0")
