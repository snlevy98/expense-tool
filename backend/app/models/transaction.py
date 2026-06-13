import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"
    __table_args__ = (
        # Partial index over unenriched rows only — stays small as rows process.
        Index(
            "ix_transactions_ai_enriched_false",
            "ai_enriched",
            postgresql_where=text("ai_enriched = false"),
        ),
        # Covers the budget Spent aggregation (subcategory + date + exclusion).
        Index(
            "ix_transactions_subcat_date",
            "subcategory_id",
            "transaction_date",
            "budget_excluded",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True
    )
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subcategories.id"), nullable=True
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    merchant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    ai_suggested_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    ai_suggested_subcategory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_enriched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    import_source: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    external_reference: Mapped[str | None] = mapped_column(
        String(200), nullable=True, index=True
    )
    # Budget exclusion (FR-4.2): a flagged transaction is ignored by all budget
    # math. Distinct from categories.budget_excluded, which marks a whole
    # category (Income, Investments) as outside the budget system entirely.
    budget_excluded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    budget_excluded_source: Mapped[str | None] = mapped_column(
        String(10), nullable=True  # 'manual' | 'rule'
    )

    account: Mapped["Account"] = relationship(  # noqa: F821
        "Account", back_populates="transactions"
    )
    category: Mapped["Category | None"] = relationship(  # noqa: F821
        "Category", back_populates="transactions"
    )
    subcategory: Mapped["Subcategory | None"] = relationship(  # noqa: F821
        "Subcategory", back_populates="transactions"
    )
