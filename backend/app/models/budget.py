import uuid

from sqlalchemy import ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Budget(Base, TimestampMixin):
    __tablename__ = "budgets"
    # Uniqueness is enforced by two partial indexes created in the migration:
    #   uq_budget_cat_month_year_no_sub  ON (category_id, month, year) WHERE subcategory_id IS NULL
    #   uq_budget_sub_month_year         ON (subcategory_id, month, year) WHERE subcategory_id IS NOT NULL

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False
    )
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subcategories.id"), nullable=True
    )
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)

    category: Mapped["Category"] = relationship(  # noqa: F821
        "Category", back_populates="budgets"
    )
    subcategory: Mapped["Subcategory | None"] = relationship(  # noqa: F821
        "Subcategory"
    )
