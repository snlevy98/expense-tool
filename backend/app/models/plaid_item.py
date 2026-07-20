import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class PlaidItem(Base, TimestampMixin):
    """One Plaid Item = one institution login. An Item can expose several
    accounts (checking, savings, credit card) which map to Account rows."""

    __tablename__ = "plaid_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    item_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    # Encrypted with PLAID_TOKEN_ENCRYPTION_KEY when configured (enc: prefix).
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    institution_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    institution_name: Mapped[str] = mapped_column(
        String(200), nullable=False, default=""
    )
    # /transactions/sync cursor — null means no sync has completed yet.
    sync_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    accounts: Mapped[list["Account"]] = relationship(  # noqa: F821
        "Account", back_populates="plaid_item"
    )
