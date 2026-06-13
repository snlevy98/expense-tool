"""
Business logic for envelope budgets: dashboard payload, cap/lock mutations,
unbudgeting, saved balances, and exclusion rules.

Opt-in semantics (FR-1.1): a budgets row's presence means the subcategory is
budgeted. Nothing is auto-seeded. Envelope math only reads subcategory rows;
legacy category-level rows (subcategory_id IS NULL) are historical-report
data only.
"""

import uuid
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.budget import Budget
from app.models.category import Category
from app.models.exclusion_rule import BudgetExclusionRule
from app.models.saved_balance import SavedBalance, SavedBalanceEvent
from app.models.subcategory import Subcategory
from app.models.transaction import Transaction
from app.schemas.budget import (
    BudgetDashboardResponse,
    BudgetSummary,
    CategoryBudgetGroup,
    ExclusionRuleCreate,
    SavedBalanceOut,
    SubcategoryBudgetRow,
    UnbudgetedSubcategory,
)
from app.services import budget_lifecycle, budget_math
from app.services.budget_math import ZERO


# ---------------------------------------------------------------------------
# Income helper (kept for AI-suggestion inputs, FR-5.2)
# ---------------------------------------------------------------------------

async def get_last_month_income(db: AsyncSession, month: int, year: int) -> Decimal:
    """
    Return total income for the month BEFORE (month, year).
    Income = abs(sum of negative-amount transactions in the Income-category).
    """
    prev_m, prev_y = budget_math.prev_month(month, year)
    start_date, end_date = budget_math.month_range(prev_m, prev_y)

    # Find the Income category (budget_excluded=True, name matching "Income")
    cat_result = await db.execute(
        select(Category).where(
            Category.budget_excluded == True,  # noqa: E712
            func.lower(Category.name) == "income",
        )
    )
    income_cat = cat_result.scalar_one_or_none()
    if income_cat is None:
        return ZERO

    result = await db.execute(
        select(func.sum(Transaction.amount)).where(
            and_(
                Transaction.category_id == income_cat.id,
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date < end_date,
            )
        )
    )
    total = result.scalar_one_or_none()
    if total is None:
        return ZERO
    # Negate because income credits are stored as negative amounts
    return abs(Decimal(str(total)))


# ---------------------------------------------------------------------------
# Dashboard payload (FR-6.1–6.3)
# ---------------------------------------------------------------------------

def _row_status(
    cap: Decimal, spent: Decimal, covered: Decimal, net: Decimal
) -> str:
    """Progress-bar state per FR-6.2."""
    if net > 0:
        return "over"
    if spent > cap:
        return "covered"
    if cap > 0 and spent >= cap * Decimal("0.8"):
        return "approaching"
    return "on_track"


async def get_budget_dashboard(
    db: AsyncSession, month: int, year: int
) -> BudgetDashboardResponse:
    await budget_lifecycle.ensure_month(db, month, year)

    cat_result = await db.execute(
        select(Category)
        .where(
            Category.is_active == True,  # noqa: E712
            Category.budget_excluded == False,  # noqa: E712
        )
        .options(selectinload(Category.subcategories))
    )
    categories = cat_result.scalars().all()

    budget_result = await db.execute(
        select(Budget).where(
            and_(
                Budget.month == month,
                Budget.year == year,
                Budget.subcategory_id.isnot(None),
            )
        )
    )
    budgets_by_sub: dict[uuid.UUID, Budget] = {
        b.subcategory_id: b for b in budget_result.scalars().all()
    }

    spent_map = await budget_math.get_spent_by_subcategory(db, month, year)

    balance_result = await db.execute(select(SavedBalance))
    balance_map: dict[uuid.UUID, Decimal] = {
        sb.subcategory_id: Decimal(str(sb.balance))
        for sb in balance_result.scalars().all()
    }

    groups: list[CategoryBudgetGroup] = []
    unbudgeted: list[UnbudgetedSubcategory] = []
    total_budgeted = ZERO
    total_spent = ZERO
    coverage_drawn = ZERO
    net_overage_count = 0

    for cat in categories:
        active_subs = [s for s in cat.subcategories if s.is_active]
        rows: list[SubcategoryBudgetRow] = []

        for sub in active_subs:
            b = budgets_by_sub.get(sub.id)
            if b is None:
                unbudgeted.append(
                    UnbudgetedSubcategory(
                        category_id=cat.id,
                        category_name=cat.name,
                        subcategory_id=sub.id,
                        subcategory_name=sub.name,
                    )
                )
                continue

            cap = Decimal(str(b.amount))
            spent = spent_map.get(sub.id, ZERO)
            saved = balance_map.get(sub.id, ZERO)
            overage = max(ZERO, spent - cap)
            covered = min(overage, saved)
            net = overage - covered

            rows.append(
                SubcategoryBudgetRow(
                    budget_id=b.id,
                    subcategory_id=sub.id,
                    subcategory_name=sub.name,
                    cap=cap,
                    spent=spent,
                    remaining=cap - spent,
                    saved_balance=saved,
                    locked=b.locked,
                    overage=overage,
                    covered_overage=covered,
                    net_overage=net,
                    status=_row_status(cap, spent, covered, net),
                )
            )

            total_budgeted += cap
            total_spent += spent
            coverage_drawn += covered
            if net > 0:
                net_overage_count += 1

        if rows:
            groups.append(
                CategoryBudgetGroup(
                    category_id=cat.id,
                    category_name=cat.name,
                    category_color=cat.color,
                    total_cap=sum((r.cap for r in rows), ZERO),
                    total_spent=sum((r.spent for r in rows), ZERO),
                    total_remaining=sum((r.remaining for r in rows), ZERO),
                    total_saved=sum((r.saved_balance for r in rows), ZERO),
                    subcategories=rows,
                )
            )

    return BudgetDashboardResponse(
        month=month,
        year=year,
        is_closed=budget_lifecycle.is_closed_month(month, year),
        summary=BudgetSummary(
            total_budgeted=total_budgeted,
            total_spent=total_spent,
            total_remaining=total_budgeted - total_spent,
            coverage_drawn=coverage_drawn,
            net_overage_count=net_overage_count,
        ),
        categories=groups,
        unbudgeted=unbudgeted,
    )


