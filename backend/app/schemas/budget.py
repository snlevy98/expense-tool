import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Dashboard payload (FR-6.1–6.3)
# ---------------------------------------------------------------------------

class SubcategoryBudgetRow(BaseModel):
    budget_id: uuid.UUID
    subcategory_id: uuid.UUID
    subcategory_name: str
    cap: Decimal
    spent: Decimal              # netted (FR-4.1), exclusions filtered (FR-4.2)
    remaining: Decimal          # cap - spent (saved balance never raises it, FR-3.3)
    saved_balance: Decimal
    locked: bool
    overage: Decimal            # max(0, spent - cap)
    covered_overage: Decimal    # min(overage, saved_balance) — provisional (FR-3.2)
    net_overage: Decimal        # overage - covered_overage
    status: Literal["on_track", "approaching", "covered", "over"]


class CategoryBudgetGroup(BaseModel):
    category_id: uuid.UUID
    category_name: str
    category_color: str
    total_cap: Decimal
    total_spent: Decimal
    total_remaining: Decimal
    total_saved: Decimal
    subcategories: list[SubcategoryBudgetRow]


class UnbudgetedSubcategory(BaseModel):
    category_id: uuid.UUID
    category_name: str
    subcategory_id: uuid.UUID
    subcategory_name: str


class BudgetSummary(BaseModel):
    total_budgeted: Decimal
    total_spent: Decimal
    total_remaining: Decimal
    coverage_drawn: Decimal       # sum of provisional covered overages
    net_overage_count: int        # subcategories with net overage (FR-6.3)


class BudgetDashboardResponse(BaseModel):
    month: int
    year: int
    is_closed: bool               # caps/locks read-only (FR-2.4)
    summary: BudgetSummary
    categories: list[CategoryBudgetGroup]
    unbudgeted: list[UnbudgetedSubcategory]


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

class CapUpdate(BaseModel):
    amount: Decimal = Field(gt=0)  # FR-1.2


class LockUpdate(BaseModel):
    locked: bool


class SavedBalanceReset(BaseModel):
    value: Decimal = Field(default=Decimal("0"), ge=0)  # FR-3.4


class SavedBalanceOut(BaseModel):
    subcategory_id: uuid.UUID
    subcategory_name: str
    balance: Decimal


class BudgetExclusionUpdate(BaseModel):
    budget_excluded: bool


class ExclusionRuleCreate(BaseModel):
    rule_type: Literal["category", "subcategory", "merchant_match"]
    match_value: str = Field(min_length=1, max_length=200)
    active: bool = True


class ExclusionRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_type: str
    match_value: str
    active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# AI suggestions — legacy shape, replaced in the suggestions-v2 chunk
# ---------------------------------------------------------------------------

class BudgetSuggestRequest(BaseModel):
    allocation: Decimal
    months_back: int = 3


class BudgetSuggestionItem(BaseModel):
    id: str
    subcategory_id: uuid.UUID | None
    subcategory_name: str | None
    category_id: uuid.UUID
    category_name: str
    monthly_avg: Decimal
    suggested_amount: Decimal


class BudgetSuggestResponse(BaseModel):
    suggestions: list[BudgetSuggestionItem]
    total_suggested: Decimal
    allocation: Decimal
