import uuid

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class BudgetExclusionRule(Base, TimestampMixin):
    """Auto-exclusion rule applied at import (FR-4.3).

    rule_type:
      'category'       — match_value is a category UUID string
      'subcategory'    — match_value is a subcategory UUID string
      'merchant_match' — match_value is a case-insensitive substring matched
                         against merchant_name / raw_description
    A manually set per-transaction flag always overrides rules.
    """

    __tablename__ = "budget_exclusion_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    match_value: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
