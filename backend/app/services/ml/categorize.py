"""
Local TF-IDF + LogReg category suggestion.

Drop-in replacement for ai_service.suggest_categories — same async signature,
same return shape, no external API.

Architecture (Stage 2 spec):

  Stage A — Category classifier
    Pipeline: ColumnTransformer(merchant_name char-ngrams, raw_description word-ngrams,
                                amount numeric features) → LogisticRegression
    Returns probability distribution over the user's category_ids.

  Stage B — Per-category subcategory classifiers
    One small pipeline per category that has >= 5 training examples AND >= 2 distinct
    subcategories. Categories below that threshold get subcategory_id=None at inference.

Confidence:
  Category top-prob >= 0.40 → return prediction; else None
  Subcategory top-prob >= 0.30 → return prediction; else None

Persistence:
  backend/models/categorize/
    metadata.json
    category_clf.joblib
    subcat_<category_id>.joblib
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# backend/models/categorize/  (relative to this file: ../../../models/categorize)
MODEL_DIR: Path = (
    Path(__file__).resolve().parent.parent.parent.parent / "models" / "categorize"
)

CATEGORY_CONFIDENCE_THRESHOLD = 0.40
SUBCATEGORY_CONFIDENCE_THRESHOLD = 0.30
MIN_TRAIN_ROWS = 30
SUBCATEGORY_MIN_EXAMPLES = 5

# Regex used both for income detection and keyword fallback tokenization
_INCOME_REGEX = re.compile(r"income|refund|credit", re.IGNORECASE)
_TOKEN_REGEX = re.compile(r"[a-z0-9]+")


# ---------------------------------------------------------------------------
# Feature transformer for amount
# ---------------------------------------------------------------------------


class AmountFeatures(BaseEstimator, TransformerMixin):
    """
    Turns a 1-D iterable of amount strings into 6 numeric features:
      [is_negative, log1p(|amount|),
       bucket_0_25, bucket_25_100, bucket_100_500, bucket_500_plus]
    """

    def fit(self, X, y=None):  # noqa: D401 — sklearn API
        return self

    def transform(self, X):
        # ColumnTransformer with a single string column key passes a 1-D pandas Series.
        # ColumnTransformer with a list passes a 2-D DataFrame. Handle both.
        if hasattr(X, "values"):
            arr = X.values
        else:
            arr = np.asarray(X)
        if arr.ndim > 1:
            arr = arr.ravel()

        rows = np.zeros((len(arr), 6), dtype=np.float32)
        for i, a in enumerate(arr):
            try:
                v = float(a)
            except (TypeError, ValueError):
                v = 0.0
            abs_v = abs(v)
            rows[i, 0] = 1.0 if v < 0 else 0.0
            rows[i, 1] = math.log1p(abs_v)
            rows[i, 2] = 1.0 if abs_v < 25 else 0.0
            rows[i, 3] = 1.0 if 25 <= abs_v < 100 else 0.0
            rows[i, 4] = 1.0 if 100 <= abs_v < 500 else 0.0
            rows[i, 5] = 1.0 if abs_v >= 500 else 0.0
        return rows


# ---------------------------------------------------------------------------
# Pipeline factory
# ---------------------------------------------------------------------------


def _build_pipeline() -> Pipeline:
    return Pipeline(
        [
            (
                "features",
                ColumnTransformer(
                    transformers=[
                        (
                            "merchant",
                            TfidfVectorizer(
                                analyzer="char_wb",
                                ngram_range=(3, 5),
                                min_df=1,
                                max_features=2000,
                                lowercase=True,
                            ),
                            "merchant_name",
                        ),
                        (
                            "desc",
                            TfidfVectorizer(
                                analyzer="word",
                                ngram_range=(1, 2),
                                min_df=1,
                                max_features=1000,
                                lowercase=True,
                            ),
                            "raw_description",
                        ),
                        ("amount", AmountFeatures(), "amount"),
                    ],
                    sparse_threshold=0.3,
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=1000,
                    class_weight="balanced",
                    C=1.0,
                    random_state=42,
                ),
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Singleton model state
# ---------------------------------------------------------------------------

_loaded_model: dict[str, Any] | None = None
_model_lock = threading.Lock()


def _load_from_disk() -> dict[str, Any] | None:
    """Read model artifacts from MODEL_DIR. Returns None if not present/corrupt."""
    meta_path = MODEL_DIR / "metadata.json"
    cat_path = MODEL_DIR / "category_clf.joblib"
    if not meta_path.exists() or not cat_path.exists():
        return None
    try:
        metadata = json.loads(meta_path.read_text())
        cat_clf = joblib.load(cat_path)
        subcat_clfs: dict[str, Any] = {}
        for path in MODEL_DIR.glob("subcat_*.joblib"):
            cat_id = path.stem.replace("subcat_", "")
            subcat_clfs[cat_id] = joblib.load(path)
        return {
            "metadata": metadata,
            "cat_clf": cat_clf,
            "subcat_clfs": subcat_clfs,
        }
    except Exception:
        logger.exception("Failed to load categorization model from %s", MODEL_DIR)
        return None


def load_model_if_exists() -> bool:
    """Load model into the singleton. Called on app startup. Idempotent."""
    global _loaded_model
    new_model = _load_from_disk()
    with _model_lock:
        _loaded_model = new_model
    if new_model is not None:
        logger.info(
            "Categorization model loaded: trained_at=%s n=%d accuracy=%.3f",
            new_model["metadata"].get("trained_at"),
            new_model["metadata"].get("n_samples", 0),
            new_model["metadata"].get("accuracy", 0.0),
        )
        return True
    logger.info("No categorization model on disk — running in keyword-fallback mode")
    return False


def get_model_info() -> dict[str, Any] | None:
    """Lightweight summary for UI badges / health checks."""
    with _model_lock:
        model = _loaded_model
    if model is None:
        return None
    md = model["metadata"]
    return {
        "trained": True,
        "trained_at": md.get("trained_at"),
        "accuracy": md.get("accuracy"),
        "n_samples": md.get("n_samples"),
        "n_categories": len(md.get("category_ids", [])),
        "n_subcategory_models": len(md.get("subcategory_models", [])),
        "version": md.get("version"),
    }


def get_model_metadata() -> dict[str, Any] | None:
    """Full metadata including per-category accuracy. Used by stats endpoint."""
    with _model_lock:
        model = _loaded_model
    if model is None:
        return None
    return dict(model["metadata"])


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def train_sync(rows: list[dict]) -> dict[str, Any]:
    """
    Synchronous training entry point. Call via ``asyncio.to_thread``.

    rows: list of dicts with keys:
      merchant_name, raw_description, amount (str), category_id (str),
      subcategory_id (str | None), weight (float)
    """
    if len(rows) < MIN_TRAIN_ROWS:
        raise ValueError(
            f"Need at least {MIN_TRAIN_ROWS} confirmed transactions to train; "
            f"got {len(rows)}"
        )

    df = pd.DataFrame(rows)
    # Defensive: ensure required columns exist and have sensible dtypes
    for col in ("merchant_name", "raw_description", "amount", "category_id", "weight"):
        if col not in df.columns:
            raise ValueError(f"Training rows missing required column: {col}")
    df["merchant_name"] = df["merchant_name"].fillna("").astype(str)
    df["raw_description"] = df["raw_description"].fillna("").astype(str)
    df["amount"] = df["amount"].fillna("0").astype(str)
    df["category_id"] = df["category_id"].astype(str)
    df["weight"] = df["weight"].astype(float)

    X = df[["merchant_name", "raw_description", "amount"]]
    y = df["category_id"].to_numpy()
    weights = df["weight"].to_numpy()

    # ---- Stage A: category classifier ----
    cat_clf = _build_pipeline()
    cat_clf.fit(X, y, clf__sample_weight=weights)

    # ---- Cross-validated per-category accuracy ----
    overall_accuracy, per_category = _evaluate_cv(X, y, weights)

    # ---- Stage B: per-category subcategory classifiers ----
    subcat_clfs: dict[str, Pipeline] = {}
    if "subcategory_id" in df.columns:
        for cat_id in df["category_id"].unique():
            sub_df = df[
                (df["category_id"] == cat_id) & df["subcategory_id"].notna()
            ].copy()
            if len(sub_df) < SUBCATEGORY_MIN_EXAMPLES:
                continue
            sub_df["subcategory_id"] = sub_df["subcategory_id"].astype(str)
            if sub_df["subcategory_id"].nunique() < 2:
                continue
            sub_X = sub_df[["merchant_name", "raw_description", "amount"]]
            sub_y = sub_df["subcategory_id"].to_numpy()
            sub_w = sub_df["weight"].to_numpy()
            sub_pipe = _build_pipeline()
            try:
                sub_pipe.fit(sub_X, sub_y, clf__sample_weight=sub_w)
                subcat_clfs[cat_id] = sub_pipe
            except Exception:
                logger.exception(
                    "Subcategory classifier failed for category %s", cat_id
                )

    # ---- Persist ----
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    # Wipe stale subcat files from previous training runs
    for old in MODEL_DIR.glob("subcat_*.joblib"):
        try:
            old.unlink()
        except OSError:
            pass
    joblib.dump(cat_clf, MODEL_DIR / "category_clf.joblib", compress=3)
    for cat_id, clf in subcat_clfs.items():
        joblib.dump(clf, MODEL_DIR / f"subcat_{cat_id}.joblib", compress=3)

    metadata = {
        "version": int(time.time()),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": int(len(df)),
        "n_user_corrections": int((df["weight"] >= 3.0).sum()),
        "category_ids": sorted(df["category_id"].unique().tolist()),
        "subcategory_models": sorted(subcat_clfs.keys()),
        "accuracy": float(overall_accuracy),
        "per_category": per_category,
    }
    (MODEL_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2))

    # Atomic swap into the singleton
    load_model_if_exists()

    return metadata


def _evaluate_cv(
    X: pd.DataFrame, y: np.ndarray, weights: np.ndarray
) -> tuple[float, dict[str, dict]]:
    """
    Stratified 5-fold CV (or fewer folds if any class has <5 examples).
    Returns (overall_accuracy, per_category={cat_id: {n, accuracy}})

    Categories with <2 examples are excluded from the CV but still reported
    with accuracy=None so the UI can flag them as "too few to evaluate".
    """
    counts = pd.Series(y).value_counts()
    rare_classes = set(counts[counts < 2].index.tolist())

    keep_mask = ~pd.Series(y).isin(rare_classes).to_numpy()
    X_cv = X[keep_mask]
    y_cv = y[keep_mask]
    w_cv = weights[keep_mask]

    per_category: dict[str, dict] = {}
    # Pre-fill rare classes
    for cat in rare_classes:
        per_category[str(cat)] = {"n": int(counts[cat]), "accuracy": None}

    if len(set(y_cv)) < 2:
        # Not enough class diversity for any meaningful CV
        return 0.0, per_category

    n_splits = min(5, int(pd.Series(y_cv).value_counts().min()))
    if n_splits < 2:
        # Even the smallest CV-eligible class has only 1 example after filtering
        for cat, n in counts.items():
            per_category.setdefault(str(cat), {"n": int(n), "accuracy": None})
        return 0.0, per_category

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

    correct: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)

    for train_idx, test_idx in skf.split(X_cv, y_cv):
        fold = _build_pipeline()
        fold.fit(
            X_cv.iloc[train_idx],
            y_cv[train_idx],
            clf__sample_weight=w_cv[train_idx],
        )
        preds = fold.predict(X_cv.iloc[test_idx])
        for true_label, pred_label in zip(y_cv[test_idx], preds):
            total[str(true_label)] += 1
            if true_label == pred_label:
                correct[str(true_label)] += 1

    overall = (
        sum(correct.values()) / sum(total.values()) if total else 0.0
    )
    for cat, n in total.items():
        per_category[cat] = {
            "n": int(n),
            "accuracy": (correct[cat] / n) if n else None,
        }
    return float(overall), per_category


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------


async def suggest_categories(
    transactions: list[dict],
    categories: list[dict],
    examples_text: str = "",  # accepted for compat with ai_service signature
) -> list[dict]:
    """
    Drop-in replacement for ai_service.suggest_categories.

    Returns one dict per input transaction:
      {"index": int, "category_id": "uuid-str" | None, "subcategory_id": "uuid-str" | None}
    """
    if not transactions or not categories:
        return []

    # Even with a model, if a category was created after training, it can't be
    # predicted — but unchanged categories still work fine.
    allowed_cat_ids: set[str] = {str(c["id"]) for c in categories}
    allowed_subcat_ids: dict[str, set[str]] = {
        str(c["id"]): {str(s["id"]) for s in c.get("subcategories", [])}
        for c in categories
    }
    income_cat_ids: set[str] = {
        str(c["id"])
        for c in categories
        if _INCOME_REGEX.search(c.get("name", "") or "")
    }

    with _model_lock:
        model = _loaded_model

    if model is None:
        return _keyword_fallback(transactions, categories)

    return await asyncio.to_thread(
        _predict_sync,
        transactions,
        model,
        allowed_cat_ids,
        allowed_subcat_ids,
        income_cat_ids,
    )


def _predict_sync(
    transactions: list[dict],
    model: dict[str, Any],
    allowed_cat_ids: set[str],
    allowed_subcat_ids: dict[str, set[str]],
    income_cat_ids: set[str],
) -> list[dict]:
    cat_clf: Pipeline = model["cat_clf"]
    subcat_clfs: dict[str, Pipeline] = model["subcat_clfs"]

    df = pd.DataFrame(
        [
            {
                "merchant_name": (
                    t.get("merchant_name") or t.get("raw_description") or ""
                ),
                "raw_description": t.get("raw_description") or "",
                "amount": str(t.get("amount", "0")),
            }
            for t in transactions
        ]
    )

    cat_classes = np.asarray([str(c) for c in cat_clf.classes_])
    cat_probs = cat_clf.predict_proba(df)

    allowed_mask = np.array([c in allowed_cat_ids for c in cat_classes], dtype=bool)

    results: list[dict] = []
    for i, t in enumerate(transactions):
        idx = t.get("index", i)
        probs = cat_probs[i].copy()
        probs[~allowed_mask] = 0.0

        if probs.sum() == 0:
            results.append({"index": idx, "category_id": None, "subcategory_id": None})
            continue

        # Negative-amount → income-like preference (mirrors the Groq prompt rule).
        # Only apply if an income-like category is in the top-3 candidates;
        # otherwise the model probably has a better idea (e.g. a refund category).
        try:
            amt = float(t.get("amount", 0) or 0)
        except (TypeError, ValueError):
            amt = 0.0
        if amt < 0 and income_cat_ids:
            top3 = np.argsort(probs)[-3:]
            for j in top3:
                if cat_classes[j] in income_cat_ids:
                    # Promote to top by setting just above current max
                    probs[j] = float(probs.max()) + 0.01
                    break

        top_idx = int(np.argmax(probs))
        top_p = float(probs[top_idx])
        cat_id = str(cat_classes[top_idx])

        if top_p < CATEGORY_CONFIDENCE_THRESHOLD:
            results.append({"index": idx, "category_id": None, "subcategory_id": None})
            continue

        # ---- Subcategory ----
        subcat_id: str | None = None
        if cat_id in subcat_clfs:
            allowed_subs = allowed_subcat_ids.get(cat_id, set())
            sub_pipe = subcat_clfs[cat_id]
            sub_classes = np.asarray([str(s) for s in sub_pipe.classes_])
            sub_probs = sub_pipe.predict_proba(df.iloc[[i]])[0].copy()
            sub_allowed_mask = np.array(
                [s in allowed_subs for s in sub_classes], dtype=bool
            )
            sub_probs[~sub_allowed_mask] = 0.0
            if sub_probs.sum() > 0:
                sub_top = int(np.argmax(sub_probs))
                if float(sub_probs[sub_top]) >= SUBCATEGORY_CONFIDENCE_THRESHOLD:
                    subcat_id = str(sub_classes[sub_top])

        results.append(
            {"index": idx, "category_id": cat_id, "subcategory_id": subcat_id}
        )

    return results


# ---------------------------------------------------------------------------
# Cold-start / no-model fallback
# ---------------------------------------------------------------------------


def _keyword_fallback(
    transactions: list[dict], categories: list[dict]
) -> list[dict]:
    """
    No-model fallback: token overlap between merchant_name and category names.
    Returns category_id=None when no category shares any token with the merchant.
    """
    results: list[dict] = []
    for i, t in enumerate(transactions):
        merchant = (t.get("merchant_name") or t.get("raw_description") or "").lower()
        merchant_tokens = set(_TOKEN_REGEX.findall(merchant))

        best_cat_id: str | None = None
        best_subcat_id: str | None = None
        best_score = 0

        for cat in categories:
            cat_tokens = set(_TOKEN_REGEX.findall((cat.get("name") or "").lower()))
            score = len(merchant_tokens & cat_tokens)
            if score > best_score:
                best_score = score
                best_cat_id = str(cat["id"])
                best_subcat_id = None
                for sub in cat.get("subcategories", []):
                    sub_tokens = set(
                        _TOKEN_REGEX.findall((sub.get("name") or "").lower())
                    )
                    if merchant_tokens & sub_tokens:
                        best_subcat_id = str(sub["id"])
                        break

        results.append(
            {
                "index": t.get("index", i),
                "category_id": best_cat_id,
                "subcategory_id": best_subcat_id,
            }
        )
    return results
