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
# AI suggestions v2 (FR-5) — history-driven, no allocation input
# ---------------------------------------------------------------------------

class BudgetSuggestionItem(BaseModel):
    subcategory_id: uuid.UUID
    subcategory_name: str
    category_id: uuid.UUID
    category_name: str
    current_cap: Decimal              # 0 when not currently budgeted
    suggested_amount: Decimal         # $5 multiple, ≤3× historical max
    locked: bool                      # locked rows are returned unchanged
    saved_balance: Decimal
    monthly_avg: Decimal              # netted trailing average (supporting stat)
    historical_max: Decimal           # max netted monthly spend in the window
    is_currently_budgeted: bool
    is_unbudgeted_candidate: bool     # unbudgeted but has real history (FR-5.8)
    rationale: str | None = None


class BudgetSuggestResponse(BaseModel):
    source: Literal["ai", "heuristic"]
    provider: str | None = None       # "groq" | "gemini" | None (heuristic)
    month: int
    year: int
    months_analyzed: int
    last_month_income: Decimal
    total_suggested: Decimal          # locked caps + suggested for the rest
    total_locked: Decimal
    suggestions: list[BudgetSuggestionItem]


class ApplySuggestionItem(BaseModel):
    subcategory_id: uuid.UUID
    amount: Decimal = Field(gt=0)


class ApplySuggestionsRequest(BaseModel):
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)
    items: list[ApplySuggestionItem]


class ApplySuggestionsResponse(BaseModel):
    applied: int


# ---------------------------------------------------------------------------
# Copy budget from another month
# ---------------------------------------------------------------------------

class CopyBudgetRequest(BaseModel):
    from_month: int = Field(ge=1, le=12)
    from_year: int = Field(ge=2000, le=2100)
    to_month: int = Field(ge=1, le=12)
    to_year: int = Field(ge=2000, le=2100)
    overwrite: bool = True  # replace existing target caps; False = only fill gaps


class CopyBudgetResponse(BaseModel):
    copied: int


# ---------------------------------------------------------------------------
# History (budget vs. actual over time)
# ---------------------------------------------------------------------------

class BudgetHistoryPoint(BaseModel):
    month: int
    year: int
    label: str                    # e.g. "Jan 2026"
    budget: Decimal               # total cap in scope that month
    spent: Decimal                # netted actual in scope that month
    surplus: Decimal              # Σ max(0, cap - spent) per subcategory
    overage: Decimal              # Σ max(0, spent - cap) per subcategory
    covered_overage: Decimal      # overage drawn from savings (settlement)
    net_overage: Decimal          # overage - covered
    saved_balance: Decimal        # scope saved-balance trajectory, end of month


class BudgetHistoryResponse(BaseModel):
    from_month: int
    from_year: int
    to_month: int
    to_year: int
    scope: Literal["all", "category", "subcategory"]
    points: list[BudgetHistoryPoint]
