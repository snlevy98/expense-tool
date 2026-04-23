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


class BudgetUpsert(BaseModel):
    category_id: uuid.UUID
    subcategory_id: uuid.UUID | None = None
    month: int
    year: int
    amount: Decimal


class BudgetDefaultUpdate(BaseModel):
    default_amount: Decimal
