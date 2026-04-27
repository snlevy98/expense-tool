"""
AI service — three tasks, three providers, three separate free-tier rate-limit pools:

  Merchant normalization  →  Google Gemini  (gemini-2.5-flash)
  Category suggestion     →  Groq           (llama-3.3-70b-versatile)
  Recurring detection     →  Cohere         (command-r7b-12-2024)

Each provider falls back to Gemini if its API key is not configured.
RateLimitError is raised on 429/503 so the /enrich endpoint can return HTTP 503
and the frontend can retry with backoff.
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import date

import cohere
import google.genai as genai
from groq import AsyncGroq

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

_gemini = genai.Client(api_key=settings.GEMINI_API_KEY)
_GEMINI_MODEL = "gemini-2.5-flash"

_groq = AsyncGroq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None
_GROQ_MODEL = "llama-3.3-70b-versatile"

_cohere = cohere.AsyncClientV2(api_key=settings.COHERE_API_KEY) if settings.COHERE_API_KEY else None
_COHERE_MODEL = "command-r7b-12-2024"

_NORMALIZE_CHUNK = 40
_SUGGEST_CHUNK   = 50


# ---------------------------------------------------------------------------
# Rate-limit sentinel
# ---------------------------------------------------------------------------

class RateLimitError(Exception):
    """Provider returned 429 or 503 — caller should retry with backoff."""


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(s in msg for s in ("429", "503", "rate_limit", "rate limit",
                                   "resource_exhausted", "unavailable",
                                   "too many requests", "toomanyrequests"))


# ---------------------------------------------------------------------------
# Per-provider callers
# ---------------------------------------------------------------------------

_RETRY_DELAYS = (5, 15, 30)   # seconds between server-side retries before giving up


async def _call_gemini(prompt: str) -> str:
    """Merchant normalization provider. Retries up to 3× on rate limit before raising."""
    last_exc: Exception | None = None
    for attempt, delay in enumerate((0, *_RETRY_DELAYS)):
        if delay:
            logger.warning("Gemini rate-limited — retrying in %ds (attempt %d)", delay, attempt + 1)
            await asyncio.sleep(delay)
        try:
            resp = await _gemini.aio.models.generate_content(model=_GEMINI_MODEL, contents=prompt)
            return resp.text.strip()
        except Exception as exc:
            if _is_rate_limit(exc):
                last_exc = exc
                continue
            raise
    raise RateLimitError(str(last_exc)) from last_exc


async def _call_groq(prompt: str) -> str:
    """Category suggestion provider. Falls back to Gemini if key not configured.
    Retries up to 3× on rate limit before raising."""
    if not _groq:
        return await _call_gemini(prompt)
    last_exc: Exception | None = None
    for attempt, delay in enumerate((0, *_RETRY_DELAYS)):
        if delay:
            logger.warning("Groq rate-limited — retrying in %ds (attempt %d)", delay, attempt + 1)
            await asyncio.sleep(delay)
        try:
            resp = await _groq.chat.completions.create(
                model=_GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            if _is_rate_limit(exc):
                last_exc = exc
                continue
            raise
    raise RateLimitError(str(last_exc)) from last_exc


async def _call_cohere(prompt: str) -> str:
    """Recurring detection provider. Falls back to Gemini if key not configured."""
    if not _cohere:
        return await _call_gemini(prompt)
    try:
        resp = await _cohere.chat(
            model=_COHERE_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.message.content[0].text.strip()
    except Exception as exc:
        if _is_rate_limit(exc):
            raise RateLimitError(str(exc)) from exc
        raise


def _strip_fences(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


# ---------------------------------------------------------------------------
# Merchant name normalization  (Gemini)
# ---------------------------------------------------------------------------

async def _normalize_chunk(descriptions: list[str]) -> list[str]:
    """Normalize one chunk. Propagates RateLimitError; returns originals on other failures."""
    numbered = "\n".join(f"{i}. {d}" for i, d in enumerate(descriptions))
    prompt = f"""Convert each bank transaction description below to a clean, human-readable merchant name.
Return ONLY a JSON array of strings in the same order.
Each string should be just the merchant name — no explanation, no extra punctuation.

Descriptions:
{numbered}

