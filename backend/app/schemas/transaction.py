import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    category_id: uuid.UUID | None
    subcategory_id: uuid.UUID | None
    transaction_date: date
    raw_description: str
    merchant_name: str
    amount: Decimal
    ai_suggested_category_id: uuid.UUID | None
    ai_suggested_subcategory_id: uuid.UUID | None
    is_recurring: bool
    import_source: str
    import_batch_id: uuid.UUID | None
    external_reference: str | None = None
    created_at: datetime
    updated_at: datetime

    # Joined names
    category_name: str | None = None
    subcategory_name: str | None = None
    account_name: str | None = None


class TransactionUpdate(BaseModel):
    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None
    merchant_name: str | None = None
    raw_description: str | None = None
    amount: Decimal | None = None
    transaction_date: date | None = None


class ImportPreviewItem(BaseModel):
    index: int
    raw_description: str
    merchant_name: str
    amount: Decimal
    transaction_date: date
    import_source: str
    external_reference: str | None = None
    ai_suggested_category_id: uuid.UUID | None = None
    ai_suggested_subcategory_id: uuid.UUID | None = None
    matched_transaction_id: uuid.UUID | None = None


class VenmoUnmatchedItem(BaseModel):
    transaction_date: date
    amount: Decimal
    merchant_name: str
    raw_description: str


class ImportPreviewResponse(BaseModel):
    transactions: list[ImportPreviewItem]
    duplicates_skipped: int = 0
    venmo_unmatched: list[VenmoUnmatchedItem] = []


class ImportConfirmItem(BaseModel):
    raw_description: str
    merchant_name: str
    amount: Decimal
    transaction_date: date
    import_source: str
    account_id: uuid.UUID
    external_reference: str | None = None
    category_id: uuid.UUID | None = None
    subcategory_id: uuid.UUID | None = None
    ai_suggested_category_id: uuid.UUID | None = None
    ai_suggested_subcategory_id: uuid.UUID | None = None
    ai_enriched: bool = False  # frontend sets True for rows that went through /enrich
    matched_transaction_id: uuid.UUID | None = None  # set for Venmo→bank matches


class ImportConfirmRequest(BaseModel):
    transactions: list[ImportConfirmItem]


class PaginatedTransactions(BaseModel):
    items: list[TransactionOut]
    total: int


class EnrichItem(BaseModel):
    index: int
    raw_description: str
    merchant_name: str
    amount: Decimal


class EnrichRequest(BaseModel):
    transactions: list[EnrichItem]
    account_type: str | None = None


class EnrichResult(BaseModel):
    index: int
    merchant_name: str
    ai_suggested_category_id: uuid.UUID | None = None
    ai_suggested_subcategory_id: uuid.UUID | None = None


class EnrichResponse(BaseModel):
    results: list[EnrichResult]


class EnrichPendingResponse(BaseModel):
    queued: int
    message: str


class EnrichStatusResponse(BaseModel):
    running: bool
    processed: int
    total: int
