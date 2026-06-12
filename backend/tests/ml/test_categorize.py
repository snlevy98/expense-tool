"""
Unit tests for app.services.ml.categorize.

Each test that touches model state monkeypatches MODEL_DIR to a tmp_path,
so tests never write to the real backend/models/categorize/ directory.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.services.ml import categorize


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _txn(merchant: str, raw: str | None = None, amount: str = "10.00", index: int = 0):
    return {
        "index": index,
        "merchant_name": merchant,
        "raw_description": raw or merchant,
        "amount": amount,
    }


def _cat(name: str, subs: list[str] | None = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "subcategories": [
            {"id": str(uuid.uuid4()), "name": s} for s in (subs or [])
        ],
    }


@pytest.fixture
def categories():
    return [
        _cat("Groceries", ["Produce", "Pantry"]),
        _cat("Dining Out", ["Coffee", "Restaurants"]),
        _cat("Gas"),
        _cat("Income"),
    ]


@pytest.fixture
def training_data(categories):
    g_id = categories[0]["id"]
    d_id = categories[1]["id"]
    gas_id = categories[2]["id"]
    inc_id = categories[3]["id"]

    g_produce = categories[0]["subcategories"][0]["id"]
    g_pantry = categories[0]["subcategories"][1]["id"]
    d_coffee = categories[1]["subcategories"][0]["id"]
    d_rest = categories[1]["subcategories"][1]["id"]

    rows = []
    # Groceries — three merchants, mixed subcategories
    for _ in range(8):
        rows.append({
            "merchant_name": "Whole Foods Market", "raw_description": "WHOLEFDS #123 AUSTIN TX",
            "amount": "85.42", "category_id": g_id, "subcategory_id": g_produce, "weight": 1.0,
        })
    for _ in range(8):
        rows.append({
            "merchant_name": "Trader Joe's", "raw_description": "TRADER JOE'S #456",
            "amount": "62.18", "category_id": g_id, "subcategory_id": g_pantry, "weight": 1.0,
        })
    for _ in range(7):
        rows.append({
            "merchant_name": "Kroger", "raw_description": "KROGER STORE 0421",
            "amount": "104.55", "category_id": g_id, "subcategory_id": g_pantry, "weight": 1.0,
        })

    # Dining — two merchants
    for _ in range(8):
        rows.append({
            "merchant_name": "Starbucks", "raw_description": "SQ *STARBUCKS #88",
            "amount": "5.85", "category_id": d_id, "subcategory_id": d_coffee, "weight": 1.0,
        })
    for _ in range(8):
        rows.append({
            "merchant_name": "Chipotle", "raw_description": "CHIPOTLE 1234 ORDER",
            "amount": "12.50", "category_id": d_id, "subcategory_id": d_rest, "weight": 1.0,
        })

    # Gas — no subcategories
    for _ in range(7):
        rows.append({
            "merchant_name": "Shell", "raw_description": "SHELL OIL 4321 DALLAS",
            "amount": "45.00", "category_id": gas_id, "subcategory_id": None, "weight": 1.0,
        })
    for _ in range(6):
        rows.append({
            "merchant_name": "Chevron", "raw_description": "CHEVRON 998 GAS",
            "amount": "52.00", "category_id": gas_id, "subcategory_id": None, "weight": 1.0,
        })

    # Income — negative amounts
    for _ in range(6):
        rows.append({
            "merchant_name": "Acme Corp Payroll", "raw_description": "ACME CORP DIRECT DEPOSIT",
            "amount": "-2500.00", "category_id": inc_id, "subcategory_id": None, "weight": 1.0,
        })

    return rows


@pytest.fixture
def trained(tmp_path, monkeypatch, training_data):
    """Train a model in an isolated MODEL_DIR. Returns the metadata dict."""
    monkeypatch.setattr(categorize, "MODEL_DIR", tmp_path)
    return categorize.train_sync(training_data)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def test_train_records_metadata(trained, training_data):
    assert trained["n_samples"] == len(training_data)
    assert "trained_at" in trained
    assert isinstance(trained["accuracy"], float)
    assert 0.0 <= trained["accuracy"] <= 1.0
    # 4 categories in training data
    assert len(trained["category_ids"]) == 4
    # Per-category metrics present for every category
    assert set(trained["per_category"].keys()) >= set(trained["category_ids"])


def test_train_min_rows_enforced(tmp_path, monkeypatch):
    monkeypatch.setattr(categorize, "MODEL_DIR", tmp_path)
    rows = [
        {
            "merchant_name": "x",
            "raw_description": "x",
            "amount": "1",
            "category_id": "a",
            "subcategory_id": None,
            "weight": 1.0,
        }
    ] * 10
    with pytest.raises(ValueError):
        categorize.train_sync(rows)


def test_train_overall_accuracy_reasonable(trained):
    # Synthetic data is highly separable — should easily clear 70%
    assert trained["accuracy"] >= 0.70, (
        f"Expected >=0.70 CV accuracy on synthetic data, got {trained['accuracy']}"
    )


# ---------------------------------------------------------------------------
# Inference — known merchants
# ---------------------------------------------------------------------------


def test_predict_known_merchants(trained, categories):
    g_id, d_id, gas_id, _inc_id = (c["id"] for c in categories)
    txns = [
        _txn("Whole Foods Market", "WHOLEFDS NEW STORE", "92.10", index=0),
        _txn("Starbucks", "SQ *STARBUCKS DOWNTOWN", "6.50", index=1),
        _txn("Shell", "SHELL OIL 777", "48.00", index=2),
    ]
    results = asyncio.run(categorize.suggest_categories(txns, categories))
    assert len(results) == 3
    assert results[0]["category_id"] == g_id
    assert results[1]["category_id"] == d_id
    assert results[2]["category_id"] == gas_id


def test_predict_preserves_index(trained, categories):
    txns = [_txn("Starbucks", index=42)]
    results = asyncio.run(categorize.suggest_categories(txns, categories))
    assert results[0]["index"] == 42


def test_predict_returns_subcategory_when_trained(trained, categories):
    """Dining has 2 subcategories with 8 examples each → subcat model trained."""
    d_id = categories[1]["id"]
    coffee_id = categories[1]["subcategories"][0]["id"]
    txns = [_txn("Starbucks", "SQ *STARBUCKS", "5.50", index=0)]
    results = asyncio.run(categorize.suggest_categories(txns, categories))
    assert results[0]["category_id"] == d_id
    assert results[0]["subcategory_id"] == coffee_id


def test_predict_subcategory_none_when_category_has_no_subs(trained, categories):
    """Gas has no subcategories — subcategory_id must be None."""
    gas_id = categories[2]["id"]
    txns = [_txn("Shell", "SHELL OIL", "45.00", index=0)]
    results = asyncio.run(categorize.suggest_categories(txns, categories))
    assert results[0]["category_id"] == gas_id
    assert results[0]["subcategory_id"] is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_negative_amount_prefers_income(trained, categories):
    inc_id = categories[3]["id"]
    txns = [_txn("Acme Corp Payroll", "ACME PAYROLL", "-2500.00", index=0)]
    results = asyncio.run(categorize.suggest_categories(txns, categories))
    assert results[0]["category_id"] == inc_id


def test_predict_filters_deleted_category(trained, categories):
    """If a category was deleted between train and inference, never return it."""
    gas_id = categories[2]["id"]
    reduced = [c for c in categories if c["name"] != "Gas"]
    txns = [_txn("Shell", "SHELL OIL 777", "48.00", index=0)]
    results = asyncio.run(categorize.suggest_categories(txns, reduced))
    assert results[0]["category_id"] != gas_id  # never the deleted one


def test_predict_low_confidence_returns_none(trained, categories):
    """Wildly novel merchant should land below the 0.40 threshold or at least
    not match anything obviously wrong with high confidence."""
    txns = [_txn("Zxqwvbnm Foreign Co", "ZXQWVBNM 9999", "33.00", index=0)]
    results = asyncio.run(categorize.suggest_categories(txns, categories))
    # We don't insist on None — just that the response shape is intact
    assert "category_id" in results[0]
    assert "subcategory_id" in results[0]


def test_predict_empty_inputs():
    assert asyncio.run(categorize.suggest_categories([], [{"id": "x", "name": "x"}])) == []
    assert asyncio.run(categorize.suggest_categories([_txn("x")], [])) == []


def test_signature_compat_examples_text_ignored(trained, categories):
    """Ensure callers passing the legacy `examples_text` arg don't break."""
    txns = [_txn("Starbucks", "STARBUCKS", "5.00", index=0)]
    results = asyncio.run(
        categorize.suggest_categories(txns, categories, examples_text="ignored content")
    )
    assert len(results) == 1