# ---------------------------------------------------------------------------
# Cap / lock / unbudget mutations (FR-1.x)
# ---------------------------------------------------------------------------

async def _get_subcategory(
    db: AsyncSession, subcategory_id: uuid.UUID
) -> Subcategory | None:
    result = await db.execute(
        select(Subcategory)
        .where(Subcategory.id == subcategory_id)
        .options(selectinload(Subcategory.category))
    )
    return result.scalar_one_or_none()


async def _get_budget_row(
    db: AsyncSession, subcategory_id: uuid.UUID, month: int, year: int
) -> Budget | None:
    result = await db.execute(
        select(Budget).where(
            and_(
                Budget.subcategory_id == subcategory_id,
                Budget.month == month,
                Budget.year == year,
            )
        )
    )
    return result.scalar_one_or_none()


async def set_subcategory_cap(
    db: AsyncSession,
    subcategory_id: uuid.UUID,
    month: int,
    year: int,
    amount: Decimal,
) -> Budget | None:
    """Create (= opt in, FR-1.1/1.4) or update (FR-1.6) a subcategory cap.
    Returns None if the subcategory does not exist or is income-side (FR-1.8).
    """
    sub = await _get_subcategory(db, subcategory_id)
    if sub is None or sub.category.budget_excluded:
        return None

    budget = await _get_budget_row(db, subcategory_id, month, year)
    if budget:
        budget.amount = amount
    else:
        budget = Budget(
            id=uuid.uuid4(),
            category_id=sub.category_id,
            subcategory_id=subcategory_id,
            month=month,
            year=year,
            amount=amount,
            locked=False,
        )
        db.add(budget)
        # Opting in creates the saved-balance pool at $0 (FR-1.5: fresh start)
        existing_balance = await db.execute(
            select(SavedBalance).where(
                SavedBalance.subcategory_id == subcategory_id
            )
        )
        if existing_balance.scalar_one_or_none() is None:
            db.add(SavedBalance(subcategory_id=subcategory_id, balance=ZERO))

    await db.flush()
    await db.refresh(budget)
    return budget


async def set_subcategory_lock(
    db: AsyncSession,
    subcategory_id: uuid.UUID,
    month: int,
    year: int,
    locked: bool,
) -> Budget | None:
    budget = await _get_budget_row(db, subcategory_id, month, year)
    if budget is None:
        return None
    budget.locked = locked
    await db.flush()
    return budget


async def remove_subcategory_budget(
    db: AsyncSession, subcategory_id: uuid.UUID, month: int, year: int
) -> bool:
    """Unbudget (FR-1.5): delete the month's cap row and the saved balance,
    logging an unbudgeted_deleted event. Historical months keep their data."""
    budget = await _get_budget_row(db, subcategory_id, month, year)
    if budget is None:
        return False
    await db.delete(budget)

    balance_result = await db.execute(
        select(SavedBalance).where(SavedBalance.subcategory_id == subcategory_id)
    )
    balance_row = balance_result.scalar_one_or_none()
    if balance_row is not None:
        balance = Decimal(str(balance_row.balance))
        db.add(
            SavedBalanceEvent(
                id=uuid.uuid4(),
                subcategory_id=subcategory_id,
                delta=-balance,
                balance_after=ZERO,
                reason=SavedBalanceEvent.REASON_UNBUDGETED,
            )
        )
        await db.delete(balance_row)

    await db.flush()
    return True


# ---------------------------------------------------------------------------
# Saved balances (FR-3.4, FR-3.5)
# ---------------------------------------------------------------------------

