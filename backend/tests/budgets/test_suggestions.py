"""
Integration tests for AI budget suggestions v2 (budget_service.suggest_budget_v2)
and the bulk apply path (FR-5).

The AI provider call is stubbed so behaviour is deterministic: we test the
heuristic fallback and the sanitization rules (positive, $5 multiples, ≤3×
historical max, locked caps untouched) without hitting a real model.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.budget import Budget
from app.schemas.budget import ApplySuggestionItem
from app.services import ai_service, budget_service


def D(v) -> Decimal:
    return Decimal(str(v))


@pytest.fixture
def stub_ai(monkeypatch):
    """Stub budget_service's AI call. Pass a {subcategory_id: amount} map to
    simulate a successful provider, or None to simulate total AI failure."""
    def _install(amount_map):
        if amount_map is None:
            async def _fail(context):
                raise RuntimeError("no provider")
            monkeypatch.setattr(budget_service.ai_service, "suggest_budget_v2", _fail)
        else:
            async def _ok(context):
                return (
                    {sid: {"amount": amt, "rationale": "stub"} for sid, amt in amount_map.items()},
                    "groq",
                )
            monkeypatch.setattr(budget_service.ai_service, "suggest_budget_v2", _ok)
    return _install


def _row(resp, subcategory_id):
    return next(s for s in resp.suggestions if s.subcategory_id == subcategory_id)


class TestHeuristicFallback:
    async def test_uses_3month_average_rounded_to_5(
        self, db_session, stub_ai, make_account, make_category, make_subcategory,
        make_transaction,
    ):
        stub_ai(None)  # force heuristic
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        # 6-month window before June 2026 is Dec..May; only the last 3 feed the
        # heuristic: (100 + 200 + 300) / 3 = 200.
        await make_transaction(acct, sub, "2026-03-15", amount=D("100"))
        await make_transaction(acct, sub, "2026-04-15", amount=D("200"))
        await make_transaction(acct, sub, "2026-05-15", amount=D("300"))

        resp = await budget_service.suggest_budget_v2(db_session, 6, 2026)

        assert resp.source == "heuristic"
        assert resp.provider is None
        row = _row(resp, sub.id)
        assert row.suggested_amount == D("200")
        assert row.historical_max == D("300")
        assert row.is_currently_budgeted is False
        assert row.is_unbudgeted_candidate is True

    async def test_subcategory_without_history_is_skipped(
        self, db_session, stub_ai, make_category, make_subcategory,
    ):
        stub_ai(None)
        cat = await make_category()
        sub = await make_subcategory(cat)  # no transactions, not budgeted

        resp = await budget_service.suggest_budget_v2(db_session, 6, 2026)

        assert all(s.subcategory_id != sub.id for s in resp.suggestions)


class TestSanitization:
    async def test_ai_amount_clamped_to_3x_historical_max(
        self, db_session, stub_ai, make_account, make_category, make_subcategory,
        make_transaction,
    ):
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        await make_transaction(acct, sub, "2026-05-10", amount=D("100"))  # max 100 → limit 300
        stub_ai({str(sub.id): 100000})

        resp = await budget_service.suggest_budget_v2(db_session, 6, 2026)

        assert resp.source == "ai"
        assert resp.provider == "groq"
        assert _row(resp, sub.id).suggested_amount == D("300")

    async def test_ai_amount_rounded_to_5(
        self, db_session, stub_ai, make_account, make_category, make_subcategory,
        make_transaction,
    ):
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        await make_transaction(acct, sub, "2026-05-10", amount=D("1000"))  # limit 3000
        stub_ai({str(sub.id): 147})

        resp = await budget_service.suggest_budget_v2(db_session, 6, 2026)

        assert _row(resp, sub.id).suggested_amount == D("145")

    async def test_locked_cap_untouched(
        self, db_session, stub_ai, make_account, make_category, make_subcategory,
        make_budget, make_transaction,
    ):
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        await make_budget(cat, sub, 6, 2026, amount=D("250"), locked=True)
        await make_transaction(acct, sub, "2026-05-10", amount=D("90"))
        stub_ai({str(sub.id): 999})  # AI tries to change it

        resp = await budget_service.suggest_budget_v2(db_session, 6, 2026)

        row = _row(resp, sub.id)
        assert row.locked is True
        assert row.suggested_amount == D("250")  # unchanged
        assert resp.total_locked == D("250")


class TestApplySuggestions:
    async def test_bulk_apply_sets_caps(
        self, db_session, make_category, make_subcategory,
    ):
        cat = await make_category()
        sub1 = await make_subcategory(cat, name="A")
        sub2 = await make_subcategory(cat, name="B")

        applied = await budget_service.apply_suggestions(
            db_session, 6, 2026,
            [
                ApplySuggestionItem(subcategory_id=sub1.id, amount=D("100")),
                ApplySuggestionItem(subcategory_id=sub2.id, amount=D("250")),
            ],
        )

        assert applied == 2
        rows = await db_session.execute(
            select(Budget).where(Budget.month == 6, Budget.year == 2026)
        )
        caps = {b.subcategory_id: D(b.amount) for b in rows.scalars().all()}
        assert caps == {sub1.id: D("100"), sub2.id: D("250")}


class TestSeasonality:
    @pytest.fixture
    def capture_ai(self, monkeypatch):
        captured = {}
        async def _capture(context):
            captured["context"] = context
            return ({}, "groq")
        monkeypatch.setattr(budget_service.ai_service, "suggest_budget_v2", _capture)
        return captured

    async def test_seasonal_inputs_when_12_months_history(
        self, db_session, capture_ai, make_account, make_category, make_subcategory,
        make_transaction,
    ):
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        # Same month last year (June 2025) → seasonal comparison input; this also
        # makes the earliest txn exactly 12 months before the June 2026 target.
        await make_transaction(acct, sub, "2025-06-15", amount=D("500"))
        await make_transaction(acct, sub, "2026-05-10", amount=D("100"))

        await budget_service.suggest_budget_v2(db_session, 6, 2026)

        ctx = capture_ai["context"]
        assert ctx["seasonal"] is True
        assert ctx["upcoming_month"] == "June"
        item = next(i for i in ctx["items"] if i["subcategory_id"] == str(sub.id))
        assert D(item["prior_year_same_month"]) == D("500")

    async def test_not_seasonal_when_history_too_short(
        self, db_session, capture_ai, make_account, make_category, make_subcategory,
        make_transaction,
    ):
        acct = await make_account()
        cat = await make_category()
        sub = await make_subcategory(cat)
        await make_transaction(acct, sub, "2026-05-10", amount=D("100"))  # ~1 month

        await budget_service.suggest_budget_v2(db_session, 6, 2026)

        assert capture_ai["context"]["seasonal"] is False

    def test_prompt_includes_seasonal_section_only_when_seasonal(self):
        base_item = {
            "subcategory_id": "x", "category_name": "Food", "subcategory_name": "Dining",
            "monthly_avg": D("100"), "historical_max": D("200"),
            "current_cap": D("0"), "locked": False, "prior_year_same_month": D("150"),
        }
        ctx = {
            "last_month_income": D("1000"), "months_back": 6,
            "seasonal": True, "upcoming_month": "June", "items": [base_item],
        }
        prompt = ai_service._build_suggest_prompt(ctx)
        assert "same_month_last_year" in prompt
        assert "June" in prompt

        ctx_off = {**ctx, "seasonal": False, "upcoming_month": None}
        assert "same_month_last_year" not in ai_service._build_suggest_prompt(ctx_off)
