from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SUPABASE_URL: str
    SUPABASE_JWT_SECRET: str = ""
    GEMINI_API_KEY: str
    GROQ_API_KEY: str = ""
    COHERE_API_KEY: str = ""
    ENVIRONMENT: str = "development"
    # Comma-separated list of allowed origins, e.g. "https://myapp.vercel.app"
    ALLOWED_ORIGINS: str = ""
    # Plaid (bank sync). Empty PLAID_CLIENT_ID disables the /plaid endpoints.
    PLAID_CLIENT_ID: str = ""
    PLAID_SECRET: str = ""
    PLAID_ENV: str = "sandbox"  # "sandbox" | "production"
    # Public URL Plaid calls with SYNC_UPDATES_AVAILABLE webhooks, e.g.
    # https://my-api.onrender.com/api/plaid/webhook. Optional — without it,
    # syncs only run on demand.
    PLAID_WEBHOOK_URL: str = ""
    # Fernet key for encrypting Plaid access tokens at rest. Optional in
    # development; strongly recommended in production.
    PLAID_TOKEN_ENCRYPTION_KEY: str = ""
    # Earliest transaction date to ingest from Plaid (ISO format, e.g.
    # 2026-01-01). Transactions dated before this are never imported — set it
    # to the day after your last CSV import to avoid duplicating history that
    # is already in the database. Empty = no cutoff (up to 730 days).
    PLAID_SYNC_START_DATE: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
