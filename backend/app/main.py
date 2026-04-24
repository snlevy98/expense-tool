"""
FastAPI application entry point for the Household Expense Tracker API.
"""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.jobs.recurring_detection import run_recurring_detection
from app.routers import accounts, amazon, budgets, categories, import_csv, reports, subcategories, transactions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup ----
    logger.info("Starting expense-tracker API (env=%s)", settings.ENVIRONMENT)

    # Schedule the nightly recurring-detection job at 02:00 server time
    scheduler.add_job(
        run_recurring_detection,
        trigger=CronTrigger(hour=2, minute=0),
        id="recurring_detection",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("APScheduler started.")

    yield

    # ---- Shutdown ----
    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped.")


app = FastAPI(
    title="Household Expense Tracker API",
    description="Backend API for tracking household expenses, budgets, and reports.",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

# In development, allow all origins.
# In production, read the comma-separated ALLOWED_ORIGINS env var.
if settings.ENVIRONMENT == "development":
    _origins = ["*"]
else:
    _origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    if not _origins:
        logger.warning("ALLOWED_ORIGINS is not set — CORS will block all cross-origin requests.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

API_PREFIX = "/api"

app.include_router(accounts.router, prefix=API_PREFIX)
app.include_router(categories.router, prefix=API_PREFIX)
app.include_router(subcategories.router, prefix=API_PREFIX)
app.include_router(transactions.router, prefix=API_PREFIX)
app.include_router(import_csv.router, prefix=API_PREFIX)
app.include_router(amazon.router, prefix=API_PREFIX)
app.include_router(budgets.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    return {"status": "ok"}


