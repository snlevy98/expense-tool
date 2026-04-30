import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SubcategoryBudgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subcategory_id: uuid.UUID
    subcategory_name: str
    category_id: uuid.UUID
    month: int
    year: int
    amount: Decimal


class CategoryBudgetOut(BaseModel):
    category_id: uuid.UUID
    category_name: str
    category_color: str
    has_subcategories: bool
    # Sum of subcategory amounts (has_subcategories=True) or direct amount (False)
    total_amount: Decimal
    # Only set when has_subcategories=False (the actual budget row id)
    budget_id: uuid.UUID | None = None
    month: int
    year: int
    subcategory_budgets: list[SubcategoryBudgetOut] = []


class BudgetListResponse(BaseModel):
    """Full budget list response including pool summary."""
    budgets: list[CategoryBudgetOut]
    pool_pct: Decimal
    pool_amount: Decimal       # last_month_income × pool_pct
    last_month_income: Decimal
    allocated: Decimal         # sum of all category budget amounts this month
    leftover: Decimal          # pool_amount − allocated


class BudgetSettingsOut(BaseModel):
    pool_pct: Decimal


class BudgetSettingsUpdate(BaseModel):
    pool_pct: Decimal  # expected range 0.01–1.00


class BudgetUpsert(BaseModel):
    category_id: uuid.UUID
    subcategory_id: uuid.UUID | None = None
    month: int
    year: int
    amount: Decimal


class BudgetDefaultUpdate(BaseModel):
    default_amount: Decimal


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