async def list_saved_balances(db: AsyncSession) -> list[SavedBalanceOut]:
    result = await db.execute(
        select(SavedBalance).options(selectinload(SavedBalance.subcategory))
    )
    return [
        SavedBalanceOut(
            subcategory_id=sb.subcategory_id,
            subcategory_name=sb.subcategory.name if sb.subcategory else "",
            balance=Decimal(str(sb.balance)),
        )
        for sb in result.scalars().all()
    ]


async def reset_saved_balance(
    db: AsyncSession, subcategory_id: uuid.UUID, value: Decimal
) -> SavedBalance | None:
    """Manually set a saved balance to any value >= 0 (FR-3.4), audited."""
    result = await db.execute(
        select(SavedBalance)
        .where(SavedBalance.subcategory_id == subcategory_id)
        .options(selectinload(SavedBalance.subcategory))
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    old = Decimal(str(row.balance))
    if value != old:
        row.balance = value
        db.add(
            SavedBalanceEvent(
                id=uuid.uuid4(),
                subcategory_id=subcategory_id,
                delta=value - old,
                balance_after=value,
                reason=SavedBalanceEvent.REASON_MANUAL_RESET,
            )
        )
        await db.flush()
    return row


# ---------------------------------------------------------------------------
# Exclusion rules (FR-4.3) — applied at import in the exclusions chunk
# ---------------------------------------------------------------------------

async def list_exclusion_rules(db: AsyncSession) -> list[BudgetExclusionRule]:
    result = await db.execute(
        select(BudgetExclusionRule).order_by(BudgetExclusionRule.created_at)
    )
    return list(result.scalars().all())


async def create_exclusion_rule(
    db: AsyncSession, body: ExclusionRuleCreate
) -> BudgetExclusionRule:
    rule = BudgetExclusionRule(
        id=uuid.uuid4(),
        rule_type=body.rule_type,
        match_value=body.match_value,
        active=body.active,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


async def delete_exclusion_rule(db: AsyncSession, rule_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(BudgetExclusionRule).where(BudgetExclusionRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        return False
    await db.delete(rule)
    await db.flush()
    return True


# ---------------------------------------------------------------------------
# Exclusion rules engine (FR-4.3) — applied at import confirm and re-applied
# after background enrichment normalizes merchant names.
# ---------------------------------------------------------------------------

def _rule_matches(rule: BudgetExclusionRule, txn: Transaction) -> bool:
    if rule.rule_type == "category":
        return txn.category_id is not None and str(txn.category_id) == rule.match_value
    if rule.rule_type == "subcategory":
        return (
            txn.subcategory_id is not None
            and str(txn.subcategory_id) == rule.match_value
        )
    if rule.rule_type == "merchant_match":
        needle = rule.match_value.lower()
        # raw_description is checked too so a rule still matches after enrichment
        # renames merchant_name (and never un-matches a name it caught pre-rename).
        return (
            needle in (txn.merchant_name or "").lower()
            or needle in (txn.raw_description or "").lower()
        )
    return False


async def apply_exclusion_rules(
    db: AsyncSession,
    transactions: list[Transaction],
    rules: list[BudgetExclusionRule] | None = None,
) -> int:
    """Apply active exclusion rules to ``transactions`` (FR-4.3).

    For each non-manual transaction, recompute whether any active rule matches:
    a match sets ``budget_excluded=True`` / ``source='rule'``; if nothing matches
    and the flag was previously rule-set, it is cleared. Manual flags
    (``source='manual'``) are never touched — the manual choice always wins.
    Settled months affected by a change are re-settled. Returns the count of
    transactions whose flag changed. The caller commits.
    """
    if not transactions:
        return 0
    if rules is None:
        result = await db.execute(
            select(BudgetExclusionRule).where(BudgetExclusionRule.active == True)  # noqa: E712
        )
        rules = list(result.scalars().all())
    if not rules:
        return 0

    snapshots: list[dict] = []
    changed = 0
    for txn in transactions:
        if txn.budget_excluded_source == "manual":
            continue
        matched = any(_rule_matches(r, txn) for r in rules)
        if matched and not txn.budget_excluded:
            before = budget_lifecycle.budget_snapshot(txn)
            txn.budget_excluded = True
            txn.budget_excluded_source = "rule"
            snapshots += [before, budget_lifecycle.budget_snapshot(txn)]
            changed += 1
        elif (
            not matched
            and txn.budget_excluded
            and txn.budget_excluded_source == "rule"
        ):
            before = budget_lifecycle.budget_snapshot(txn)
            txn.budget_excluded = False
            txn.budget_excluded_source = None
            snapshots += [before, budget_lifecycle.budget_snapshot(txn)]
            changed += 1

    if changed:
        await db.flush()
        await budget_lifecycle.reconcile_transaction_change(db, snapshots)
    return changed
