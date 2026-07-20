import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Account(Base, TimestampMixin):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    institution: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sign_convention: Mapped[str] = mapped_column(
        String(20), nullable=False, default="positive_expense"
    )
    # Set when this account is fed by a Plaid Item (bank sync) instead of CSV.
    plaid_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plaid_items.id"), nullable=True
    )
    plaid_account_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True
    )

    transactions: Mapped[list["Transaction"]] = relationship(  # noqa: F821
        "Transaction", back_populates="account"
    )
    plaid_item: Mapped["PlaidItem | None"] = relationship(  # noqa: F821
        "PlaidItem", back_populates="accounts"
    )
