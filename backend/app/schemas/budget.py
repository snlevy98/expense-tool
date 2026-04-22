import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class BudgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    month: int
    year: int
    amount: Decimal
    created_at: datetime
    updated_at: datetime

    category_name: str | None = None
    category_color: str | None = None


class BudgetUpsert(BaseModel):
    category_id: uuid.UUID
    month: int
    year: int
    amount: Decimal


class BudgetDefaultUpdate(BaseModel):
    default_amount: Decimal
