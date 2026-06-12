import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class SavedBalance(Base, TimestampMixin):
    """Per-subcategory spendable rollover pool (FR-3.1).

    Created when a subcategory is first budgeted; deleted when it is
    unbudgeted (FR-1.5 — re-budgeting starts fresh at $0).
    """

    __tablename__ = "saved_balances"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_saved_balances_non_negative"),
    )

    subcategory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subcategories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    balance: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    subcategory: Mapped["Subcategory"] = relationship("Subcategory")  # noqa: F821


class SavedBalanceEvent(Base, TimestampMixin):
    """Audit trail for every saved-balance mutation (NFR-5).

    Retained even after the balance row is deleted. month/year are set for
    settlement and recompute events. The partial unique index
    uq_sbe_settlement (subcategory_id, year, month) WHERE reason IN
    ('month_close_surplus', 'month_close_coverage') is the DB-level backstop
    that settlement applies at most once per (subcategory, month).
    """

    __tablename__ = "saved_balance_events"

    REASON_SURPLUS = "month_close_surplus"
    REASON_COVERAGE = "month_close_coverage"
    REASON_MANUAL_RESET = "manual_reset"
    REASON_MANUAL_ADJUST = "manual_adjust"
    REASON_RECOMPUTE = "recompute"
    REASON_UNBUDGETED = "unbudgeted_deleted"

    SETTLEMENT_REASONS = (REASON_SURPLUS, REASON_COVERAGE)
    BALANCE_AFFECTING_REASONS = (REASON_SURPLUS, REASON_COVERAGE, REASON_RECOMPUTE)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subcategory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subcategories.id"), nullable=False, index=True
    )
    delta: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(String(30), nullable=False)
    month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
