from decimal import Decimal

from pydantic import BaseModel

from app.schemas.transaction import TransactionOut


class DashboardSummary(BaseModel):
    income: Decimal       # this month's Income-category transactions (receipts)
    budget: Decimal       # last month's income × pool_pct
    spent: Decimal        # non-excluded expense spending this month
    remaining: Decimal    # budget − spent
    investments: Decimal  # Investments-category spending this month
    savings: Decimal      # income − investments − spent


class DashboardSubcategoryRow(BaseModel):
    subcategory_id: str
    subcategory_name: str
    budget: Decimal
    spent: Decimal
    remaining: Decimal
    status: str  # "green", "yellow", "red"


class DashboardCategoryRow(BaseModel):
    category_id: str
    category_name: str
    category_color: str
    budget: Decimal
    spent: Decimal
    remaining: Decimal
    status: str  # "green", "yellow", "red"
    subcategories: list[DashboardSubcategoryRow] = []


class DashboardResponse(BaseModel):
    month: int
    year: int
    summary: DashboardSummary
    rows: list[DashboardCategoryRow]
    total_budget: Decimal
    total_spent: Decimal


class TrendPoint(BaseModel):
    month: int
    year: int
    total_spent: Decimal


class TrendResponse(BaseModel):
    points: list[TrendPoint]


class TopMerchantRow(BaseModel):
    merchant_name: str
    total_spent: Decimal
    transaction_count: int


class YTDMonthEntry(BaseModel):
    month: int
    budget: Decimal
    spent: Decimal


class YTDCategoryRow(BaseModel):
    category_id: str
    category_name: str
    months: list[YTDMonthEntry]


class YTDResponse(BaseModel):
    year: int
    categories: list[YTDCategoryRow]


RecurringTransaction = TransactionOut
