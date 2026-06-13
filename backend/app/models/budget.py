import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Budget(Base, TimestampMixin):
    __tablename__ = "budgets"
    # Uniqueness is enforced by two partial indexes (PostgreSQL treats NULLs as
    # distinct, so a single unique constraint can't express both shapes).
    # Envelope budgeting (FR-1.3) only reads rows WHERE subcategory_id IS NOT NULL;
    # legacy category-level rows are retained for historical reports only.
    # Row presence = budgeted (FR-1.1): amount must be > 0 (ck_budgets_amount_positive).
    __table_args__ = (
        Index(
            "uq_budget_cat_month_year_no_sub",
            "category_id",
            "month",
            "year",
            unique=True,
            postgresql_where=text("subcategory_id IS NULL"),
        ),
        Index(
            "uq_budget_sub_month_year",
            "subcategory_id",
            "month",
            "year",
            unique=True,
            postgresql_where=text("subcategory_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False
    )
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "subcategories.id", ondelete="CASCADE", name="fk_budgets_subcategory_id"
        ),
        nullable=True,
    )
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    category: Mapped["Category"] = relationship(  # noqa: F821
        "Category", back_populates="budgets"
    )
    subcategory: Mapped["Subcategory | None"] = relationship(  # noqa: F821
        "Subcategory"
    )
