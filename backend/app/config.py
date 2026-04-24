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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
