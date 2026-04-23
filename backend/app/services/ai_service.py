"""
AI service using Google Gemini for:
  - Batch category suggestions
  - Merchant name normalization
  - Recurring transaction detection

NOTE on async: google-generativeai's generate_content_async() uses
blocking HTTP internally in v0.8.x and can deadlock inside uvicorn's
event loop. We use asyncio.to_thread() with the synchronous
generate_content() instead, which runs the call in a thread pool and
cooperates correctly with the async event loop.
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import date

import google.generativeai as genai

from app.config import settings

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.GEMINI_API_KEY)
_model = genai.GenerativeModel("gemini-2.0-flash")

_NORMALIZE_CHUNK = 40   # descriptions per Gemini call
_SUGGEST_CHUNK   = 50   # transactions per category-suggestion call


def _call_gemini(prompt: str) -> str:
    """Synchronous Gemini call — run via asyncio.to_thread to avoid blocking the event loop."""
    response = _model.generate_content(prompt)
    return response.text.strip()


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences that Gemini sometimes wraps around JSON."""
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


# ---------------------------------------------------------------------------
# Category suggestions
# ---------------------------------------------------------------------------

async def _suggest_categories_chunk(
    transactions: list[dict], categories: list[dict], index_offset: int
) -> list[dict]:
    """Suggest categories for one chunk of transactions. Returns [] on failure."""
    cat_text = json.dumps(
        [
            {
                "id": str(c.get("id", "")),
                "name": c.get("name", ""),
                "subcategories": [
                    {"id": str(s.get("id", "")), "name": s.get("name", "")}
                    for s in c.get("subcategories", [])
                ],
            }
            for c in categories
        ],
        indent=2,
    )

    txn_text = json.dumps(
        [
            {
                "index": index_offset + i,
                "merchant_name": t.get("merchant_name", t.get("raw_description", "")),
                "raw_description": t.get("raw_description", ""),
                "amount": str(t.get("amount", "")),
            }
            for i, t in enumerate(transactions)
        ],
        indent=2,
    )

    prompt = f"""You are a financial categorization assistant.

Given the following expense categories and subcategories:
{cat_text}

And the following transactions:
{txn_text}

For EACH transaction, suggest the most appropriate category_id and subcategory_id from the provided lists.
If no subcategory fits, use null for subcategory_id.
If no category fits, use null for both.

Respond ONLY with a valid JSON array. Each element must have:
  - index (integer, matching the transaction index above)
  - category_id (string UUID or null)
  - subcategory_id (string UUID or null)

Do not include any explanation or markdown fences. Output raw JSON only."""

    try:
        raw = await asyncio.to_thread(_call_gemini, prompt)
        raw = _strip_fences(raw)
        suggestions = json.loads(raw)
        return suggestions if isinstance(suggestions, list) else []
    except Exception:
        logger.exception("AI category suggestion chunk (offset=%d) failed", index_offset)
        return []


async def suggest_categories(
    transactions: list[dict], categories: list[dict]
) -> list[dict]:
    """
    Suggest category/subcategory for each transaction using Gemini.
    Processes in chunks of _SUGGEST_CHUNK to stay within token limits.

    Returns list of {index, category_id, subcategory_id}.
    On any error returns an empty list so the import continues.
    """
    if not transactions or not categories:
        return []

    results: list[dict] = []
    for start in range(0, len(transactions), _SUGGEST_CHUNK):
        chunk = transactions[start : start + _SUGGEST_CHUNK]
        results.extend(
            await _suggest_categories_chunk(chunk, categories, index_offset=start)
        )
    return results


# ---------------------------------------------------------------------------
# Merchant name normalization
# ---------------------------------------------------------------------------

async def _normalize_chunk(descriptions: list[str]) -> list[str]:
    """Normalize one chunk of descriptions. Returns originals on any failure."""
    numbered = "\n".join(f"{i}. {d}" for i, d in enumerate(descriptions))
    prompt = f"""Convert each bank transaction description below to a clean, human-readable merchant name.
Return ONLY a JSON array of strings in the same order.
Each string should be just the merchant name — no explanation, no extra punctuation.

Descriptions:
{numbered}

Respond with a JSON array only, like: ["Merchant A", "Merchant B", ...]
Do not include markdown fences or explanations."""

    try:
        raw = await asyncio.to_thread(_call_gemini, prompt)
        raw = _strip_fences(raw)
        names = json.loads(raw)
        if isinstance(names, list) and len(names) == len(descriptions):
            return [str(n).strip() or descriptions[i] for i, n in enumerate(names)]
        logger.warning(
            "Merchant normalization returned %d names for %d descriptions — using originals",
            len(names) if isinstance(names, list) else -1,
            len(descriptions),
        )
        return descriptions
    except Exception:
        logger.exception("Merchant normalization chunk failed")
        return descriptions


