import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AccountCreate(BaseModel):
    name: str
    type: str
    institution: str
    sign_convention: str = "positive_expense"


class AccountUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    institution: str | None = None
    is_active: bool | None = None
    sign_convention: str | None = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    institution: str
    is_active: bool
    sign_convention: str
    created_at: datetime
    updated_at: datetime
