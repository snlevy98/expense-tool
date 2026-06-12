"""
Amazon Categorizer router.

GET  /amazon/uncategorized-count   — count of uncategorized Amazon transactions
POST /amazon/analyze               — parse order-history CSVs, match to DB
                                     transactions, AI-suggest categories for items
POST /amazon/apply-groceries       — bulk update matched grocery transactions
POST /amazon/itemize               — create individual item transactions, remove parent
"""

import io
import logging
import re
import uuid
from collections import Counter
from datetime import date as date_type, timedelta
from decimal import Decimal, InvalidOperation

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.middleware.auth import require_auth
from app.models.category import Category
from app.models.transaction import Transaction
from app.services import ai_service, budget_lifecycle

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/amazon", tags=["amazon"])

AMAZON_MERCHANT = "Amazon"
WHOLE_FOODS_NAME = "Whole Foods Market - Uptown Dallas"
WF_TO_VALUE = "Whole Foods Market - Uptown Dallas"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_payment_amount(payments_str: str) -> Decimal | None:
    """Extract the largest dollar amount from a payments string like
    'AmEx ending in 1003: 2026-04-21: $20.56; '"""
    if not payments_str or str(payments_str).lower() in ("nan", "none", ""):
        return None
    matches = re.findall(r"\$(\d+\.?\d*)", str(payments_str))
    if not matches:
        return None
    try:
        return max(Decimal(m) for m in matches)
    except (InvalidOperation, ValueError):
        return None


