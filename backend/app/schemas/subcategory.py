import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SubcategoryCreate(BaseModel):
    category_id: uuid.UUID
    name: str


class SubcategoryUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None


class SubcategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
