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
from app.routers import accounts, budgets, categories, import_csv, reports, subcategories, transactions

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

if settings.ENVIRONMENT == "development":
    allowed_origins = ["*"]
else:
    allowed_origins = [
        "https://expense-tracker.yourdomain.com",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
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
app.include_router(budgets.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    return {"status": "ok"}


@app.get("/debug/token", tags=["debug"])
async def debug_token(request: Request) -> dict:
    from jose import jwt as jose_jwt, JWTError
    from app.middleware.auth import _get_jwks
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return {"error": "No Bearer token"}
    token = auth_header.split(" ", 1)[1]
    try:
        header = jose_jwt.get_unverified_header(token)
        alg = header.get("alg", "HS256")
        if alg == "HS256":
            payload = jose_jwt.decode(token, settings.SUPABASE_JWT_SECRET, algorithms=["HS256"], options={"verify_aud": False})
        else:
            jwks = await _get_jwks()
            kid = header.get("kid")
            key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
            payload = jose_jwt.decode(token, key, algorithms=[alg], options={"verify_aud": False})
        return {"ok": True, "alg": alg, "payload": payload}
    except JWTError as e:
        return {"ok": False, "error": str(e), "header": header, "token_preview": token[:40]}