def _parse_price(price_str: str) -> Decimal:
    """Parse '$18.99' or '18.99' → Decimal('18.99')"""
    try:
        return Decimal(str(price_str).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _parse_quantity(val) -> int:
    """Safely parse a quantity value; any non-positive or non-numeric → 1."""
    try:
        n = int(float(str(val).strip()))
        return n if n > 0 else 1
    except (ValueError, TypeError, AttributeError):
        return 1


async def _find_amazon_txn(
    db: AsyncSession,
    amount: Decimal,
    order_date: str,
    date_window: int = 3,
) -> Transaction | None:
    """Find an uncategorized Amazon transaction matching amount within ±date_window days."""
    try:
        od = date_type.fromisoformat(str(order_date).strip()[:10])
    except (ValueError, TypeError):
        od = None

    conditions = [
        Transaction.merchant_name == AMAZON_MERCHANT,
        Transaction.amount == amount,
        Transaction.category_id.is_(None),
    ]
    if od:
        conditions += [
            Transaction.transaction_date >= od - timedelta(days=date_window),
            Transaction.transaction_date <= od + timedelta(days=date_window),
        ]

    result = await db.execute(
        select(Transaction)
        .where(and_(*conditions))
        .order_by(Transaction.transaction_date.asc())
        .limit(1)
    )
    return result.scalars().first()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class AnalyzeOrderItem(BaseModel):
    description: str
    price: Decimal
    quantity: int
    asin: str
    suggested_category_id: uuid.UUID | None = None
    suggested_subcategory_id: uuid.UUID | None = None


class GroceryMatch(BaseModel):
    order_id: str
    order_date: str
    transaction_id: uuid.UUID | None
    transaction_date: str | None
    amount: Decimal
    items_summary: str


class RegularOrder(BaseModel):
    order_id: str
    order_date: str
    transaction_id: uuid.UUID | None
    transaction_date: str | None
    amount: Decimal
    items: list[AnalyzeOrderItem]


class UnmatchedOrder(BaseModel):
    order_id: str
    order_date: str
    to: str
    amount: Decimal | None
    reason: str


class AmazonAnalysisResponse(BaseModel):
    grocery_matches: list[GroceryMatch]
    regular_orders: list[RegularOrder]
    unmatched: list[UnmatchedOrder]


class ApplyGroceryItem(BaseModel):
    transaction_id: uuid.UUID
    order_id: str
    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None


class ApplyGroceriesRequest(BaseModel):
    matches: list[ApplyGroceryItem]


class ItemizeItemIn(BaseModel):
    description: str
    price: Decimal
    quantity: int = 1
    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None


class ItemizeOrderIn(BaseModel):
    parent_transaction_id: uuid.UUID
    order_id: str
    items: list[ItemizeItemIn]


class ItemizeRequest(BaseModel):
    orders: list[ItemizeOrderIn]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/uncategorized-count")
async def amazon_uncategorized_count(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    result = await db.execute(
        select(func.count()).select_from(Transaction).where(
            and_(
                Transaction.merchant_name == AMAZON_MERCHANT,
                Transaction.category_id.is_(None),
            )
        )
    )
    return {"count": result.scalar_one()}


@router.post("/analyze", response_model=AmazonAnalysisResponse)
async def analyze_orders(
    orders_file: UploadFile,
    items_file: UploadFile,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> AmazonAnalysisResponse:
    """
    Parse both Amazon order-history CSVs, match orders to DB Amazon transactions,
    and AI-suggest categories for non-grocery item descriptions.
    """
    # --- Parse CSVs ---
    try:
        orders_df = pd.read_csv(io.BytesIO(await orders_file.read()))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse orders file: {exc}")
    try:
        items_df = pd.read_csv(io.BytesIO(await items_file.read()))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse items file: {exc}")

    # Normalise column names (strip whitespace, lowercase, drop BOM)
    orders_df.columns = [c.strip().lower().lstrip("\ufeff") for c in orders_df.columns]
    items_df.columns  = [c.strip().lower().lstrip("\ufeff") for c in items_df.columns]

    # Validate that the right files were uploaded
    orders_required = {"order id", "to", "payments"}
    items_required  = {"order id", "description", "price"}
    missing_orders = orders_required - set(orders_df.columns)
    missing_items  = items_required  - set(items_df.columns)
    if missing_orders:
        raise HTTPException(
            status_code=400,
            detail=f"Orders file is missing columns: {missing_orders}. "
                   "Make sure you uploaded the correct file (one row per order).",
        )
    if missing_items:
        raise HTTPException(
            status_code=400,
            detail=f"Items file is missing columns: {missing_items}. "
                   "Make sure you uploaded the correct file (one row per item).",
        )

    # --- Identify grocery order IDs ---
    grocery_order_ids: set[str] = set(
        orders_df[
            orders_df["to"].astype(str).str.strip() == WF_TO_VALUE
        ]["order id"].astype(str)
    )

    # --- Group items by order_id ---
    items_df["order id"] = items_df["order id"].astype(str)
    items_by_order: dict[str, list[dict]] = {}
    for _, row in items_df.iterrows():
        oid = str(row["order id"])
        items_by_order.setdefault(oid, []).append({
            "description": str(row.get("description", "")).strip(),
            "price": _parse_price(str(row.get("price", "0"))),
            "quantity": _parse_quantity(row.get("quantity", 1)),
            "asin": str(row.get("asin", "")).strip(),
        })

    # --- Load categories for AI ---
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

    # --- Build flat item list for AI (non-grocery only) ---
    non_grocery_order_ids = set(
        orders_df[
            orders_df["to"].astype(str).str.strip() != WF_TO_VALUE
        ]["order id"].astype(str)
    )
    ai_items: list[dict] = []
    ai_item_map: list[tuple[str, int]] = []  # (order_id, item_index)

    for oid in non_grocery_order_ids:
        for i, item in enumerate(items_by_order.get(oid, [])):
            if item["description"]:
                ai_items.append({
                    "index": len(ai_items),
                    "merchant_name": item["description"],
                    "raw_description": item["description"],
                    "amount": str(item["price"]),
                })
                ai_item_map.append((oid, i))

    # --- AI category suggestions ---
    suggestions_map: dict[int, dict] = {}
    if ai_items:
        try:
            suggestions = await ai_service.suggest_categories(ai_items, category_dicts)
            suggestions_map = {s["index"]: s for s in suggestions if isinstance(s, dict)}
        except ai_service.RateLimitError:
            logger.warning("AI rate limited during Amazon analysis — proceeding without suggestions")
        except Exception:
            logger.exception("AI suggestion failed during Amazon analysis")

    # Attach suggestions back to items
    for flat_idx, (oid, item_i) in enumerate(ai_item_map):
        s = suggestions_map.get(flat_idx, {})
        item = items_by_order[oid][item_i]
        try:
            item["suggested_category_id"] = (
                uuid.UUID(s["category_id"]) if s.get("category_id") else None
            )
            item["suggested_subcategory_id"] = (
                uuid.UUID(s["subcategory_id"]) if s.get("subcategory_id") else None
            )
        except (ValueError, AttributeError):
            item["suggested_category_id"] = None
            item["suggested_subcategory_id"] = None

    # --- Match each order to a DB transaction ---
    grocery_matches: list[GroceryMatch] = []
    regular_orders: list[RegularOrder] = []
    unmatched: list[UnmatchedOrder] = []

    for _, order_row in orders_df.iterrows():
        oid = str(order_row["order id"])
        order_date = str(order_row.get("date", "")).strip()
        to_field = str(order_row.get("to", "")).strip()
        amount = _extract_payment_amount(str(order_row.get("payments", "")))

        if amount is None or amount <= 0:
            unmatched.append(UnmatchedOrder(
                order_id=oid, order_date=order_date, to=to_field,
                amount=None, reason="no_payment_amount",
            ))
            continue

        is_grocery = oid in grocery_order_ids
        txn = await _find_amazon_txn(db, amount, order_date)

        if is_grocery:
            order_items = items_by_order.get(oid, [])
            summary_parts = [i["description"] for i in order_items[:5] if i["description"]]
            summary = "; ".join(summary_parts)
            if len(order_items) > 5:
                summary += f" … +{len(order_items) - 5} more"
            grocery_matches.append(GroceryMatch(
                order_id=oid,
                order_date=order_date,
                transaction_id=txn.id if txn else None,
                transaction_date=str(txn.transaction_date) if txn else None,
                amount=amount,
                items_summary=summary,
            ))
        else:
            order_items = items_by_order.get(oid, [])
            if txn:
                regular_orders.append(RegularOrder(
                    order_id=oid,
                    order_date=order_date,
                    transaction_id=txn.id,
                    transaction_date=str(txn.transaction_date),
                    amount=amount,
                    items=[
                        AnalyzeOrderItem(
                            description=it["description"],
                            price=it["price"],
                            quantity=it["quantity"],
                            asin=it["asin"],
                            suggested_category_id=it.get("suggested_category_id"),
                            suggested_subcategory_id=it.get("suggested_subcategory_id"),
                        )
                        for it in order_items
                    ],
                ))
            else:
                unmatched.append(UnmatchedOrder(
                    order_id=oid, order_date=order_date, to=to_field,
                    amount=amount, reason="no_transaction_found",
                ))

    return AmazonAnalysisResponse(
        grocery_matches=grocery_matches,
        regular_orders=regular_orders,
        unmatched=unmatched,
    )


@router.post("/apply-groceries")
async def apply_groceries(
    body: ApplyGroceriesRequest,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    """
    Update matched grocery transactions:
      merchant_name  → "Whole Foods Market - Uptown Dallas"
      category_id    → provided value
      subcategory_id → provided value
    """
    if not body.matches:
        return {"updated": 0}

    updated = 0
    snapshots: list[dict] = []
    for match in body.matches:
        result = await db.execute(
            select(Transaction).where(Transaction.id == match.transaction_id)
        )
        txn = result.scalar_one_or_none()
        if not txn:
            continue
        snapshots.append(budget_lifecycle.budget_snapshot(txn))
        txn.merchant_name = WHOLE_FOODS_NAME
        txn.category_id = match.category_id
        txn.subcategory_id = match.subcategory_id
        snapshots.append(budget_lifecycle.budget_snapshot(txn))
        updated += 1

    await db.flush()
    # Categorizing can affect settled months (FR-4.4)
    await budget_lifecycle.reconcile_transaction_change(db, snapshots)
    return {"updated": updated}


@router.post("/itemize")
async def itemize_orders(
    body: ItemizeRequest,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    """
    For each order: create one transaction per item (inheriting account + date from
    the parent), then repurpose the parent as an "Amazon Order Taxes/Fees" row whose
    amount is the original charge minus the sum of all item prices.
    """
    if not body.orders:
        return {"created": 0, "modified": 0}

    created = 0
    modified = 0
    snapshots: list[dict] = []

    for order in body.orders:
        result = await db.execute(
            select(Transaction).where(Transaction.id == order.parent_transaction_id)
        )
        parent = result.scalar_one_or_none()
        if not parent:
            logger.warning("Parent transaction %s not found — skipping", order.parent_transaction_id)
            continue

        snapshots.append(budget_lifecycle.budget_snapshot(parent))

        # Create one child transaction per item
        for item in order.items:
            child = Transaction(
                id=uuid.uuid4(),
                account_id=parent.account_id,
                transaction_date=parent.transaction_date,
                raw_description=item.description,
                merchant_name=AMAZON_MERCHANT,
                amount=item.price * item.quantity if item.quantity > 1 else item.price,
                category_id=item.category_id,
                subcategory_id=item.subcategory_id,
                ai_suggested_category_id=item.category_id,
                ai_suggested_subcategory_id=item.subcategory_id,
                is_recurring=False,
                import_source="amazon_itemization",
                import_batch_id=parent.import_batch_id,
            )
            db.add(child)
            snapshots.append(budget_lifecycle.budget_snapshot(child))
            created += 1

        # Repurpose parent as taxes/fees row instead of deleting it
        items_total = sum(
            item.price * item.quantity if item.quantity > 1 else item.price
            for item in order.items
        )
        taxes_amount = max(Decimal("0"), parent.amount - items_total)

        # Most common category among the confirmed items
        cat_counts: Counter = Counter(
            item.category_id for item in order.items if item.category_id
        )
        most_common_cat = cat_counts.most_common(1)[0][0] if cat_counts else None

        parent.raw_description = f"Amazon Order Taxes/Fees - {order.order_id}"
        parent.merchant_name = AMAZON_MERCHANT
        parent.amount = taxes_amount
        parent.category_id = most_common_cat
        parent.subcategory_id = None
        parent.ai_suggested_category_id = most_common_cat
        parent.ai_suggested_subcategory_id = None
        snapshots.append(budget_lifecycle.budget_snapshot(parent))
        modified += 1

    await db.flush()
    # Itemization re-dates/re-categorizes spend; settled months recompute (FR-4.4)
    await budget_lifecycle.reconcile_transaction_change(db, snapshots)
    return {"created": created, "modified": modified}
