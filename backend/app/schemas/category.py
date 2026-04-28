import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.subcategory import SubcategoryOut


class SubcategoryReorderRequest(BaseModel):
    subcategory_ids: list[uuid.UUID]


class CategoryCreate(BaseModel):
    name: str
    color: str = "#4A90E2"


class CategoryUpdate(BaseModel):
    name: str | None = None
    color: str | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str
    is_active: bool
    budget_excluded: bool = False
    subcategories: list[SubcategoryOut] = []
    created_at: datetime
    updated_at: datetime
