"""
ML model management router.

  POST /api/ml/train                — retrain the categorization model from
                                      all confirmed transactions in the DB
  GET  /api/ml/training-data/stats  — per-category counts + per-category
                                      cross-validated accuracy from the
                                      currently loaded model (powers the
                                      Settings → Machine Learning panel)
  GET  /api/ml/model/info           — lightweight model summary for header
                                      badges / health checks
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.middleware.auth import require_auth
from app.models.category import Category
from app.models.transaction import Transaction
from app.services.ml import categorize

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ml", tags=["ml"])

# Single in-flight training run at a time — same pattern as enrichment_service.
_train_lock = asyncio.Lock()


@router.post("/train")
async def train_model(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    """Retrain the categorization model on all confirmed transactions."""
    if _train_lock.locked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Training already in progress — try again in a few seconds.",
        )

    async with _train_lock:
        # Pull labeled training data
        result = await db.execute(
            select(
                Transaction.merchant_name,
                Transaction.raw_description,
                Transaction.amount,
                Transaction.category_id,
                Transaction.subcategory_id,
                Transaction.ai_suggested_category_id,
            )
            .where(Transaction.category_id.isnot(None))
            .where(Transaction.merchant_name.isnot(None))
            .where(Transaction.merchant_name != "")
        )
        rows = result.all()

        if len(rows) < categorize.MIN_TRAIN_ROWS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Need at least {categorize.MIN_TRAIN_ROWS} confirmed "
                    f"transactions to train; have {len(rows)}."
                ),
            )

        # Sample-weight user corrections 3× — they're the highest-quality signal
        training_rows = []
        for r in rows:
            corrected = (
                r.ai_suggested_category_id is not None
                and r.category_id != r.ai_suggested_category_id
            )
            training_rows.append(
                {
                    "merchant_name": r.merchant_name,
                    "raw_description": r.raw_description or "",
                    "amount": str(r.amount),
                    "category_id": str(r.category_id),
                    "subcategory_id": (
                        str(r.subcategory_id) if r.subcategory_id else None
                    ),
                    "weight": 3.0 if corrected else 1.0,
                }
            )

        try:
            metadata = await asyncio.to_thread(categorize.train_sync, training_rows)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        except Exception:
            logger.exception("Categorization model training failed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Training failed — check server logs.",
            )

    return metadata


@router.get("/training-data/stats")
async def training_data_stats(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(require_auth),
) -> dict:
    """
    Returns counts + accuracy per category, in the shape the Settings panel
    needs to render the bucketed breakdown (Strong / Decent / Weak).
    """
    # Total confirmed
    total_q = await db.execute(
        select(func.count(Transaction.id))
        .where(Transaction.category_id.isnot(None))
        .where(Transaction.merchant_name.isnot(None))
        .where(Transaction.merchant_name != "")
    )
    total_confirmed = int(total_q.scalar() or 0)

    # User corrections (where AI suggested but user overrode)
    corrections_q = await db.execute(
        select(func.count(Transaction.id))
        .where(Transaction.category_id.isnot(None))
        .where(Transaction.ai_suggested_category_id.isnot(None))
        .where(Transaction.category_id != Transaction.ai_suggested_category_id)
    )
    user_corrections = int(corrections_q.scalar() or 0)

    # Per-category counts in one query
    counts_q = await db.execute(
        select(
            Transaction.category_id,
            func.count(Transaction.id).label("n"),
            func.count(func.distinct(Transaction.subcategory_id)).label("n_subs"),
        )
        .where(Transaction.category_id.isnot(None))
        .group_by(Transaction.category_id)
    )
    counts_by_cat: dict[str, dict[str, int]] = defaultdict(
        lambda: {"n": 0, "n_subs": 0}
    )
    for row in counts_q.all():
        counts_by_cat[str(row.category_id)] = {"n": int(row.n), "n_subs": int(row.n_subs)}

    # Categories (active only, with subcategories loaded)
    cat_q = await db.execute(
        select(Category)
        .options(selectinload(Category.subcategories))
        .where(Category.is_active.is_(True))
        .order_by(Category.name)
    )
    categories = cat_q.scalars().all()

    # Per-category model accuracy from the current trained model
    metadata = categorize.get_model_metadata()
    per_cat_metrics = (metadata or {}).get("per_category", {})

    cat_breakdown = []
    for c in categories:
        cid = str(c.id)
        counts = counts_by_cat.get(cid, {"n": 0, "n_subs": 0})
        metric = per_cat_metrics.get(cid)
        cat_breakdown.append(
            {
                "id": cid,
                "name": c.name,
                "color": c.color,
                "n_transactions": counts["n"],
                "n_subcategories_used": counts["n_subs"],
                "n_subcategories_available": len(c.subcategories),
                "accuracy": (metric.get("accuracy") if metric else None),
                "evaluated_n": (metric.get("n", 0) if metric else 0),
            }
        )

    return {
        "total_confirmed": total_confirmed,
        "user_corrections": user_corrections,
        "categories": cat_breakdown,
        "model": categorize.get_model_info(),
        "thresholds": {
            "min_train_rows": categorize.MIN_TRAIN_ROWS,
            "subcategory_min_examples": categorize.SUBCATEGORY_MIN_EXAMPLES,
            "category_confidence": categorize.CATEGORY_CONFIDENCE_THRESHOLD,
            "subcategory_confidence": categorize.SUBCATEGORY_CONFIDENCE_THRESHOLD,
        },
    }


@router.get("/model/info")
async def model_info(auth: dict = Depends(require_auth)) -> dict:
    """Lightweight model summary."""
    info = categorize.get_model_info()
    if info is None:
        return {"trained": False}
    return info
