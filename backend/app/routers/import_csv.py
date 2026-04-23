"""
CSV import router: /preview and /confirm endpoints.
"""

import asyncio
import logging
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.middleware.auth import require_auth
from app.models.category import Category
from app.models.transaction import Transaction
from app.schemas.transaction import (
    ImportConfirmRequest,
    ImportPreviewItem,
    ImportPreviewResponse,
)
from app.services import ai_service
from app.services.csv_service import parse_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/import", tags=["import"])


@router.post("/preview", response_model=ImportPreviewResponse)
async def preview_import(
    file: UploadFile,
    account_id: uuid.UUID = Form(...),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> ImportPreviewResponse:
    """
    Parse an uploaded CSV/Excel file, call AI for category suggestions and
    merchant normalization, deduplicate against existing transactions by
    external reference (or date+amount+description), and return a preview.
    """
    allowed_extensions = (".csv", ".xlsx", ".xls")
    fname = (file.filename or "").lower()
    if not any(fname.endswith(ext) for ext in allowed_extensions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV and Excel (.xlsx, .xls) files are accepted.",
        )

    contents = await file.read()
    try:
        parsed_rows = parse_file(contents, filename=file.filename or "upload.csv")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if not parsed_rows:
        return ImportPreviewResponse(transactions=[], duplicates_skipped=0)

    # ---- Duplicate detection ----
    # For rows that have an external_reference, check that field first (fast, exact).
    # Fall back to (account_id, date, amount, raw_description) for rows without one.
    refs_in_file = [r["external_reference"] for r in parsed_rows if r.get("external_reference")]
    existing_refs: set[str] = set()
    if refs_in_file:
        ref_result = await db.execute(
            select(Transaction.external_reference).where(
                and_(
                    Transaction.account_id == account_id,
                    Transaction.external_reference.in_(refs_in_file),
                )
            )
        )
        existing_refs = {row[0] for row in ref_result.fetchall() if row[0]}

    # For rows without a reference, use the legacy fingerprint check
    existing_fingerprints: set[tuple] = set()
    no_ref_rows = [r for r in parsed_rows if not r.get("external_reference")]
    for row in no_ref_rows:
        fp_result = await db.execute(
            select(Transaction.id).where(
                and_(
                    Transaction.account_id == account_id,
                    Transaction.transaction_date == row["transaction_date"],
                    Transaction.amount == row["amount"],
                    Transaction.raw_description == row["raw_description"],
                )
            )
        )
        if fp_result.scalar_one_or_none():
            existing_fingerprints.add(
                (str(row["transaction_date"]), str(row["amount"]), row["raw_description"])
            )

    def _is_duplicate(row: dict) -> bool:
        ref = row.get("external_reference")
        if ref:
            return ref in existing_refs
        return (
            str(row["transaction_date"]),
            str(row["amount"]),
            row["raw_description"],
        ) in existing_fingerprints

    # Filter out duplicates entirely; count them for the UI
    unique_rows = [r for r in parsed_rows if not _is_duplicate(r)]
    duplicates_skipped = len(parsed_rows) - len(unique_rows)

    if not unique_rows:
        return ImportPreviewResponse(transactions=[], duplicates_skipped=duplicates_skipped)

    # ---- Normalize merchant names via AI (batch) ----
    try:
        descriptions = [r["raw_description"] for r in unique_rows]
        normalized_names = await ai_service.normalize_merchant_names_batch(descriptions)
        for row, name in zip(unique_rows, normalized_names):
            if name:
                row["merchant_name"] = name
    except Exception as exc:
        logger.warning("Merchant normalization failed, using raw descriptions: %s", exc)

    # ---- Load active categories for AI suggestions ----
    cat_result = await db.execute(
        select(Category)
        .options(selectinload(Category.subcategories))
    )
    categories = cat_result.scalars().all()
    category_dicts = [
        {
            "id": str(c.id),
            "name": c.name,
            "subcategories": [
                {"id": str(s.id), "name": s.name}
                for s in c.subcategories
            ],
        }
        for c in categories
    ]
    logger.info(
        "AI category suggestion: %d categories loaded, %d transactions to suggest for",
        len(category_dicts),
        len(unique_rows),
    )

    suggestions = await ai_service.suggest_categories(unique_rows, category_dicts)
    logger.info(
        "AI category suggestion: received %d suggestions (expected %d)",
        len(suggestions),
        len(unique_rows),
    )
    suggestion_map: dict[int, dict] = {s["index"]: s for s in suggestions if isinstance(s, dict)}
    logger.info("AI category suggestion: suggestion_map has %d entries", len(suggestion_map))

    # ---- Build preview items ----
    preview_items: list[ImportPreviewItem] = []
    for idx, row in enumerate(unique_rows):
        suggestion = suggestion_map.get(idx, {})

        cat_id: uuid.UUID | None = None
        subcat_id: uuid.UUID | None = None
        try:
            if suggestion.get("category_id"):
                cat_id = uuid.UUID(suggestion["category_id"])
            if suggestion.get("subcategory_id"):
                subcat_id = uuid.UUID(suggestion["subcategory_id"])
        except (ValueError, AttributeError):
            pass

        preview_items.append(
            ImportPreviewItem(
                index=idx,
                raw_description=row["raw_description"],
                merchant_name=row["merchant_name"],
                amount=Decimal(str(row["amount"])),
                transaction_date=row["transaction_date"],
                import_source=row["import_source"],
                external_reference=row.get("external_reference"),
                ai_suggested_category_id=cat_id,
                ai_suggested_subcategory_id=subcat_id,
            )
        )

    return ImportPreviewResponse(transactions=preview_items, duplicates_skipped=duplicates_skipped)


@router.post("/confirm", status_code=status.HTTP_201_CREATED)
async def confirm_import(
    body: ImportConfirmRequest,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    """
    Save confirmed transactions to the database.
    Assigns a shared import_batch_id to all rows in the batch.
    Triggers async recurring detection after saving.
    """
    if not body.transactions:
        return {"imported": 0, "import_batch_id": None}

    import_batch_id = uuid.uuid4()
    saved_transactions: list[Transaction] = []

    for item in body.transactions:
        txn = Transaction(
            id=uuid.uuid4(),
            account_id=item.account_id,
            category_id=item.category_id,
            subcategory_id=item.subcategory_id,
            transaction_date=item.transaction_date,
            raw_description=item.raw_description,
            merchant_name=item.merchant_name,
            amount=item.amount,
            ai_suggested_category_id=item.ai_suggested_category_id,
            ai_suggested_subcategory_id=item.ai_suggested_subcategory_id,
            is_recurring=False,
            import_source=item.import_source,
            import_batch_id=import_batch_id,
            external_reference=item.external_reference,
        )
        db.add(txn)
        saved_transactions.append(txn)

    await db.flush()

    # Trigger recurring detection asynchronously (don't block the response)
    asyncio.create_task(_run_recurring_detection(saved_transactions, db))

    return {"imported": len(saved_transactions), "import_batch_id": str(import_batch_id)}


async def _run_recurring_detection(
    new_transactions: list[Transaction], db: AsyncSession
) -> None:
    """Background task: detect recurring patterns in the newly imported batch."""
    try:
        txn_dicts = [
            {
                "id": str(t.id),
                "merchant_name": t.merchant_name,
                "amount": float(t.amount),
                "transaction_date": t.transaction_date,
            }
            for t in new_transactions
        ]
        recurring_ids = await ai_service.detect_recurring(txn_dicts)
        if recurring_ids:
            recurring_uuid_set = {uuid.UUID(rid) for rid in recurring_ids if rid}
            for txn in new_transactions:
                if txn.id in recurring_uuid_set:
                    txn.is_recurring = True
            await db.commit()
    except Exception as exc:
        logger.warning("Background recurring detection failed: %s", exc)
