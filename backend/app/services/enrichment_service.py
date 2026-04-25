"""
Background AI enrichment service.

Runs after import confirm (for transactions not yet enriched by the frontend)
or on demand via POST /api/transactions/enrich-pending.
"""

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


def _is_amazon(raw: str) -> bool:
    upper = (raw or "").upper()
    return "AMAZON" in upper or "AMZN" in upper


async def run_background_enrichment(transactions: list[Transaction]) -> None:
    """
    Fire-and-forget: normalize merchant names + suggest categories for unenriched rows.

    Opens its own DB session — safe to call with asyncio.create_task after a request
    has flushed. On RateLimitError, commits any partial progress and returns; those
    rows stay ai_enriched=False so the user can retry via the Auto-categorize button.
    """
    if not transactions:
        return

    txn_ids = [t.id for t in transactions]
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

            if regular_txns:
                try:
                    # Step 1: normalize merchant names
                    descriptions = [t.raw_description for t in regular_txns]
                    normalized = await ai_service.normalize_merchant_names_batch(descriptions)
                    for txn, name in zip(regular_txns, normalized):
                        if name:
                            txn.merchant_name = name

                    # Step 2: suggest categories
                    txn_dicts = [
                        {
                            "index": i,
                            "raw_description": t.raw_description,
                            "merchant_name": t.merchant_name,
                            "amount": str(t.amount),
                        }
                        for i, t in enumerate(regular_txns)
                    ]
                    suggestions = await ai_service.suggest_categories(
                        txn_dicts, category_dicts, examples_text=examples_text
                    )
                    s_map = {s["index"]: s for s in suggestions if isinstance(s, dict)}

                    for i, txn in enumerate(regular_txns):
                        s = s_map.get(i, {})
                        try:
                            if s.get("category_id"):
                                txn.ai_suggested_category_id = uuid.UUID(s["category_id"])
                            if s.get("subcategory_id"):
                                txn.ai_suggested_subcategory_id = uuid.UUID(s["subcategory_id"])
                        except (ValueError, AttributeError):
                            pass
                        txn.ai_enriched = True

                except ai_service.RateLimitError:
                    logger.warning(
                        "Background enrichment rate-limited — %d rows left unenriched",
                        len(regular_txns),
                    )
                    # Commit whatever Amazon progress we made; regular rows stay ai_enriched=False
                    await db.commit()
                    return

            await db.commit()
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
