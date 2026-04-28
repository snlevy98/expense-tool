"""
Background AI enrichment service.

Runs after import confirm (for transactions not yet enriched by the frontend)
or on demand via POST /api/transactions/enrich-pending.
"""

import asyncio
import logging
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models.category import Category
from app.models.transaction import Transaction
from app.services import ai_service

logger = logging.getLogger(__name__)

# One enrichment run at a time — prevents duplicate AI calls when the
# Auto-categorize button is clicked multiple times before the task finishes.
_enrichment_lock = asyncio.Lock()


def is_enrichment_running() -> bool:
    """Return True if a background enrichment task is currently active."""
    return _enrichment_lock.locked()


def _is_amazon(raw: str) -> bool:
    upper = (raw or "").upper()
    return "AMAZON" in upper or "AMZN" in upper


async def run_background_enrichment(transactions: list[Transaction]) -> None:
    """
    Fire-and-forget: normalize merchant names + suggest categories for unenriched rows.

    Opens its own DB session — safe to call with asyncio.create_task after a request
    has flushed. Acquires a module-level lock so concurrent calls (e.g. from spam-
    clicking Auto-categorize) skip immediately rather than making duplicate AI calls.
    On RateLimitError, commits any partial progress and returns; those rows stay
    ai_enriched=False so the user can retry later.
    """
    if not transactions:
        return

    if _enrichment_lock.locked():
        logger.info(
            "Enrichment already in progress — skipping duplicate task (%d txns)",
            len(transactions),
        )
        return

    txn_ids = [t.id for t in transactions]

    async with _enrichment_lock:
        logger.info("Background enrichment starting for %d transactions", len(txn_ids))
        try:
            async with AsyncSessionLocal() as db:
                # Re-fetch with our own session (caller's session may already be closed)
                result = await db.execute(
                    select(Transaction).where(Transaction.id.in_(txn_ids))
                )
                db_txns = result.scalars().all()
                if not db_txns:
                    return

                # Load categories
                cat_result = await db.execute(
                    select(Category).options(selectinload(Category.subcategories))
                )
                categories = cat_result.scalars().all()
                category_dicts = [
                    {
                        "id": str(c.id),
                        "name": c.name,
                        "subcategories": [{"id": str(s.id), "name": s.name} for s in c.subcategories],
                    }
                    for c in categories
                ]

                examples_text = await _build_examples_text(db, category_dicts)

                amazon_txns = [t for t in db_txns if _is_amazon(t.raw_description)]
                regular_txns = [t for t in db_txns if not _is_amazon(t.raw_description)]

                # Amazon: normalize name, mark enriched — no AI category suggestion needed
                for t in amazon_txns:
                    t.merchant_name = "Amazon"
                    t.ai_enriched = True

                # Commit Amazon rows immediately so they're never lost
                if amazon_txns:
                    await db.commit()

                if regular_txns:
                    # Process chunk-by-chunk: normalize → suggest → mark enriched → commit.
                    # Each committed chunk is fully enriched; if a rate limit fires mid-run
                    # the already-committed chunks are safe and only the remaining ones
                    # stay ai_enriched=False for the next retry.
                    CHUNK = ai_service._NORMALIZE_CHUNK  # 40 — fits in one API call each step
                    enriched_count = 0

                    for chunk_start in range(0, len(regular_txns), CHUNK):
                        chunk = regular_txns[chunk_start : chunk_start + CHUNK]

                        try:
                            # Step 1: normalize merchant names for this chunk
                            descriptions = [t.raw_description for t in chunk]
                            normalized = await ai_service.normalize_merchant_names_batch(descriptions)
                            for txn, name in zip(chunk, normalized):
                                if name:
                                    txn.merchant_name = name

                            # Brief pause between normalization and categorization
                            await asyncio.sleep(1)

                            # Step 2: suggest categories for this chunk (local indices 0..N-1)
                            txn_dicts = [
                                {
                                    "index": i,
                                    "raw_description": t.raw_description,
                                    "merchant_name": t.merchant_name,
                                    "amount": str(t.amount),
                                }
                                for i, t in enumerate(chunk)
                            ]
                            suggestions = await ai_service.suggest_categories(
                                txn_dicts, category_dicts, examples_text=examples_text
                            )
                            s_map = {s["index"]: s for s in suggestions if isinstance(s, dict)}

                            for i, txn in enumerate(chunk):
                                s = s_map.get(i, {})
                                try:
                                    if s.get("category_id"):
                                        txn.ai_suggested_category_id = uuid.UUID(s["category_id"])
                                    if s.get("subcategory_id"):
                                        txn.ai_suggested_subcategory_id = uuid.UUID(s["subcategory_id"])
                                except (ValueError, AttributeError):
                                    pass
                                txn.ai_enriched = True

                            # Commit this chunk — fully enriched rows are now persisted
                            await db.commit()
                            enriched_count += len(chunk)
                            logger.info(
                                "Enrichment chunk committed: %d/%d regular txns done",
                                enriched_count,
                                len(regular_txns),
                            )

                            # Pause between chunks to ease rate-limit pressure
                            if chunk_start + CHUNK < len(regular_txns):
                                await asyncio.sleep(2)

                        except ai_service.RateLimitError:
                            logger.warning(
                                "Background enrichment rate-limited after %d/%d regular txns "
                                "— remaining %d rows stay unenriched for next retry",
                                enriched_count,
                                len(regular_txns),
                                len(regular_txns) - enriched_count,
                            )
                            return

                logger.info(
                    "Background enrichment complete: %d regular, %d Amazon",
                    len(regular_txns),
                    len(amazon_txns),
                )

        except Exception:
            logger.exception("Background enrichment failed")


async def _build_examples_text(db, category_dicts: list[dict]) -> str:
    """
    Build the few-shot categorization examples string from recent user-confirmed
    transactions. Prioritises cases where the user corrected the AI suggestion.
    """
    try:
        ex_result = await db.execute(
            select(
                Transaction.merchant_name,
                Transaction.category_id,
                Transaction.subcategory_id,
                Transaction.ai_suggested_category_id,
                Transaction.updated_at,
            )
            .where(Transaction.category_id.isnot(None))
            .where(Transaction.merchant_name.isnot(None))
            .order_by(Transaction.updated_at.desc())
            .limit(300)
        )
        ex_rows = ex_result.all()

        # User corrections first
        ex_rows = sorted(
            ex_rows,
            key=lambda r: 0 if (
                r.ai_suggested_category_id and r.category_id != r.ai_suggested_category_id
            ) else 1,
        )

        cat_name_map = {c["id"]: c["name"] for c in category_dicts}
        subcat_name_map = {
            s["id"]: s["name"]
            for c in category_dicts
            for s in c["subcategories"]
        }
        seen: set[str] = set()
        per_cat: dict[str, int] = defaultdict(int)
        lines: list[str] = []

        for row in ex_rows:
            key = row.merchant_name.strip().lower()
            cat_key = str(row.category_id)
            if key in seen or per_cat[cat_key] >= 3:
                continue
            cat_name = cat_name_map.get(cat_key, "")
            if not cat_name:
                continue
            sub_name = subcat_name_map.get(str(row.subcategory_id or ""), "")
            label = f"{cat_name} > {sub_name}" if sub_name else cat_name
            lines.append(f'  - "{row.merchant_name}" → {label}')
            seen.add(key)
            per_cat[cat_key] += 1
            if len(lines) >= 25:
                break

        return "\n".join(lines)

    except Exception:
        logger.exception("Failed to build examples text for background enrichment")
        return ""
