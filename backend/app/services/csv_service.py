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


def _venmo_account_holder(rows: list[list[str]]) -> str:
    """Extract account holder name from 'Account Statement - (@Handle)' header row."""
    if not rows or not rows[0]:
        return ""
    first_cell = str(rows[0][0]).strip()
    m = re.search(r"@([^)]+)", first_cell)
    if m:
        return m.group(1).strip().replace("-", " ")
    return ""


def _venmo_other_person(from_name: str, to_name: str, account_holder: str) -> str:
    """Return whichever of from/to is not the account holder (word-overlap fallback)."""
    holder_norm = account_holder.strip().lower()
    if from_name.strip().lower() == holder_norm:
        return to_name.strip()
    if to_name.strip().lower() == holder_norm:
        return from_name.strip()
    holder_words = set(holder_norm.split())
    from_overlap = len(set(from_name.strip().lower().split()) & holder_words)
    to_overlap = len(set(to_name.strip().lower().split()) & holder_words)
    return to_name.strip() if from_overlap >= to_overlap else from_name.strip()


def parse_venmo_csv(file_bytes: bytes, filename: str = "venmo.csv") -> list[dict]:
    """Parse a Venmo statement CSV export into transaction dicts."""
    content = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)

    account_holder = _venmo_account_holder(rows)

    header_row_idx: int | None = None
    header_norm: list[str] = []
    for i, row in enumerate(rows):
        norm = [c.strip().lower() for c in row]
        if "id" in norm and "datetime" in norm and "from" in norm and "to" in norm:
            header_row_idx = i
            header_norm = norm
            break

    if header_row_idx is None:
        raise ValueError(
            "Could not find Venmo CSV header row (expected ID, Datetime, From, To columns)."
        )

    def _col(name: str) -> int | None:
        return header_norm.index(name) if name in header_norm else None

    id_idx = _col("id")
    dt_idx = _col("datetime")
    note_idx = _col("note")
    from_idx = _col("from")
    to_idx = _col("to")
    status_idx = _col("status")
    funding_source_idx = _col("funding source")
    destination_idx = _col("destination")
    amount_idx = next(
        (i for i, h in enumerate(header_norm) if "amount" in h and "total" in h), None
    )

    if id_idx is None or dt_idx is None or from_idx is None or to_idx is None:
        raise ValueError("Venmo CSV is missing required columns (ID, Datetime, From, To).")
    if amount_idx is None:
        raise ValueError("Could not find 'Amount (total)' column in Venmo CSV.")

    transactions: list[dict] = []
    for row in rows[header_row_idx + 1:]:
        row = [str(c) for c in row]
        needed = max(id_idx, dt_idx, from_idx, to_idx, amount_idx)
        if len(row) <= needed:
            continue

        txn_id = row[id_idx].strip()
        if not txn_id or txn_id.lower() == "nan":
            continue

        raw_dt = row[dt_idx].strip()
        if not raw_dt:
            continue

        if status_idx is not None and status_idx < len(row):
            if row[status_idx].strip().lower() not in ("complete", ""):
                continue

        try:
            txn_date = _parse_date(raw_dt)
        except ValueError:
            continue

        note = (row[note_idx].strip() if note_idx is not None and note_idx < len(row) else "") or ""
        from_name = row[from_idx].strip() if from_idx < len(row) else ""
        to_name = row[to_idx].strip() if to_idx < len(row) else ""

        amount_raw = row[amount_idx].strip() if amount_idx < len(row) else ""
        if not amount_raw:
            continue
        # Venmo sign convention is inverted vs app convention:
        # Venmo "+" = money received (income) → app negative; "–" = money sent (expense) → app positive
        amount = -_parse_amount(amount_raw)

        merchant_name = (
            _venmo_other_person(from_name, to_name, account_holder)
            if account_holder
            else (to_name or from_name)
        )

        funding_source = (
            row[funding_source_idx].strip()
            if funding_source_idx is not None and funding_source_idx < len(row)
            else ""
        )
        destination = (
            row[destination_idx].strip()
            if destination_idx is not None and destination_idx < len(row)
            else ""
        )
        # If funding source or destination is a real bank account (not Venmo balance),
        # this transaction also appears on the linked bank/card statement.
        is_bank_transfer = (
            (bool(funding_source) and funding_source.lower() != "venmo balance") or
            (bool(destination) and destination.lower() != "venmo balance")
        )

        transactions.append(
            {
                "raw_description": note or merchant_name,
                "merchant_name": merchant_name or note or txn_id,
                "amount": amount,
                "transaction_date": txn_date,
                "import_source": filename,
                "external_reference": txn_id,
                "is_venmo_bank_transfer": is_bank_transfer,
            }
        )

    return transactions


def parse_file(file_bytes: bytes, filename: str, account_type: str | None = None) -> list[dict]:
    """
    Auto-detect file type from extension and parse accordingly.
    Supports .csv, .xlsx, .xls. Venmo accounts use a dedicated parser.
    """
    if account_type and account_type.lower() == "venmo":
        return parse_venmo_csv(file_bytes, filename)
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in ("xlsx", "xls"):
        return parse_excel(file_bytes, filename)
    return parse_csv(file_bytes, filename)