async def normalize_merchant_names_batch(descriptions: list[str]) -> list[str]:
    """
    Normalize a list of raw bank descriptions to human-readable merchant names.
    Processes in chunks of _NORMALIZE_CHUNK to stay within Gemini token limits.
    Falls back to the original description for any chunk that fails.
    """
    if not descriptions:
        return []

    results: list[str] = []
    for start in range(0, len(descriptions), _NORMALIZE_CHUNK):
        chunk = descriptions[start : start + _NORMALIZE_CHUNK]
        results.extend(await _normalize_chunk(chunk))
    return results


# ---------------------------------------------------------------------------
# Recurring detection
# ---------------------------------------------------------------------------

async def detect_recurring(transactions: list[dict]) -> list[str]:
    """
    Analyze transactions to find recurring charges using a heuristic:
      - Same merchant_name appearing 2+ times
      - Similar amounts (within 5%)
      - At regular intervals (weekly, bi-weekly, monthly, or quarterly)

    Returns a list of transaction IDs (as strings) that are likely recurring.
    Falls back to heuristic-only if the AI call fails.
    """
    if not transactions:
        return []

    by_merchant: dict[str, list[dict]] = defaultdict(list)
    for txn in transactions:
        key = (txn.get("merchant_name") or "").strip().lower()
        if key:
            by_merchant[key].append(txn)

    candidate_ids: set[str] = set()

    for merchant, txns in by_merchant.items():
        if len(txns) < 2:
            continue

        def _to_date(t: dict) -> date:
            val = t.get("transaction_date")
            if isinstance(val, date):
                return val
            try:
                return date.fromisoformat(str(val))
            except Exception:
                return date.min

        txns_sorted = sorted(txns, key=_to_date)
        amounts = [float(t.get("amount", 0)) for t in txns_sorted]

        if len(amounts) >= 2:
            mean_amount = sum(amounts) / len(amounts)
            if mean_amount == 0:
                continue
            if all(abs(a - mean_amount) / abs(mean_amount) <= 0.05 for a in amounts):
                dates = [_to_date(t) for t in txns_sorted]
                intervals = [
                    (dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)
                ]
                if intervals:
                    mean_interval = sum(intervals) / len(intervals)
                    is_regular = (
                        (6 <= mean_interval <= 8)
                        or (13 <= mean_interval <= 15)
                        or (25 <= mean_interval <= 35)
                        or (85 <= mean_interval <= 95)
                    ) and all(abs(iv - mean_interval) <= 5 for iv in intervals)
                    if is_regular:
                        for t in txns_sorted:
                            tid = t.get("id")
                            if tid:
                                candidate_ids.add(str(tid))

    if candidate_ids and len(transactions) <= 200:
        txn_text = json.dumps(
            [
                {
                    "id": str(t.get("id", "")),
                    "merchant_name": t.get("merchant_name", ""),
                    "amount": str(t.get("amount", "")),
                    "transaction_date": str(t.get("transaction_date", "")),
                }
                for t in transactions
            ],
            indent=2,
        )

        prompt = f"""Analyze the following transactions and identify which ones are recurring charges
(subscriptions, utilities, memberships, loan payments, etc.).

Transactions:
{txn_text}

Respond ONLY with a JSON array of transaction IDs (strings) that are recurring.
Example: ["uuid-1", "uuid-2"]
Do not include any explanation. Output raw JSON only."""

        try:
            raw = await asyncio.to_thread(_call_gemini, prompt)
            raw = _strip_fences(raw)
            ai_ids = json.loads(raw)
            if isinstance(ai_ids, list):
                candidate_ids.update(str(i) for i in ai_ids)
        except Exception:
            logger.exception("AI recurring detection failed")

    return list(candidate_ids)