Respond with a JSON array only, like: ["Merchant A", "Merchant B", ...]
Do not include markdown fences or explanations."""

    try:
        raw = await _call_gemini(prompt)
        raw = _strip_fences(raw)
        names = json.loads(raw)
        if isinstance(names, list) and len(names) == len(descriptions):
            return [str(n).strip() or descriptions[i] for i, n in enumerate(names)]
        logger.warning(
            "Merchant normalization: got %d names for %d descriptions — using originals",
            len(names) if isinstance(names, list) else -1,
            len(descriptions),
        )
        return descriptions
    except RateLimitError:
        raise
    except Exception:
        logger.exception("Merchant normalization chunk failed")
        return descriptions


async def normalize_merchant_names_batch(descriptions: list[str]) -> list[str]:
    if not descriptions:
        return []
    results: list[str] = []
    for start in range(0, len(descriptions), _NORMALIZE_CHUNK):
        results.extend(await _normalize_chunk(descriptions[start : start + _NORMALIZE_CHUNK]))
    return results


# ---------------------------------------------------------------------------
# Category suggestion  (Groq)
# ---------------------------------------------------------------------------

async def _suggest_categories_chunk(
    transactions: list[dict], categories: list[dict], index_offset: int,
    examples_text: str = "",
) -> list[dict]:
    """Suggest categories for one chunk. Propagates RateLimitError; returns [] on other failures."""
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
                # Use the transaction's own index if set (preserves real indices across
                # frontend batches); fall back to offset+i for internal chunking.
                "index": t.get("index") if t.get("index") is not None else index_offset + i,
                "merchant_name": t.get("merchant_name", t.get("raw_description", "")),
                "raw_description": t.get("raw_description", ""),
                "amount": str(t.get("amount", "")),
            }
            for i, t in enumerate(transactions)
        ],
        indent=2,
    )

    examples_section = (
        f"Learn from this user's past categorizations and follow these patterns "
        f"when you see the same or similar merchants:\n{examples_text}\n\n"
        if examples_text else ""
    )

    prompt = f"""You are a financial categorization assistant.

{examples_section}Given the following expense categories and subcategories:
{cat_text}

And the following transactions:
{txn_text}

For EACH transaction, pick the single best-matching category_id and subcategory_id.
Rules:
- If a transaction matches a merchant from the past examples above, use that same category
- ALWAYS assign a category_id — NEVER return null for category_id. Every transaction can be categorized; pick the closest match even if you are uncertain
- The only exception is a payment to yourself or a pure inter-account transfer with no merchant — those may use null
- Use null for subcategory_id only if no subcategory fits the chosen category
- Negative amounts are usually refunds or credits — assign a credits/income category if one exists, otherwise the category that fits the original charge type
- Amazon, online retailers, streaming services, restaurants, cafes, and subscription charges always have a matching category — do not return null for these

Respond with a JSON object in exactly this shape:
{{"suggestions": [
  {{"index": <integer>, "category_id": "<UUID string>", "subcategory_id": "<UUID string or null>"}},
  ...
]}}

Output raw JSON only — no explanation, no markdown."""

    try:
        raw = await _call_groq(prompt)
        raw = _strip_fences(raw)
        parsed = json.loads(raw)
        # Primary: explicit {"suggestions": [...]} shape we requested
        if isinstance(parsed, dict):
            if "suggestions" in parsed and isinstance(parsed["suggestions"], list):
                suggestions = parsed["suggestions"]
            else:
                # Fallback: first list value (e.g. {"results": [...]})
                suggestions = next((v for v in parsed.values() if isinstance(v, list)), None)
                if suggestions is None:
                    # Last resort: dict-of-dicts keyed by index str {"0": {...}, "1": {...}}
                    candidates = list(parsed.values())
                    if candidates and isinstance(candidates[0], dict) and "index" in candidates[0]:
                        suggestions = candidates
                    else:
                        logger.warning(
                            "Category suggestion: unrecognised dict shape (offset=%d): %s",
                            index_offset, list(parsed.keys())[:5],
                        )
                        return []
        else:
            suggestions = parsed
        if not isinstance(suggestions, list):
            logger.warning("Category suggestion returned non-list (offset=%d)", index_offset)
            return []
        return suggestions
    except RateLimitError:
        raise
    except Exception:
        logger.exception("Category suggestion chunk (offset=%d) failed", index_offset)
        return []


async def suggest_categories(
    transactions: list[dict], categories: list[dict], examples_text: str = ""
) -> list[dict]:
    if not transactions or not categories:
        return []
    results: list[dict] = []
    for start in range(0, len(transactions), _SUGGEST_CHUNK):
        results.extend(
            await _suggest_categories_chunk(
                transactions[start : start + _SUGGEST_CHUNK],
                categories,
                index_offset=start,
                examples_text=examples_text,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Recurring detection  (Cohere)
# ---------------------------------------------------------------------------

async def detect_recurring(transactions: list[dict]) -> list[str]:
    """
    Heuristic first-pass, then Cohere confirms / expands.
    Returns a list of transaction IDs (strings) that are likely recurring.
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
                intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
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
                            if t.get("id"):
                                candidate_ids.add(str(t["id"]))

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
            raw = await _call_cohere(prompt)
            raw = _strip_fences(raw)
            ai_ids = json.loads(raw)
            if isinstance(ai_ids, list):
                candidate_ids.update(str(i) for i in ai_ids)
        except Exception:
            logger.exception("AI recurring detection failed")

    return list(candidate_ids)
