import uuid

from sqlalchemy import ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class BudgetDefault(Base, TimestampMixin):
    __tablename__ = "budget_defaults"
    __table_args__ = (
        UniqueConstraint("category_id", name="uq_budget_default_category"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False
    )
    default_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)

    category: Mapped["Category"] = relationship(  # noqa: F821
        "Category", back_populates="budget_default"
    )
