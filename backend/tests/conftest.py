"""
Shared test fixtures.

DB-backed tests run against a *throwaway* Postgres (docker-compose.test.yml),
never Supabase. SQLite is deliberately not an option: the budget lifecycle
relies on Postgres-only features (pg_advisory_xact_lock, the uq_sbe_settlement
partial unique index, UPDATE ... RETURNING), so the schema is built by running
the real Alembic migrations — not Base.metadata.create_all, which would omit
the raw-SQL index that backs settle-once idempotency.

Start the DB before running:  docker compose -f docker-compose.test.yml up -d
Override the URL with the TEST_DATABASE_URL env var if your DB lives elsewhere.

Each DB test gets a session wrapped in a transaction that is rolled back on
teardown, so tests are isolated and order-independent. The lifecycle code only
flushes (never commits), so a single outer transaction cleanly contains it.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parent.parent

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/expense_test",
)


def _skip_if_no_db():
    return pytest.mark.skip(reason="test Postgres unavailable")


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_db():
    """Build the schema once per session by running `alembic upgrade head`
    against the test DB. Idempotent: a no-op if the DB is already at head."""
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(
            "Could not migrate test DB (is docker-compose.test.yml up?).\n"
            f"alembic stderr:\n{result.stderr}"
        )
    yield


@pytest_asyncio.fixture
async def db_session(_migrate_test_db) -> AsyncSession:
    """A session bound to an open transaction that is rolled back on teardown.

    A fresh NullPool engine per test sidesteps asyncpg's cross-event-loop
    pooling issues with pytest-asyncio's function-scoped loops.
    """
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    try:
        conn = await engine.connect()
    except OperationalError:
        await engine.dispose()
        pytest.skip("test Postgres not reachable (docker compose up?)")
    trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        # A test that triggers an IntegrityError leaves the DB transaction
        # already aborted; only roll back if it's still live to avoid a noisy
        # "transaction already deassociated" warning.
        if conn.in_transaction():
            await trans.rollback()
        await conn.close()
        await engine.dispose()


# ---------------------------------------------------------------------------
# Model factories — minimal valid rows, override any field via kwargs.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
def make_account(db_session):
    from app.models.account import Account

    async def _make(name="Test Checking", type="checking", institution="Test Bank", **kw):
        acct = Account(id=uuid.uuid4(), name=name, type=type, institution=institution, **kw)
        db_session.add(acct)
        await db_session.flush()
        return acct

    return _make


@pytest_asyncio.fixture
def make_category(db_session):
    from app.models.category import Category

    async def _make(name="Food", color="#4A90E2", **kw):
        cat = Category(id=uuid.uuid4(), name=name, color=color, **kw)
        db_session.add(cat)
        await db_session.flush()
        return cat

    return _make


@pytest_asyncio.fixture
def make_subcategory(db_session):
    from app.models.subcategory import Subcategory

    async def _make(category, name="Dining Out", **kw):
        sub = Subcategory(id=uuid.uuid4(), category_id=category.id, name=name, **kw)
        db_session.add(sub)
        await db_session.flush()
        return sub

    return _make


@pytest_asyncio.fixture
def make_budget(db_session):
    from app.models.budget import Budget

    async def _make(category, subcategory, month, year, amount, locked=False, **kw):
        b = Budget(
            id=uuid.uuid4(),
            category_id=category.id,
            subcategory_id=subcategory.id,
            month=month,
            year=year,
            amount=amount,
            locked=locked,
            **kw,
        )
        db_session.add(b)
        await db_session.flush()
        return b

    return _make


@pytest_asyncio.fixture
def make_budget_month(db_session):
    from app.models.budget_month import BudgetMonth

    async def _make(month, year, **kw):
        bm = BudgetMonth(id=uuid.uuid4(), month=month, year=year, **kw)
        db_session.add(bm)
        await db_session.flush()
        return bm

    return _make


@pytest_asyncio.fixture
def make_transaction(db_session):
    from datetime import date

    from app.models.transaction import Transaction

    async def _make(account, subcategory, when, amount, category=None, budget_excluded=False, **kw):
        txn = Transaction(
            id=uuid.uuid4(),
            account_id=account.id,
            category_id=(category.id if category else subcategory.category_id),
            subcategory_id=subcategory.id,
            transaction_date=when if isinstance(when, date) else date.fromisoformat(when),
            raw_description=kw.pop("raw_description", "Test txn"),
            merchant_name=kw.pop("merchant_name", "Test Merchant"),
            amount=amount,
            budget_excluded=budget_excluded,
            **kw,
        )
        db_session.add(txn)
        await db_session.flush()
        return txn

    return _make
