"""
Flexible multi-format parser for bank/credit-card export files.
Supports CSV (.csv) and Excel (.xlsx, .xls) formats.
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd


# ---------------------------------------------------------------------------
# Column-name candidates
# ---------------------------------------------------------------------------

DATE_CANDIDATES = [
    "date",
    "transaction date",
    "posted date",
    "trans date",
    "posting date",
    "settlement date",
    "value date",
]

DESCRIPTION_CANDIDATES = [
    "description",
    "merchant",
    "memo",
    "payee",
    "transaction description",
    "details",
    "narrative",
    "particulars",
    "reference",
]

AMOUNT_CANDIDATES = [
    "amount",
    "transaction amount",
    "net amount",
]

DEBIT_CANDIDATES = [
    "debit",
    "debit amount",
    "withdrawals",
    "withdrawal",
    "charge",
]

CREDIT_CANDIDATES = [
    "credit",
    "credit amount",
    "deposits",
    "deposit",
    "payment",
]

MERCHANT_CANDIDATES = [
    "merchant name",
    "merchant",
    "vendor",
]

REFERENCE_CANDIDATES = [
    "reference",
    "ref",
    "transaction id",
    "transaction ref",
    "check number",
    "cheque number",
    "confirmation",
    "confirmation number",
]

# ---------------------------------------------------------------------------
# Date-format patterns
# ---------------------------------------------------------------------------

DATE_FORMATS = [
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%m-%d-%Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%b %d %Y",
    "%B %d %Y",
    "%m/%d/%y",
    "%d/%m/%y",
    "%Y/%m/%d",
]


def _normalize_header(header: str) -> str:
    return str(header).strip().lower()


def _find_column(headers_normalized: list[str], candidates: list[str]) -> int | None:
    for idx, h in enumerate(headers_normalized):
        if h in candidates:
            return idx
    return None


def _looks_like_date_str(val: str) -> bool:
    """Return True if val parses as a date under any of our known formats."""
    val = val.strip().strip('"').split(" ")[0].split("T")[0]
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(val, fmt)
            return True
        except ValueError:
            continue
    return False


def _looks_like_amount_str(val: str) -> bool:
    """Return True if val looks like a numeric amount (possibly with sign/currency symbols)."""
    val = val.strip().strip('"')
    if val in ("", "nan", "NaN", "None", "*", "-"):
        return False
    clean = re.sub(r"[^\d.\-]", "", val)
    if not clean or clean == ".":
        return False
    try:
        Decimal(clean)
        return True
    except InvalidOperation:
        return False


def _detect_columns_positionally(
    rows: list[list[str]],
) -> dict | None:
    """
    Heuristic positional column detection for headerless bank exports.
    Scans sample rows to identify date, amount, and description columns by
    their data patterns. Returns a dict with keys:
        date_idx, amount_idx, desc_idx, sign_flip
    or None if no reliable mapping can be found.
    """
    if not rows:
        return None

    n_cols = max((len(r) for r in rows), default=0)
    if n_cols == 0:
        return None

    # Sample up to 10 rows for detection
    sample = rows[:min(10, len(rows))]

    date_idx: int | None = None
    amount_idx: int | None = None

    # Scan each column for date-like or amount-like values
    for col in range(n_cols):
        vals = [str(r[col]).strip().strip('"') for r in sample if col < len(r)]
        vals = [v for v in vals if v and v.lower() not in ("nan", "")]
        if not vals:
            continue

        date_hits = sum(1 for v in vals if _looks_like_date_str(v))
        amount_hits = sum(1 for v in vals if _looks_like_amount_str(v))

        threshold = len(vals) * 0.7
        if date_hits >= threshold and date_idx is None:
            date_idx = col
        elif amount_hits >= threshold and amount_idx is None and col != date_idx:
            amount_idx = col

    if date_idx is None or amount_idx is None:
        return None

    # Description: column with the longest average text that isn't date or amount
    desc_idx: int | None = None
    max_avg_len = 0.0
    for col in range(n_cols):
        if col in (date_idx, amount_idx):
            continue
        vals = [str(r[col]).strip().strip('"') for r in sample if col < len(r)]
        vals = [v for v in vals if v and v.lower() not in ("nan", "", "*")]
        if vals:
            avg = sum(len(v) for v in vals) / len(vals)
            if avg > max_avg_len:
                max_avg_len = avg
                desc_idx = col

    if desc_idx is None:
        return None

    # Detect sign convention: if majority of non-zero amounts are negative,
    # the file uses negative-for-expense; flip signs to match app convention.
    sign_flip = False
    all_vals = [str(r[amount_idx]).strip().strip('"') for r in rows if amount_idx < len(r)]
    parsed_amounts = []
    for v in all_vals:
        clean = re.sub(r"[^\d.\-]", "", v)
        if clean and clean not in ("", "-", "."):
            try:
                parsed_amounts.append(Decimal(clean))
            except InvalidOperation:
                pass
    nonzero = [a for a in parsed_amounts if a != 0]
    if nonzero and sum(1 for a in nonzero if a < 0) > len(nonzero) * 0.5:
        sign_flip = True

    return {
        "date_idx": date_idx,
        "amount_idx": amount_idx,
        "desc_idx": desc_idx,
        "sign_flip": sign_flip,
    }


def _parse_date(raw: str) -> date:
    raw = str(raw).strip()
    # pandas may return a datetime string like "2024-01-15 00:00:00"
    raw = raw.split(" ")[0].split("T")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {raw!r}")


def _parse_amount(raw: str) -> Decimal:
    raw = str(raw).strip()
    if raw in ("", "nan", "NaN", "None"):
        return Decimal("0")
    negative = False
    if raw.startswith("(") and raw.endswith(")"):
        negative = True
        raw = raw[1:-1]
    raw = re.sub(r"[^\d.\-]", "", raw)
    if not raw or raw == "-":
        return Decimal("0")
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return Decimal("0")
    return -amount if negative else amount


def _row_is_header(row: list[str]) -> bool:
    """
    Return True if this row looks like the actual transaction header row.
    We require it to contain at least one date-like column AND at least one
    description-like or amount-like column from our known candidate lists.
    """
    norm = [_normalize_header(c) for c in row]
    norm_set = set(norm)
    has_date = any(c in norm_set for c in DATE_CANDIDATES)
    has_desc = any(c in norm_set for c in DESCRIPTION_CANDIDATES)
    has_amount = any(
        c in norm_set
        for c in AMOUNT_CANDIDATES + DEBIT_CANDIDATES + CREDIT_CANDIDATES
    )
    return has_date and (has_desc or has_amount)


def _rows_to_transactions(rows: list[list[str]], filename: str) -> list[dict]:
    """
    Core parsing logic shared by CSV and Excel paths.
    Accepts a list of rows (each row is a list of string values).
    Returns parsed transaction dicts.
    """
    # Find header row: prefer a row whose cells match our known column candidates.
    # Fall back to the first row with >= 2 non-empty cells if no match found.
    header_row_idx: int | None = None
    headers_raw: list[str] = []

    # First pass: look for a row that semantically matches our column lists.
    for i, row in enumerate(rows):
        str_row = [str(c) for c in row]
        non_empty = [c for c in str_row if c.strip() and c.strip().lower() != "nan"]
        if len(non_empty) >= 2 and _row_is_header(str_row):
            header_row_idx = i
            headers_raw = str_row
            break

    # Second pass (fallback): first row with >= 2 non-empty cells.
    if header_row_idx is None:
        for i, row in enumerate(rows):
            str_row = [str(c) for c in row]
            non_empty = [c for c in str_row if c.strip() and c.strip().lower() != "nan"]
            if len(non_empty) >= 2:
                header_row_idx = i
                headers_raw = str_row
                break

    if not headers_raw or header_row_idx is None:
        raise ValueError("File appears to be empty or has no readable headers.")

    headers_norm = [_normalize_header(h) for h in headers_raw]

    date_idx = _find_column(headers_norm, DATE_CANDIDATES)
    desc_idx = _find_column(headers_norm, DESCRIPTION_CANDIDATES)
    amount_idx = _find_column(headers_norm, AMOUNT_CANDIDATES)
    debit_idx = _find_column(headers_norm, DEBIT_CANDIDATES)
    credit_idx = _find_column(headers_norm, CREDIT_CANDIDATES)
    merchant_idx = _find_column(headers_norm, MERCHANT_CANDIDATES)
    reference_idx = _find_column(headers_norm, REFERENCE_CANDIDATES)

    # If semantic detection failed, try positional heuristics on all rows.
    # This handles headerless bank exports (e.g. Wells Fargo checking).
    sign_flip = False
    if date_idx is None or desc_idx is None:
        positional = _detect_columns_positionally(rows)
        if positional and positional.get("date_idx") is not None and positional.get("desc_idx") is not None:
            header_row_idx = -1          # treat ALL rows as data (no header row)
            date_idx = positional["date_idx"]
            desc_idx = positional["desc_idx"]
            if amount_idx is None:
                amount_idx = positional.get("amount_idx")
            debit_idx = None
            credit_idx = None
            merchant_idx = None
            reference_idx = None
            sign_flip = positional.get("sign_flip", False)

    if date_idx is None:
        raise ValueError(
            f"Cannot detect date column. Headers found: {headers_raw}. "
            f"Expected one of: {DATE_CANDIDATES}"
        )
    if desc_idx is None:
        raise ValueError(
            f"Cannot detect description column. Headers found: {headers_raw}. "
            f"Expected one of: {DESCRIPTION_CANDIDATES}"
        )

    has_single_amount = amount_idx is not None
    has_split_amount = debit_idx is not None or credit_idx is not None

    if not has_single_amount and not has_split_amount:
        raise ValueError(
            f"Cannot detect amount column. Headers found: {headers_raw}. "
            f"Expected one of: {AMOUNT_CANDIDATES + DEBIT_CANDIDATES + CREDIT_CANDIDATES}"
        )

    transactions: list[dict] = []
    data_rows = rows[header_row_idx + 1:]
    max_idx = max(
        date_idx,
        desc_idx,
        amount_idx if amount_idx is not None else 0,
        debit_idx if debit_idx is not None else 0,
        credit_idx if credit_idx is not None else 0,
    )

    for row in data_rows:
        row = [str(c) for c in row]
        if not any(c.strip() and c.strip().lower() != "nan" for c in row):
            continue
        while len(row) <= max_idx:
            row.append("")

        raw_date = row[date_idx].strip()
        if not raw_date or raw_date.lower() == "nan":
            continue

        try:
            txn_date = _parse_date(raw_date)
        except ValueError:
            continue

        raw_description = row[desc_idx].strip()

        if has_single_amount:
            raw_amount = row[amount_idx].strip() if amount_idx is not None else "0"
            amount = _parse_amount(raw_amount)
            # Headerless exports (e.g. Wells Fargo) use negative-for-expense;
            # flip sign so positive = expense to match app convention.
            if sign_flip:
                amount = -amount
        else:
            debit_raw = row[debit_idx].strip() if debit_idx is not None else ""
            credit_raw = row[credit_idx].strip() if credit_idx is not None else ""
            debit = _parse_amount(debit_raw) if debit_raw else Decimal("0")
            credit = _parse_amount(credit_raw) if credit_raw else Decimal("0")
            amount = debit - credit

        merchant_name = ""
        if merchant_idx is not None and merchant_idx < len(row):
            merchant_name = row[merchant_idx].strip()

        # Extract reference and strip surrounding single-quotes (common in bank exports)
        external_reference: str | None = None
        if reference_idx is not None and reference_idx < len(row):
            ref_raw = row[reference_idx].strip()
            if ref_raw and ref_raw.lower() != "nan":
                external_reference = ref_raw.strip("'").strip()

        transactions.append(
            {
                "raw_description": raw_description,
                "merchant_name": merchant_name or raw_description,
                "amount": amount,
                "transaction_date": txn_date,
                "import_source": filename,
                "external_reference": external_reference,
            }
        )

    return transactions


def parse_csv(file_bytes: bytes, filename: str = "upload.csv") -> list[dict]:
    """Parse a CSV file and return transaction dicts."""
    content = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    return _rows_to_transactions(rows, filename)


def parse_excel(file_bytes: bytes, filename: str = "upload.xlsx") -> list[dict]:
    """
    Parse an Excel file (.xlsx or .xls) and return transaction dicts.
    Uses the first sheet. Tries to auto-detect the header row.
    """
    # Read all rows as strings, no header inference by pandas
    df = pd.read_excel(
        io.BytesIO(file_bytes),
        sheet_name=0,
        header=None,
        dtype=str,
    )
    # Replace pandas NaN with empty string
    df = df.fillna("")
    rows = df.values.tolist()
    return _rows_to_transactions(rows, filename)


def parse_file(file_bytes: bytes, filename: str) -> list[dict]:
    """
    Auto-detect file type from extension and parse accordingly.
    Supports .csv, .xlsx, .xls.
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in ("xlsx", "xls"):
        return parse_excel(file_bytes, filename)
    return parse_csv(file_bytes, filename)