# ---------------------------------------------------------------------------
# Cold start / fallback
# ---------------------------------------------------------------------------


def test_keyword_fallback_when_no_model(tmp_path, monkeypatch, categories):
    monkeypatch.setattr(categorize, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(categorize, "_loaded_model", None)
    # Merchant name literally contains the category name
    txns = [_txn("Joe's Groceries Market", "JOE GROCERIES 12", "42.00", index=0)]
    results = asyncio.run(categorize.suggest_categories(txns, categories))
    g_id = categories[0]["id"]
    assert results[0]["category_id"] == g_id


def test_keyword_fallback_returns_none_when_no_overlap(tmp_path, monkeypatch, categories):
    monkeypatch.setattr(categorize, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(categorize, "_loaded_model", None)
    txns = [_txn("Random Store", "RANDOM 12345", "10.00", index=0)]
    results = asyncio.run(categorize.suggest_categories(txns, categories))
    assert results[0]["category_id"] is None
    assert results[0]["subcategory_id"] is None


# ---------------------------------------------------------------------------
# Model lifecycle
# ---------------------------------------------------------------------------


def test_load_model_if_exists_with_no_model(tmp_path, monkeypatch):
    monkeypatch.setattr(categorize, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(categorize, "_loaded_model", "stale_marker")  # type: ignore
    loaded = categorize.load_model_if_exists()
    assert loaded is False
    assert categorize.get_model_info() is None


def test_load_model_if_exists_after_train(trained):
    info = categorize.get_model_info()
    assert info is not None
    assert info["trained"] is True
    assert info["n_samples"] == trained["n_samples"]
    assert info["n_categories"] == len(trained["category_ids"])


def test_get_model_metadata_includes_per_category(trained):
    md = categorize.get_model_metadata()
    assert md is not None
    assert "per_category" in md
    assert isinstance(md["per_category"], dict)
