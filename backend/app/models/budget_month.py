import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class BudgetMonth(Base, TimestampMixin):
    """Lifecycle/settlement registry for budget months (FR-2.1–2.3).

    Row presence = the month has been materialized (caps copied forward).
    settled_at = month-close settlement has been claimed; claiming is done via
    UPDATE ... WHERE settled_at IS NULL RETURNING so settlement runs exactly
    once even under concurrent requests (NFR-2).
    """

    __tablename__ = "budget_months"
    __table_args__ = (
        UniqueConstraint("month", "year", name="uq_budget_months_month_year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
