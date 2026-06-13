"""
CSV import router: /preview, /enrich, and /confirm endpoints.

/preview  — parses + deduplicates only; returns immediately (no AI)
/enrich   — AI merchant normalization + category suggestion for a batch;
             returns 503 on rate limit so the client can retry with backoff
/confirm  — saves confirmed transactions to the database
"""

import asyncio
import logging
import uuid
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.middleware.auth import require_auth
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.schemas.transaction import (
    EnrichRequest,
    EnrichResponse,
    EnrichResult,
    ImportConfirmRequest,
    ImportPreviewItem,
    ImportPreviewResponse,
    VenmoUnmatchedItem,
)
from app.services import ai_service, budget_lifecycle, budget_service
from app.services.csv_service import parse_file
from app.services.enrichment_service import run_background_enrichment

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
    Parse an uploaded CSV/Excel file, deduplicate against existing transactions,
    and return a preview immediately. AI enrichment happens via POST /enrich.
    """
    allowed_extensions = (".csv", ".xlsx", ".xls")
    fname = (file.filename or "").lower()
    if not any(fname.endswith(ext) for ext in allowed_extensions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV and Excel (.xlsx, .xls) files are accepted.",
        )

    account_result = await db.execute(select(Account).where(Account.id == account_id))
    account = account_result.scalar_one_or_none()
    account_type = account.type if account else None
    sign_convention = account.sign_convention if account else "positive_expense"

    contents = await file.read()
    try:
        parsed_rows = parse_file(
            contents,
            filename=file.filename or "upload.csv",
            account_type=account_type,
            sign_convention=sign_convention,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if not parsed_rows:
        return ImportPreviewResponse(transactions=[], duplicates_skipped=0)

    # ---- Venmo bank-transfer matching ----
    # Rows where funding source / destination is a real bank account (not Venmo balance)
    # correspond to a charge or deposit that also appears on the linked bank statement.
    # Try to find the existing bank transaction (amount exact, date ±3 days, description
    # contains "venmo") and record its ID so /confirm can update it instead of inserting.
    venmo_unmatched: list[VenmoUnmatchedItem] = []
    for row in parsed_rows:
        if not row.get("is_venmo_bank_transfer"):
            continue
        date_val = row["transaction_date"]
        amount_val = row["amount"]
        match_result = await db.execute(
            select(Transaction).where(
                and_(
                    Transaction.amount == amount_val,
                    Transaction.transaction_date >= date_val - timedelta(days=3),
                    Transaction.transaction_date <= date_val + timedelta(days=3),
                    Transaction.raw_description.ilike("%venmo%"),
                )
            ).limit(1)
        )
        matched_txn = match_result.scalar_one_or_none()
        if matched_txn:
            row["matched_transaction_id"] = str(matched_txn.id)
        else:
            venmo_unmatched.append(
                VenmoUnmatchedItem(
                    transaction_date=date_val,
                    amount=amount_val,
                    merchant_name=row.get("merchant_name", ""),
                    raw_description=row.get("raw_description", ""),
                )
            )

    # Drop unmatched bank-transfer rows — they have no place to land
    parsed_rows = [
        r for r in parsed_rows
        if not r.get("is_venmo_bank_transfer") or r.get("matched_transaction_id")
    ]

    if not parsed_rows and not venmo_unmatched:
        return ImportPreviewResponse(transactions=[], duplicates_skipped=0)

    # ---- Duplicate detection ----

    # --- External-reference deduplication (for banks that export a unique ID) ---
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

    # --- Fingerprint deduplication (date + amount + description) ---
    # Count how many times each unique fingerprint appears in this import file.
    # Then query the DB for how many existing transactions match each fingerprint.
    # We consume one DB match per import row — so if two identical rows are in
    # the file but only one is in the DB, the first is a duplicate and the second
    # is imported as new.
    no_ref_rows = [r for r in parsed_rows if not r.get("external_reference")]
    import_fp_counts: Counter = Counter()
    for row in no_ref_rows:
        # Use native types (date, Decimal) as keys — both are hashable and are what
        # asyncpg expects in parameterised queries against Date/Numeric columns.
        fp = (row["transaction_date"], row["amount"], row["raw_description"])
        import_fp_counts[fp] += 1

    fp_db_counts: dict[tuple, int] = {}
    for fp in import_fp_counts:
        date_val, amount_val, desc_val = fp
        count_result = await db.execute(
            select(func.count()).select_from(Transaction).where(
                and_(
                    Transaction.account_id == account_id,
                    Transaction.transaction_date == date_val,   # date object
                    Transaction.amount == amount_val,           # Decimal object
                    Transaction.raw_description == desc_val,
                )
            )
        )
        fp_db_counts[fp] = count_result.scalar_one()

    # Track how many DB matches we've consumed per fingerprint as we scan rows
    fp_consumed: Counter = Counter()

    def _is_duplicate(row: dict) -> bool:
        ref = row.get("external_reference")
        if ref:
            return ref in existing_refs
        fp = (row["transaction_date"], row["amount"], row["raw_description"])
        db_count = fp_db_counts.get(fp, 0)
        if db_count == 0:
            return False
        # Consume one DB match — subsequent identical rows in the same file are new
        if fp_consumed[fp] < db_count:
            fp_consumed[fp] += 1
            return True
        return False

    unique_rows = [r for r in parsed_rows if not _is_duplicate(r)]
    duplicates_skipped = len(parsed_rows) - len(unique_rows)

    if not unique_rows:
        return ImportPreviewResponse(
            transactions=[],
            duplicates_skipped=duplicates_skipped,
            venmo_unmatched=venmo_unmatched,
        )

    # Build preview items with raw data — AI enrichment happens client-side via /enrich
    preview_items = [
        ImportPreviewItem(
            index=idx,
            raw_description=row["raw_description"],
            merchant_name=row.get("merchant_name") or row["raw_description"],
            amount=Decimal(str(row["amount"])),
            transaction_date=row["transaction_date"],
            import_source=row["import_source"],
            external_reference=row.get("external_reference"),
            ai_suggested_category_id=None,
            ai_suggested_subcategory_id=None,
            matched_transaction_id=uuid.UUID(row["matched_transaction_id"])
                if row.get("matched_transaction_id") else None,
        )
        for idx, row in enumerate(unique_rows)
    ]

    return ImportPreviewResponse(
        transactions=preview_items,
        duplicates_skipped=duplicates_skipped,
        venmo_unmatched=venmo_unmatched,
    )


@router.post("/enrich", response_model=EnrichResponse)
async def enrich_batch(
    body: EnrichRequest,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> EnrichResponse:
    """
    AI-enrich a batch of transactions: normalize merchant names and suggest categories.
    Returns 503 when Gemini is rate-limited so the client can retry with backoff.
    """
    if not body.transactions:
        return EnrichResponse(results=[])

    # ---- Load categories for suggestion ----
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

    # ---- Build few-shot examples from past categorizations ----
    # Prioritise transactions where the user corrected the AI suggestion,
    # then manually categorized, then accepted AI suggestions.
    # Deduplicate by merchant name, cap at 3 per category, 25 total.
    examples_text = ""
    try:
        ex_result = await db.execute(
            select(
                Transaction.merchant_name,
                Transaction.category_id,
                Transaction.subcategory_id,
                Transaction.ai_suggested_category_id,
            )
            .where(Transaction.category_id.isnot(None))
            .where(Transaction.merchant_name.isnot(None))
            .order_by(Transaction.updated_at.desc())
            .limit(300)
        )
        ex_rows = ex_result.all()

        # Sort: user corrections first (changed from AI suggestion), then the rest
        ex_rows = sorted(
            ex_rows,
            key=lambda r: 0 if (
                r.ai_suggested_category_id and
                r.category_id != r.ai_suggested_category_id
            ) else 1,
        )

        # Build name lookup maps from already-loaded category_dicts
        cat_name_map = {c["id"]: c["name"] for c in category_dicts}
        subcat_name_map = {
            s["id"]: s["name"]
            for c in category_dicts
            for s in c["subcategories"]
        }

        seen_merchants: set[str] = set()
        per_category: dict[str, int] = defaultdict(int)
        lines: list[str] = []

        for row in ex_rows:
            merchant_key = row.merchant_name.strip().lower()
            cat_key = str(row.category_id)
            if merchant_key in seen_merchants or per_category[cat_key] >= 3:
                continue
            cat_name = cat_name_map.get(cat_key, "")
            if not cat_name:
                continue
            sub_name = subcat_name_map.get(str(row.subcategory_id or ""), "")
            label = f"{cat_name} > {sub_name}" if sub_name else cat_name
            lines.append(f'  - "{row.merchant_name}" → {label}')
            seen_merchants.add(merchant_key)
            per_category[cat_key] += 1
            if len(lines) >= 25:
                break

        examples_text = "\n".join(lines)
    except Exception:
        logger.exception("Failed to load categorization examples — proceeding without them")

    def _is_amazon(raw: str) -> bool:
        upper = (raw or "").upper()
        return "AMAZON" in upper or "AMZN" in upper

    all_txns = [
        {
            "index": item.index,
            "raw_description": item.raw_description,
            "merchant_name": item.merchant_name,
            "amount": str(item.amount),
        }
        for item in body.transactions
    ]

    # Split Amazon vs non-Amazon — Amazon transactions skip AI entirely
    amazon_txns = [t for t in all_txns if _is_amazon(t["raw_description"])]
    regular_txns = [t for t in all_txns if not _is_amazon(t["raw_description"])]

    for t in amazon_txns:
        t["merchant_name"] = "Amazon"

    txns = all_txns  # keep original ordering for result assembly

    is_venmo = (body.account_type or "").lower() == "venmo"

    try:
        suggestions: list[dict] = []
        if regular_txns:
            if not is_venmo:
                # Normalize merchant names — skipped for Venmo since merchant_name
                # is already set to the other person's name during CSV parsing.
                descriptions = [t["raw_description"] for t in regular_txns]
                normalized = await ai_service.normalize_merchant_names_batch(descriptions)
                for txn, name in zip(regular_txns, normalized):
                    if name:
                        txn["merchant_name"] = name

            # Suggest categories using merchant name + raw_description + past examples
            suggestions = await ai_service.suggest_categories(
                regular_txns, category_dicts, examples_text=examples_text
            )

    except ai_service.RateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable — please retry.",
        ) from exc

    suggestion_map: dict[int, dict] = {
        s["index"]: s for s in suggestions if isinstance(s, dict)
    }

    results: list[EnrichResult] = []
    for txn in txns:
        idx = txn["index"]
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
        results.append(
            EnrichResult(
                index=idx,
                merchant_name=txn["merchant_name"],
                ai_suggested_category_id=cat_id,
                ai_suggested_subcategory_id=subcat_id,
            )
        )

    return EnrichResponse(results=results)


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
        if item.matched_transaction_id:
            # Venmo→bank match: enrich the existing bank transaction in-place.
            # Preserves the original account, amount, date, and any manual categorization.
            match_result = await db.execute(
                select(Transaction).where(Transaction.id == item.matched_transaction_id)
            )
            existing = match_result.scalar_one_or_none()
            if existing:
                existing.merchant_name = item.merchant_name
                existing.raw_description = item.raw_description
                existing.ai_suggested_category_id = item.ai_suggested_category_id
                existing.ai_suggested_subcategory_id = item.ai_suggested_subcategory_id
                existing.ai_enriched = item.ai_enriched
                existing.import_batch_id = import_batch_id
                saved_transactions.append(existing)
        else:
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
                ai_enriched=item.ai_enriched,
                is_recurring=False,
                import_source=item.import_source,
                import_batch_id=import_batch_id,
                external_reference=item.external_reference,
            )
            db.add(txn)
            saved_transactions.append(txn)

    await db.flush()

    # Late-arriving transactions dated in already-settled months re-settle
    # those months (FR-2.4 / FR-4.4). Venmo match-updates don't change
    # date/amount/subcategory, so only categorized inserts can have an effect.
    await budget_lifecycle.reconcile_transaction_change(
        db, [budget_lifecycle.budget_snapshot(t) for t in saved_transactions]
    )

    # Auto-exclude per the exclusion rules (FR-4.3); re-settles affected months.
    await budget_service.apply_exclusion_rules(db, saved_transactions)

    asyncio.create_task(_run_recurring_detection(saved_transactions, db))

    # Enrich any transactions the frontend didn't finish processing before confirm
    unenriched = [t for t in saved_transactions if not t.ai_enriched]
    if unenriched:
        asyncio.create_task(run_background_enrichment(unenriched))

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
