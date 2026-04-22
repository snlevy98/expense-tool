"""
APScheduler nightly job: detect recurring transactions from the last 90 days
and update the is_recurring flag in the database.
"""

import logging
import uuid
from datetime import date, timedelta

from sqlalchemy import and_, select

from app.db.session import AsyncSessionLocal
from app.models.transaction import Transaction
from app.services.ai_service import detect_recurring

logger = logging.getLogger(__name__)


async def run_recurring_detection() -> None:
    """
    Nightly job that scans all transactions from the last 90 days,
    identifies recurring ones via AI + heuristics, and updates the DB.
    """
    cutoff = date.today() - timedelta(days=90)
    logger.info("Running nightly recurring detection (cutoff: %s)", cutoff)

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Transaction).where(
                    and_(
                        Transaction.transaction_date >= cutoff,
                        Transaction.amount > 0,
                    )
                )
            )
            transactions = result.scalars().all()

            if not transactions:
                logger.info("No transactions found for recurring detection.")
                return

            txn_dicts = [
                {
                    "id": str(t.id),
                    "merchant_name": t.merchant_name,
                    "amount": float(t.amount),
                    "transaction_date": t.transaction_date,
                }
                for t in transactions
            ]

            recurring_ids_str = await detect_recurring(txn_dicts)
            recurring_uuids: set[uuid.UUID] = set()
            for rid in recurring_ids_str:
                try:
                    recurring_uuids.add(uuid.UUID(rid))
                except (ValueError, AttributeError):
                    pass

            updated = 0
            for txn in transactions:
                should_be_recurring = txn.id in recurring_uuids
                if txn.is_recurring != should_be_recurring:
                    txn.is_recurring = should_be_recurring
                    updated += 1

            await db.commit()
            logger.info(
                "Recurring detection complete. Checked %d transactions, updated %d.",
                len(transactions),
                updated,
            )

        except Exception as exc:
            await db.rollback()
            logger.error("Recurring detection job failed: %s", exc, exc_info=True)
